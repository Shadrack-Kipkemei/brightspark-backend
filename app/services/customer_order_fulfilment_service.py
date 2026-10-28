
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import (
    CustomerOrder,
    InventoryBatch,
    Sale,
    SaleItem,
    SalePayment,
    StockMovement,
    User,
)
from app.services.notification_service import (
    check_product_stock_notification,
)


CENT = Decimal("0.01")
ZERO = Decimal("0")

ALLOWED_PAYMENT_METHODS = {"CASH", "MPESA"}


def money(value):
    return Decimal(str(value)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def decimal_value(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def fulfil_customer_order(order_id, payments):
    """
    Convert a confirmed customer order into a completed sale.

    Uses saved order quantities and prices, consumes inventory
    using FIFO, calculates historical cost and gross profit,
    records payments, and completes the order in one transaction.

    Raises ValueError for validation or stock errors.
    """

    if not isinstance(payments, list) or not payments:
        raise ValueError("At least one payment is required.")

    validated_payments = []
    payment_total = ZERO

    for payment in payments:
        if not isinstance(payment, dict):
            raise ValueError("An invalid payment was provided.")

        method = str(
            payment.get("payment_method") or ""
        ).strip().upper()

        amount = decimal_value(payment.get("amount"))

        if method not in ALLOWED_PAYMENT_METHODS:
            raise ValueError(
                "Payment method must be CASH or MPESA."
            )

        if amount is None or amount <= ZERO:
            raise ValueError(
                "Payment amount must be greater than zero."
            )

        # Reject fractions of a cent instead of silently
        # changing the amount entered by staff.
        if amount != money(amount):
            raise ValueError(
                "Payment amounts can have at most two decimal places."
            )

        amount = money(amount)
        payment_total += amount

        validated_payments.append({
            "payment_method": method,
            "amount": amount,
        })

    try:
        # Lock the order so concurrent requests cannot fulfil it twice.
        order = (
            CustomerOrder.query
            .filter_by(id=order_id)
            .with_for_update()
            .first()
        )

        if not order:
            raise ValueError("Customer order not found.")

        if order.status != "CONFIRMED":
            raise ValueError(
                "Only confirmed orders can be fulfilled. "
                f"Current status: {order.status}."
            )

        # Also check the database relationship/foreign key value.
        existing_sale = Sale.query.filter_by(
            customer_order_id=order.id
        ).first()

        if existing_sale:
            raise ValueError(
                "This order has already been converted into a sale."
            )

        if not order.items:
            raise ValueError("This order has no items to fulfil.")

        employee_id = str(get_jwt_identity() or "")
        employee = db.session.get(User, employee_id)

        if not employee:
            raise ValueError("The current staff account was not found.")

        branch = order.branch

        if not branch or not branch.is_active:
            raise ValueError(
                "The branch associated with this order is unavailable."
            )

        # Payment must match the saved order total exactly.
        order_total = money(order.total_amount)
        payment_total = money(payment_total)

        if payment_total != order_total:
            raise ValueError(
                f"Payment total ({payment_total}) must equal "
                f"the order total ({order_total})."
            )

        # Employees may only fulfil orders at their assigned branch.
        # The route also checks this before calling the service.
        from app.permissions.auth import (
            get_current_branch_id,
            get_current_role,
        )

        if (
            get_current_role() == "employee"
            and get_current_branch_id() != order.branch_id
        ):
            raise ValueError(
                "You cannot fulfil an order belonging to another branch."
            )

        # Validate stored order lines before modifying inventory.
        order_lines = []

        for order_item in order.items:
            quantity = decimal_value(order_item.quantity)
            line_total = decimal_value(order_item.line_total)

            if quantity is None or quantity <= ZERO:
                raise ValueError(
                    f"Invalid quantity for {order_item.product_name}."
                )

            if line_total is None or line_total < ZERO:
                raise ValueError(
                    f"Invalid saved price for {order_item.product_name}."
                )

            if quantity % Decimal("0.001") != ZERO:
                raise ValueError(
                    f"Invalid quantity precision for "
                    f"{order_item.product_name}."
                )

            order_lines.append({
                "order_item": order_item,
                "quantity": quantity,
                "line_total": money(line_total),
            })

        calculated_order_total = money(sum(
            (line["line_total"] for line in order_lines),
            ZERO,
        ))

        if calculated_order_total != order_total:
            raise ValueError(
                "The saved order lines do not match the order total. "
                "Please review the order before fulfilling it."
            )

        # Lock and validate all relevant inventory before deducting
        # any quantities. This helps avoid partial fulfilment.
        locked_batches = {}

        for line in order_lines:
            order_item = line["order_item"]

            batches = (
                InventoryBatch.query
                .filter(
                    InventoryBatch.product_id == order_item.product_id,
                    InventoryBatch.branch_id == order.branch_id,
                    InventoryBatch.status == "ACTIVE",
                    InventoryBatch.quantity_remaining > ZERO,
                )
                .order_by(InventoryBatch.received_at.asc())
                .with_for_update()
                .all()
            )

            available = sum(
                (
                    Decimal(str(batch.quantity_remaining))
                    for batch in batches
                ),
                ZERO,
            )

            if available < line["quantity"]:
                raise ValueError(
                    f"Insufficient stock for {order_item.product_name}. "
                    f"Required: {line['quantity']}; available: {available}."
                )

            locked_batches[order_item.id] = batches

        sale = Sale(
            branch_id=order.branch_id,
            employee_id=employee.id,
            customer_id=None,
            customer_order_id=order.id,
            total_amount=order_total,
            total_cost=ZERO,
            gross_profit=ZERO,
            status="COMPLETED",
        )

        db.session.add(sale)
        db.session.flush()

        total_cost = ZERO
        notification_products = set()

        # Consume each order line using FIFO batch costs.
        for line in order_lines:
            order_item = line["order_item"]
            quantity = line["quantity"]
            remaining_quantity = quantity
            item_cost = ZERO

            batches = locked_batches[order_item.id]

            for batch in batches:
                if remaining_quantity <= ZERO:
                    break

                batch_quantity = Decimal(
                    str(batch.quantity_remaining)
                )

                if batch_quantity <= ZERO:
                    continue

                quantity_from_batch = min(
                    batch_quantity,
                    remaining_quantity,
                )

                historical_cost = Decimal(str(batch.unit_cost))

                item_cost += quantity_from_batch * historical_cost

                batch.quantity_remaining = (
                    batch_quantity - quantity_from_batch
                )

                if batch.quantity_remaining == ZERO:
                    batch.status = "DEPLETED"

                db.session.add(StockMovement(
                    product_id=order_item.product_id,
                    branch_id=order.branch_id,
                    movement_type="SALE",
                    quantity=quantity_from_batch,
                    reference=sale.id,
                    reason=f"Customer order {order.order_reference}",
                    created_by=employee.id,
                ))

                remaining_quantity -= quantity_from_batch

            if remaining_quantity > ZERO:
                raise ValueError(
                    f"Stock changed while fulfilling "
                    f"{order_item.product_name}. Please try again."
                )

            item_cost = money(item_cost)
            line_total = line["line_total"]

            # Use the saved order line total as authoritative.
            # The stored average selling price is rounded to cents.
            average_selling_price = money(line_total / quantity)

            db.session.add(SaleItem(
                sale_id=sale.id,
                product_id=order_item.product_id,
                quantity=quantity,
                unit=order_item.unit,
                cost_price=money(item_cost / quantity),
                actual_selling_price=average_selling_price,
                total=line_total,
            ))

            total_cost += item_cost
            notification_products.add(order_item.product_id)

        total_cost = money(total_cost)

        sale.total_cost = total_cost
        sale.gross_profit = money(order_total - total_cost)

        for payment in validated_payments:
            db.session.add(SalePayment(
                sale_id=sale.id,
                payment_method=payment["payment_method"],
                amount=payment["amount"],
            ))

        order.status = "COMPLETED"
        order.reviewed_by = employee.id
        from datetime import datetime
        order.reviewed_at = datetime.utcnow()

        # Save the sale, payments, order status and stock changes
        # together. A failure rolls the transaction back.
        db.session.flush()

        for product_id in notification_products:
            check_product_stock_notification(
                product_id,
                order.branch_id,
            )

        db.session.commit()
        return sale

    except Exception:
        db.session.rollback()
        raise
