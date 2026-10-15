"""
Sales routes for BrightSpark.

This module handles:

- Product search for sales
- Recording sales
- FIFO inventory consumption
- Cash payments
- M-Pesa payments
- Split payments
- Viewing sales
- Voiding incorrect sales

Important:

The employee enters the actual selling price.

The product's stored selling price is only a reference.
It is NOT automatically used as the final sale price.
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Branch,
    InventoryBatch,
    Product,
    Sale,
    SaleItem,
    SalePayment,
    StockMovement,
    User
)
from app.permissions.auth import (
    get_current_branch_id,
    get_current_role,
    role_required
)
from app.services.notification_service import (
    check_product_stock_notification
)


sales_bp = Blueprint(
    "sales",
    __name__,
    url_prefix="/api/sales"
)


ALLOWED_PAYMENT_METHODS = {
    "CASH",
    "MPESA"
}


def decimal_value(value):
    """
    Safely convert a value into Decimal.
    """

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def money(value):
    """
    Round monetary values to two decimal places.
    """

    return Decimal(str(value)).quantize(
        Decimal("0.01")
    )


def serialize_sale_item(item):
    """
    Serialize a sale item.
    """

    return {
        "id": item.id,
        "product_id": item.product_id,
        "quantity": float(item.quantity),
        "unit": item.unit,
        "cost_price": float(item.cost_price),
        "actual_selling_price": float(
            item.actual_selling_price
        ),
        "total": float(item.total),
        "product": {
            "name": item.product.name,
            "sku": item.product.sku,
            "category": item.product.category,
        }
    }


def serialize_sale_payment(payment):
    """
    Serialize a sale payment.
    """

    return {
        "id": payment.id,
        "payment_method": payment.payment_method,
        "amount": float(payment.amount),
        "created_at": (
            payment.created_at.isoformat()
            if payment.created_at
            else None
        )
    }


def serialize_sale(sale):
    """
    Serialize a complete sale.
    """

    return {
        "id": sale.id,
        "branch_id": sale.branch_id,
        "employee_id": sale.employee_id,
        "customer_id": sale.customer_id,
        "total_amount": float(sale.total_amount),
        "total_cost": float(sale.total_cost),
        "gross_profit": float(sale.gross_profit),
        "status": sale.status,
        "sold_at": (
            sale.sold_at.isoformat()
            if sale.sold_at
            else None
        ),
        "created_at": (
            sale.created_at.isoformat()
            if sale.created_at
            else None
        ),
        "branch": {
            "id": sale.branch.id,
            "name": sale.branch.name,
            "code": sale.branch.code,
        },
        "employee": {
            "id": sale.employee.id,
            "full_name": sale.employee.full_name,
            "email": sale.employee.email,
        },
        "items": [
            serialize_sale_item(item)
            for item in sale.items
        ],
        "payments": [
            serialize_sale_payment(payment)
            for payment in sale.payments
        ]
    }


def validate_branch_access(branch_id):
    """
    Employees can only operate in their assigned branch.

    Administrators can operate across branches.
    """

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "admin":
        return True

    if role == "employee":
        return current_branch_id == branch_id

    return False


def get_available_quantity(product_id, branch_id):
    """
    Calculate available sellable stock.
    """

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.branch_id == branch_id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).all()

    total = Decimal("0")

    for batch in batches:
        total += Decimal(
            str(batch.quantity_remaining)
        )

    return total


@sales_bp.get("/search-products")
@role_required("admin", "employee")
def search_products():
    """
    Search products for the employee sales screen.

    The response intentionally does NOT return a standard
    selling price as the final sale price.

    The employee enters the actual selling price manually.
    """

    search = request.args.get(
        "q",
        ""
    ).strip()

    if not search:
        return jsonify({
            "success": False,
            "message": "Search query is required."
        }), 400

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee" and not current_branch_id:
        return jsonify({
            "success": False,
            "message": "Employee is not assigned to a branch."
        }), 400

    search_pattern = f"%{search}%"

    products_query = Product.query.filter(
        Product.is_active.is_(True)
    ).filter(
        or_(
            Product.name.ilike(search_pattern),
            Product.sku.ilike(search_pattern),
            Product.category.ilike(search_pattern)
        )
    )

    products = products_query.order_by(
        Product.name.asc()
    ).limit(20).all()

    results = []

    for product in products:

        if role == "employee":
            branch_id = current_branch_id
            available = get_available_quantity(
                product.id,
                branch_id
            )

            if available <= 0:
                continue

        else:
            branch_id = request.args.get(
                "branch_id"
            )

            if branch_id:
                available = get_available_quantity(
                    product.id,
                    branch_id
                )
            else:
                available = Decimal("0")

        # Get FIFO batch cost as the current cost reference.
        batch_query = InventoryBatch.query.filter(
            InventoryBatch.product_id == product.id,
            InventoryBatch.status == "ACTIVE",
            InventoryBatch.quantity_remaining > 0
        )

        if branch_id:
            batch_query = batch_query.filter(
                InventoryBatch.branch_id == branch_id
            )

        first_batch = batch_query.order_by(
            InventoryBatch.received_at.asc()
        ).first()

        cost_price = (
            float(first_batch.unit_cost)
            if first_batch
            else None
        )

        results.append({
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "unit": product.unit,
            "cost_price": cost_price,
            "available_stock": float(available),
            "low_stock_threshold": float(
                product.low_stock_threshold
            ),
            "image_url": product.image_url,
            "branch_id": branch_id
        })

    return jsonify({
        "success": True,
        "count": len(results),
        "products": results
    }), 200


@sales_bp.post("")
@role_required("admin", "employee")
def create_sale():
    """
    Record a sale.

    FIFO inventory is consumed.

    The employee enters the actual selling price.

    Supported payments:

    - CASH
    - MPESA
    - Split payment using multiple payment records
    """

    data = request.get_json() or {}

    items = data.get("items", [])
    payments = data.get("payments", [])
    customer_id = data.get("customer_id")

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # Employees always use their assigned branch.
    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = data.get("branch_id")

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Branch ID is required."
        }), 400

    if not validate_branch_access(branch_id):
        return jsonify({
            "success": False,
            "message": "You do not have access to this branch."
        }), 403

    if not items:
        return jsonify({
            "success": False,
            "message": "At least one sale item is required."
        }), 400

    if not payments:
        return jsonify({
            "success": False,
            "message": "At least one payment is required."
        }), 400

    branch = db.session.get(
        Branch,
        branch_id
    )

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    if not branch.is_active:
        return jsonify({
            "success": False,
            "message": "Branch is inactive."
        }), 400

    employee_id = get_jwt_identity()

    employee = db.session.get(
        User,
        employee_id
    )

    if not employee:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    # Employees must belong to the branch.
    if (
        role == "employee"
        and employee.branch_id != branch.id
    ):
        return jsonify({
            "success": False,
            "message": "Employee is not assigned to this branch."
        }), 403

    validated_items = []

    # Validate all sale items before changing inventory.
    for item in items:

        product_id = item.get(
            "product_id"
        )

        quantity = decimal_value(
            item.get("quantity")
        )

        actual_selling_price = decimal_value(
            item.get("actual_selling_price")
        )

        if not product_id:
            return jsonify({
                "success": False,
                "message": "Product ID is required."
            }), 400

        if quantity is None or quantity <= 0:
            return jsonify({
                "success": False,
                "message": (
                    "Sale quantity must be greater than zero."
                )
            }), 400

        if actual_selling_price is None:
            return jsonify({
                "success": False,
                "message": (
                    "Actual selling price is required."
                )
            }), 400

        if actual_selling_price < 0:
            return jsonify({
                "success": False,
                "message": (
                    "Actual selling price cannot be negative."
                )
            }), 400

        product = db.session.get(
            Product,
            product_id
        )

        if not product:
            return jsonify({
                "success": False,
                "message": "Product not found."
            }), 404

        if not product.is_active:
            return jsonify({
                "success": False,
                "message": (
                    f"Product '{product.name}' is inactive."
                )
            }), 400

        if quantity % Decimal("0.001") != 0:
            return jsonify({
                "success": False,
                "message": (
                    f"Quantity for '{product.name}' "
                    "can have up to three decimal places."
                )
            }), 400

        available = get_available_quantity(
            product.id,
            branch.id
        )

        if quantity > available:
            return jsonify({
                "success": False,
                "message": (
                    f"Insufficient stock for "
                    f"'{product.name}'. "
                    f"Available: {float(available)} "
                    f"{product.unit}."
                )
            }), 400

        validated_items.append({
            "product": product,
            "quantity": quantity,
            "actual_selling_price": money(
                actual_selling_price
            )
        })

    # Calculate expected sale total.
    total_amount = Decimal("0")

    for item in validated_items:

        item_total = (
            item["quantity"]
            * item["actual_selling_price"]
        )

        total_amount += item_total

    total_amount = money(total_amount)

    # Validate payments.
    payment_total = Decimal("0")
    validated_payments = []

    for payment in payments:

        payment_method = str(
            payment.get("payment_method", "")
        ).strip().upper()

        amount = decimal_value(
            payment.get("amount")
        )

        if payment_method not in ALLOWED_PAYMENT_METHODS:
            return jsonify({
                "success": False,
                "message": (
                    "Payment method must be CASH or MPESA."
                )
            }), 400

        if amount is None or amount <= 0:
            return jsonify({
                "success": False,
                "message": (
                    "Payment amount must be greater than zero."
                )
            }), 400

        amount = money(amount)

        payment_total += amount

        validated_payments.append({
            "payment_method": payment_method,
            "amount": amount
        })

    payment_total = money(payment_total)

    if payment_total != total_amount:
        return jsonify({
            "success": False,
            "message": (
                f"Payment total ({float(payment_total)}) "
                f"must equal sale total "
                f"({float(total_amount)})."
            )
        }), 400

    try:

        sale = Sale(
            branch_id=branch.id,
            employee_id=employee.id,
            customer_id=customer_id,
            total_amount=total_amount,
            total_cost=Decimal("0"),
            gross_profit=Decimal("0"),
            status="COMPLETED"
        )

        db.session.add(sale)

        # Generate sale ID before adding child records.
        db.session.flush()

        total_cost = Decimal("0")

        # -------------------------------------------------
        # FIFO INVENTORY CONSUMPTION
        # -------------------------------------------------

        for item in validated_items:

            product = item["product"]
            remaining_quantity = item["quantity"]
            actual_price = item["actual_selling_price"]

            # Lock inventory rows while processing the sale.
            batches = InventoryBatch.query.filter(
                InventoryBatch.product_id == product.id,
                InventoryBatch.branch_id == branch.id,
                InventoryBatch.status == "ACTIVE",
                InventoryBatch.quantity_remaining > 0
            ).order_by(
                InventoryBatch.received_at.asc()
            ).with_for_update().all()

            available = Decimal("0")

            for batch in batches:
                available += Decimal(
                    str(batch.quantity_remaining)
                )

            if remaining_quantity > available:
                raise ValueError(
                    f"Insufficient stock for "
                    f"'{product.name}'."
                )

            item_cost = Decimal("0")

            while remaining_quantity > 0:

                current_batch = None

                for batch in batches:
                    if Decimal(
                        str(batch.quantity_remaining)
                    ) > 0:
                        current_batch = batch
                        break

                if current_batch is None:
                    raise ValueError(
                        f"Unable to find sufficient "
                        f"inventory for '{product.name}'."
                    )

                batch_quantity = Decimal(
                    str(current_batch.quantity_remaining)
                )

                quantity_from_batch = min(
                    batch_quantity,
                    remaining_quantity
                )

                historical_cost = Decimal(
                    str(current_batch.unit_cost)
                )

                item_cost += (
                    quantity_from_batch
                    * historical_cost
                )

                current_batch.quantity_remaining = (
                    batch_quantity
                    - quantity_from_batch
                )

                if current_batch.quantity_remaining == 0:
                    current_batch.status = "DEPLETED"

                stock_movement = StockMovement(
                    product_id=product.id,
                    branch_id=branch.id,
                    movement_type="SALE",
                    quantity=quantity_from_batch,
                    reference=sale.id,
                    reason="Stock sold",
                    created_by=employee.id
                )

                db.session.add(stock_movement)

                remaining_quantity -= quantity_from_batch

            item_total = money(
                item["quantity"]
                * actual_price
            )

            item_cost = money(item_cost)

            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=item["quantity"],
                unit=product.unit,
                cost_price=money(
                    item_cost / item["quantity"]
                ),
                actual_selling_price=actual_price,
                total=item_total
            )

            db.session.add(sale_item)

            total_cost += item_cost

        total_cost = money(total_cost)

        gross_profit = money(
            total_amount - total_cost
        )

        sale.total_cost = total_cost
        sale.gross_profit = gross_profit

        # -------------------------------------------------
        # PAYMENTS
        # -------------------------------------------------

        for payment in validated_payments:

            sale_payment = SalePayment(
                sale_id=sale.id,
                payment_method=payment["payment_method"],
                amount=payment["amount"]
            )

            db.session.add(sale_payment)

        check_product_stock_notification(
            product_id,
            branch_id
        )

        db.session.commit()

    except ValueError as error:

        db.session.rollback()

        return jsonify({
            "success": False,
            "message": str(error)
        }), 400

    except Exception:

        db.session.rollback()

        return jsonify({
            "success": False,
            "message": (
                "An unexpected error occurred while "
                "recording the sale."
            )
        }), 500

    return jsonify({
        "success": True,
        "message": "Sale recorded successfully.",
        "sale": serialize_sale(sale)
    }), 201


@sales_bp.get("")
@role_required("admin", "employee")
def get_sales():
    """
    List sales.

    Employees only see their own branch.

    Administrators can filter by branch.
    """

    requested_branch_id = request.args.get(
        "branch_id"
    )

    status = request.args.get(
        "status"
    )

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    query = Sale.query

    if role == "employee":

        if not current_branch_id:
            return jsonify({
                "success": False,
                "message": (
                    "Employee is not assigned to a branch."
                )
            }), 400

        query = query.filter(
            Sale.branch_id == current_branch_id
        )

    elif requested_branch_id:

        query = query.filter(
            Sale.branch_id == requested_branch_id
        )

    if status:
        query = query.filter(
            Sale.status == status.upper()
        )

    sales = query.order_by(
        Sale.sold_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(sales),
        "sales": [
            serialize_sale(sale)
            for sale in sales
        ]
    }), 200


@sales_bp.get("/<string:sale_id>")
@role_required("admin", "employee")
def get_sale(sale_id):
    """
    Get one sale.
    """

    sale = db.session.get(
        Sale,
        sale_id
    )

    if not sale:
        return jsonify({
            "success": False,
            "message": "Sale not found."
        }), 404

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if (
        role == "employee"
        and sale.branch_id != current_branch_id
    ):
        return jsonify({
            "success": False,
            "message": (
                "You do not have access to this sale."
            )
        }), 403

    return jsonify({
        "success": True,
        "sale": serialize_sale(sale)
    }), 200


@sales_bp.patch("/<string:sale_id>/void")
@role_required("admin")
def void_sale(sale_id):
    """
    Void an incorrect sale.

    Only administrators can void sales.

    The original sale record remains in the database.

    NOTE:
    Full inventory restoration and accounting reversal for
    voided sales should be handled carefully before production.
    """

    sale = db.session.get(
        Sale,
        sale_id
    )

    if not sale:
        return jsonify({
            "success": False,
            "message": "Sale not found."
        }), 404

    if sale.status == "VOIDED":
        return jsonify({
            "success": False,
            "message": "Sale is already voided."
        }), 400

    if sale.status != "COMPLETED":
        return jsonify({
            "success": False,
            "message": (
                f"Sale cannot be voided because its "
                f"status is {sale.status}."
            )
        }), 400

    sale.status = "VOIDED"

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Sale voided successfully.",
        "sale": serialize_sale(sale)
    }), 200