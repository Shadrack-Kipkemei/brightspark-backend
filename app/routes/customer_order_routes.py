
"""
Public customer-order routes for BrightSpark.

Submitting an order does not:
- Deduct inventory.
- Record payments.
- Create a sale.

Staff review orders separately.
"""

import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Branch,
    CustomerOrder,
    CustomerOrderItem,
    InventoryBatch,
    Product,
)
from app.permissions.auth import (
    get_current_branch_id,
    get_current_role,
    role_required,
)


customer_orders_bp = Blueprint(
    "customer_orders",
    __name__,
    url_prefix="/api/customer-orders",
)

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value):
    """Round a monetary amount to two decimal places."""
    return Decimal(str(value)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def serialize_order(order):
    """Convert an order and its items into JSON-safe data."""
    return {
        "id": order.id,
        "order_reference": order.order_reference,
        "branch": {
            "id": order.branch.id,
            "name": order.branch.name,
            "location": order.branch.location,
        },
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "customer_email": order.customer_email,
        "fulfilment_method": order.fulfilment_method,
        "delivery_address": order.delivery_address,
        "customer_notes": order.customer_notes,
        "total_amount": float(order.total_amount),
        "status": order.status,
        "reviewed_by": order.reviewed_by,
        "reviewed_at": (
            order.reviewed_at.isoformat()
            if order.reviewed_at
            else None
        ),
        "created_at": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
        "updated_at": (
            order.updated_at.isoformat()
            if order.updated_at
            else None
        ),
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "quantity": float(item.quantity),
                "unit": item.unit,
                "unit_price": float(item.unit_price),
                "line_total": float(item.line_total),
            }
            for item in order.items
        ],
    }


def staff_can_access_order(order):
    """
    Administrators can access all orders.

    Employees can access only orders belonging to their
    assigned branch, based on their JWT branch_id claim.
    """
    if get_current_role() == "admin":
        return True

    branch_id = get_current_branch_id()

    return bool(branch_id and order.branch_id == branch_id)


def make_order_reference():
    """Generate a customer-facing reference on the server."""
    date_part = datetime.utcnow().strftime("%Y%m%d")
    random_part = secrets.token_hex(4).upper()

    return f"BS-{date_part}-{random_part}"


def calculate_line_price(product, branch_id, requested_quantity):
    """
    Calculate an order line's price using active batches
    without reserving or deducting their inventory.

    When a quantity spans different price tiers, the lowest
    priced stock is quoted first, then the next-lowest tier.
    """
    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product.id,
        InventoryBatch.branch_id == branch_id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0,
    ).order_by(
        InventoryBatch.selling_price.asc(),
        InventoryBatch.received_at.asc(),
    ).all()

    available_quantity = sum(
        (
            Decimal(str(batch.quantity_remaining))
            for batch in batches
        ),
        ZERO,
    )

    if available_quantity < requested_quantity:
        return None, (
            f"Insufficient stock for {product.name}. "
            f"Available quantity: {available_quantity} {product.unit}."
        )

    quantity_left = requested_quantity
    line_total = ZERO

    for batch in batches:
        if quantity_left <= ZERO:
            break

        batch_quantity = Decimal(
            str(batch.quantity_remaining)
        )
        quantity_to_price = min(
            quantity_left,
            batch_quantity,
        )

        batch_price = Decimal(str(batch.selling_price))

        line_total += quantity_to_price * batch_price
        quantity_left -= quantity_to_price

    line_total = money(line_total)

    # Store an indicative average unit price for the order.
    # line_total remains the authoritative line amount.
    unit_price = money(line_total / requested_quantity)

    return {
        "quantity": requested_quantity,
        "unit_price": unit_price,
        "line_total": line_total,
    }, None


# =========================================================
# PUBLIC: SUBMIT AN ORDER
# =========================================================

@customer_orders_bp.post("")
def create_customer_order():
    """
    Submit an order without requiring customer login.

    The server calculates prices from current branch inventory.
    No stock is deducted and no sale or payment is created.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Please submit a valid JSON order.",
        }), 400

    branch_id = str(data.get("branch_id") or "").strip()
    customer_name = str(
        data.get("customer_name") or ""
    ).strip()
    customer_phone = str(
        data.get("customer_phone") or ""
    ).strip()
    customer_email = str(
        data.get("customer_email") or ""
    ).strip() or None

    fulfilment_method = str(
        data.get("fulfilment_method") or ""
    ).strip().upper()

    delivery_address = str(
        data.get("delivery_address") or ""
    ).strip() or None

    customer_notes = str(
        data.get("customer_notes") or ""
    ).strip() or None

    items = data.get("items")

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Please select a branch.",
        }), 400

    if not customer_name or len(customer_name) > 150:
        return jsonify({
            "success": False,
            "message": "Enter a valid customer name.",
        }), 400

    if not customer_phone or len(customer_phone) > 30:
        return jsonify({
            "success": False,
            "message": "Enter a valid phone number.",
        }), 400

    if customer_email and len(customer_email) > 255:
        return jsonify({
            "success": False,
            "message": "Email address is too long.",
        }), 400

    if fulfilment_method not in {"PICKUP", "DELIVERY"}:
        return jsonify({
            "success": False,
            "message": (
                "Fulfilment method must be PICKUP or DELIVERY."
            ),
        }), 400

    if (
        fulfilment_method == "DELIVERY"
        and not delivery_address
    ):
        return jsonify({
            "success": False,
            "message": "A delivery address is required.",
        }), 400

    if (
        delivery_address
        and len(delivery_address) > 5000
    ):
        return jsonify({
            "success": False,
            "message": "Delivery address is too long.",
        }), 400

    if not isinstance(items, list) or not items:
        return jsonify({
            "success": False,
            "message": "Your order must contain at least one item.",
        }), 400

    if len(items) > 100:
        return jsonify({
            "success": False,
            "message": "An order cannot contain more than 100 items.",
        }), 400

    branch = db.session.get(Branch, branch_id)

    if not branch or not branch.is_active:
        return jsonify({
            "success": False,
            "message": "The selected branch is unavailable.",
        }), 400

    # Validate all lines and reject duplicate product IDs.
    validated_items = []
    seen_product_ids = set()

    for item in items:
        if not isinstance(item, dict):
            return jsonify({
                "success": False,
                "message": "An order item is invalid.",
            }), 400

        product_id = str(
            item.get("product_id") or ""
        ).strip()

        if not product_id:
            return jsonify({
                "success": False,
                "message": "An order item is missing its product ID.",
            }), 400

        if product_id in seen_product_ids:
            return jsonify({
                "success": False,
                "message": (
                    "Each product should appear only once in an order. "
                    "Combine duplicate product quantities."
                ),
            }), 400

        seen_product_ids.add(product_id)

        try:
            quantity = Decimal(str(item.get("quantity")))
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({
                "success": False,
                "message": f"Invalid quantity for product {product_id}.",
            }), 400

        if (
            not quantity.is_finite()
            or quantity <= ZERO
            or quantity.as_tuple().exponent < -3
        ):
            return jsonify({
                "success": False,
                "message": (
                    "Quantities must be positive and may have "
                    "at most three decimal places."
                ),
            }), 400

        product = db.session.get(Product, product_id)

        if not product or not product.is_active:
            return jsonify({
                "success": False,
                "message": (
                    f"Product {product_id} is unavailable."
                ),
            }), 400

        validated_items.append((product, quantity))

    # Calculate each line from database prices.
    # Prices supplied by the browser are deliberately ignored.
    priced_items = []
    total_amount = ZERO

    for product, quantity in validated_items:
        pricing, error = calculate_line_price(
            product,
            branch.id,
            quantity,
        )

        if error:
            return jsonify({
                "success": False,
                "message": error,
            }), 409

        priced_items.append((product, pricing))
        total_amount += pricing["line_total"]

    total_amount = money(total_amount)

    order = CustomerOrder(
        order_reference=make_order_reference(),
        branch_id=branch.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        fulfilment_method=fulfilment_method,
        delivery_address=(
            delivery_address
            if fulfilment_method == "DELIVERY"
            else None
        ),
        customer_notes=customer_notes,
        total_amount=total_amount,
        status="PENDING",
    )

    db.session.add(order)

    for product, pricing in priced_items:
        order.items.append(
            CustomerOrderItem(
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                quantity=pricing["quantity"],
                unit=product.unit,
                unit_price=pricing["unit_price"],
                line_total=pricing["line_total"],
            )
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({
        "success": True,
        "message": (
            "Your order has been received and is awaiting "
            "staff review. No payment has been recorded."
        ),
        "order": serialize_order(order),
    }), 201


# =========================================================
# STAFF: LIST ORDERS
# =========================================================

@customer_orders_bp.get("")
@role_required("admin", "employee")
def get_customer_orders():
    """List customer orders visible to the current staff member."""
    query = CustomerOrder.query

    if get_current_role() != "admin":
        branch_id = get_current_branch_id()

        if not branch_id:
            return jsonify({
                "success": False,
                "message": (
                    "Your employee account has no assigned branch."
                ),
            }), 403

        query = query.filter(
            CustomerOrder.branch_id == branch_id
        )

    status = request.args.get("status", "").strip().upper()

    allowed_statuses = {
        "PENDING",
        "CONFIRMED",
        "REJECTED",
    }

    if status:
        if status not in allowed_statuses:
            return jsonify({
                "success": False,
                "message": "Invalid order status filter.",
            }), 400

        query = query.filter(
            CustomerOrder.status == status
        )

    orders = query.order_by(
        CustomerOrder.created_at.desc()
    ).limit(100).all()

    return jsonify({
        "success": True,
        "count": len(orders),
        "orders": [
            serialize_order(order)
            for order in orders
        ],
    }), 200


# =========================================================
# STAFF: VIEW ONE ORDER
# =========================================================

@customer_orders_bp.get("/<string:order_id>")
@role_required("admin", "employee")
def get_customer_order(order_id):
    """View an individual order."""
    order = db.session.get(CustomerOrder, order_id)

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found.",
        }), 404

    if not staff_can_access_order(order):
        return jsonify({
            "success": False,
            "message": "You cannot access orders for another branch.",
        }), 403

    return jsonify({
        "success": True,
        "order": serialize_order(order),
    }), 200


# =========================================================
# STAFF: REVIEW AN ORDER
# =========================================================

@customer_orders_bp.patch("/<string:order_id>/status")
@role_required("admin", "employee")
def update_customer_order_status(order_id):
    """
    Review a pending order.

    Only CONFIRMED or REJECTED are allowed here.
    Confirmation does not create a sale or deduct stock.
    """
    from flask_jwt_extended import get_jwt_identity

    order = db.session.get(CustomerOrder, order_id)

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found.",
        }), 404

    if not staff_can_access_order(order):
        return jsonify({
            "success": False,
            "message": "You cannot review orders for another branch.",
        }), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Please provide a valid JSON request.",
        }), 400

    new_status = str(
        data.get("status") or ""
    ).strip().upper()

    if new_status not in {"CONFIRMED", "REJECTED"}:
        return jsonify({
            "success": False,
            "message": (
                "Status must be CONFIRMED or REJECTED."
            ),
        }), 400

    if order.status != "PENDING":
        return jsonify({
            "success": False,
            "message": (
                "Only pending orders can be reviewed. "
                f"Current status: {order.status}."
            ),
        }), 409

    order.status = new_status
    order.reviewed_by = str(get_jwt_identity())
    order.reviewed_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "success": True,
        "message": (
            "Order reviewed successfully. "
            "No inventory was deducted and no sale was recorded."
        ),
        "order": serialize_order(order),
    }), 200



# =========================================================
# STAFF: FULFIL A CONFIRMED ORDER
# =========================================================

@customer_orders_bp.post("/<string:order_id>/fulfil")
@role_required("admin", "employee")
def fulfil_customer_order_route(order_id):
    """
    Convert a confirmed customer order into a sale.

    The request contains payment details only.
    Products, quantities and prices come from the saved order.
    """

    from app.services.customer_order_fulfilment_service import (
        fulfil_customer_order,
    )

    order = db.session.get(CustomerOrder, order_id)

    if not order:
        return jsonify({
            "success": False,
            "message": "Customer order not found.",
        }), 404

    if not staff_can_access_order(order):
        return jsonify({
            "success": False,
            "message": (
                "You cannot fulfil orders belonging to another branch."
            ),
        }), 403

    if order.status != "CONFIRMED":
        return jsonify({
            "success": False,
            "message": (
                "Only confirmed orders can be fulfilled. "
                f"Current status: {order.status}."
            ),
        }), 409

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Please provide a valid JSON request.",
        }), 400

    # Intentionally accept payment details only.
    # Never accept replacement products, quantities or prices here.
    if "items" in data or "total_amount" in data:
        return jsonify({
            "success": False,
            "message": (
                "Items and prices are taken from the saved order. "
                "Submit payment details only."
            ),
        }), 400

    try:
        sale = fulfil_customer_order(
            order_id=order_id,
            payments=data.get("payments"),
        )

        return jsonify({
            "success": True,
            "message": (
                "Customer order fulfilled successfully. "
                "The sale and payments have been recorded."
            ),
            "order": serialize_order(
                db.session.get(CustomerOrder, order_id)
            ),
            "sale": {
                "id": sale.id,
                "customer_order_id": sale.customer_order_id,
                "branch_id": sale.branch_id,
                "employee_id": sale.employee_id,
                "total_amount": float(sale.total_amount),
                "total_cost": float(sale.total_cost),
                "gross_profit": float(sale.gross_profit),
                "status": sale.status,
            },
        }), 201

    except ValueError as error:
        db.session.rollback()

        return jsonify({
            "success": False,
            "message": str(error),
        }), 400

    except Exception:
        db.session.rollback()

        return jsonify({
            "success": False,
            "message": (
                "An unexpected error occurred while fulfilling "
                "the customer order. No partial sale was saved."
            ),
        }), 500
