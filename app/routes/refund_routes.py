"""
Refund and return routes for BrightSpark.

This module handles:

- Full refunds
- Partial refunds
- Sellable returns
- Damaged/faulty returns
- Cash refunds
- M-Pesa refunds
- Split refunds
- Refund history

Important:
The original sale is never deleted.
A refund is recorded as a separate transaction.
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Sale,
    SaleItem,
    SalePayment,
    Refund,
    RefundItem,
    InventoryBatch,
    StockMovement,
    Product,
    Branch,
    User
)

from app.permissions.auth import (
    role_required,
    get_current_role,
    get_current_branch_id
)


refund_bp = Blueprint(
    "refunds",
    __name__,
    url_prefix="/api/refunds"
)


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def decimal_value(value):
    """Convert a value to Decimal safely."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def validate_branch_access(branch_id):
    """Ensure the current user can access the branch."""
    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "admin":
        return True

    if role == "employee":
        return current_branch_id == branch_id

    return False


def get_refunded_quantity(sale_item_id):
    """
    Calculate how much of a sale item has already been refunded.
    """

    refund_items = RefundItem.query.filter_by(
        sale_item_id=sale_item_id
    ).all()

    total = Decimal("0")

    for item in refund_items:
        total += Decimal(str(item.quantity))

    return total


def serialize_refund(refund):
    """Convert a refund to JSON."""
    return {
        "id": refund.id,
        "original_sale_id": refund.original_sale_id,
        "branch_id": refund.branch_id,
        "processed_by": refund.processed_by,
        "reason": refund.reason,
        "status": refund.status,
        "total_refund_amount": float(
            refund.total_refund_amount
        ),
        "created_at": (
            refund.created_at.isoformat()
            if refund.created_at
            else None
        ),
        "items": [
            {
                "id": item.id,
                "sale_item_id": item.sale_item_id,
                "product_id": item.product_id,
                "quantity": float(item.quantity),
                "unit": item.unit,
                "unit_price": float(item.unit_price),
                "refund_amount": float(item.refund_amount),
                "stock_destination": item.stock_destination
            }
            for item in refund.items
        ]
    }


# ---------------------------------------------------------
# Create refund
# ---------------------------------------------------------

@refund_bp.post("")
@role_required("admin", "employee")
def create_refund():

    data = request.get_json() or {}

    original_sale_id = data.get("original_sale_id")
    reason = str(data.get("reason", "")).strip()
    items = data.get("items", [])
    payment_method = str(
        data.get("payment_method", "")
    ).upper()

    if not original_sale_id:
        return jsonify({
            "success": False,
            "message": "Original sale ID is required."
        }), 400

    if not reason:
        return jsonify({
            "success": False,
            "message": "Refund reason is required."
        }), 400

    if not items or not isinstance(items, list):
        return jsonify({
            "success": False,
            "message": "At least one refund item is required."
        }), 400

    allowed_payment_methods = {
        "CASH",
        "MPESA",
        "SPLIT"
    }

    if payment_method not in allowed_payment_methods:
        return jsonify({
            "success": False,
            "message": (
                "Payment method must be CASH, MPESA "
                "or SPLIT."
            )
        }), 400

    # -----------------------------------------------------
    # Find original sale
    # -----------------------------------------------------

    sale = db.session.get(
        Sale,
        original_sale_id
    )

    if not sale:
        return jsonify({
            "success": False,
            "message": "Original sale not found."
        }), 404

    if sale.status != "COMPLETED":
        return jsonify({
            "success": False,
            "message": (
                "Only completed sales can be refunded."
            )
        }), 400

    # -----------------------------------------------------
    # Branch authorization
    # -----------------------------------------------------

    if not validate_branch_access(sale.branch_id):
        return jsonify({
            "success": False,
            "message": (
                "You do not have access to this sale."
            )
        }), 403

    branch = db.session.get(
        Branch,
        sale.branch_id
    )

    if not branch:
        return jsonify({
            "success": False,
            "message": "Sale branch not found."
        }), 404

    # -----------------------------------------------------
    # Current user
    # -----------------------------------------------------

    user_id = get_jwt_identity()

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    # -----------------------------------------------------
    # Validate refund items
    # -----------------------------------------------------

    sale_items = {
        item.id: item
        for item in sale.items
    }

    validated_items = []

    total_refund = Decimal("0")

    for requested_item in items:

        sale_item_id = requested_item.get(
            "sale_item_id"
        )

        quantity = decimal_value(
            requested_item.get("quantity")
        )

        stock_destination = str(
            requested_item.get(
                "stock_destination",
                "SELLABLE"
            )
        ).upper()

        if not sale_item_id:
            return jsonify({
                "success": False,
                "message": (
                    "Each refund item requires "
                    "sale_item_id."
                )
            }), 400

        if quantity is None or quantity <= 0:
            return jsonify({
                "success": False,
                "message": (
                    "Refund quantity must be greater "
                    "than zero."
                )
            }), 400

        if stock_destination not in {
            "SELLABLE",
            "DAMAGED"
        }:
            return jsonify({
                "success": False,
                "message": (
                    "Stock destination must be "
                    "SELLABLE or DAMAGED."
                )
            }), 400

        sale_item = sale_items.get(
            sale_item_id
        )

        if not sale_item:
            return jsonify({
                "success": False,
                "message": (
                    "Sale item does not belong "
                    "to the original sale."
                )
            }), 400

        # -------------------------------------------------
        # Calculate remaining refundable quantity
        # -------------------------------------------------

        original_quantity = Decimal(
            str(sale_item.quantity)
        )

        already_refunded = get_refunded_quantity(
            sale_item.id
        )

        remaining_quantity = (
            original_quantity
            - already_refunded
        )

        if quantity > remaining_quantity:
            return jsonify({
                "success": False,
                "message": (
                    f"Cannot refund {float(quantity)} "
                    f"{sale_item.unit}. "
                    f"Only {float(remaining_quantity)} "
                    f"{sale_item.unit} remain refundable."
                )
            }), 400

        unit_price = Decimal(
            str(sale_item.actual_selling_price)
        )

        refund_amount = (
            quantity * unit_price
        )

        total_refund += refund_amount

        validated_items.append({
            "sale_item": sale_item,
            "quantity": quantity,
            "unit_price": unit_price,
            "refund_amount": refund_amount,
            "stock_destination": stock_destination
        })

    if total_refund <= 0:
        return jsonify({
            "success": False,
            "message": "Refund amount must be greater than zero."
        }), 400

    # -----------------------------------------------------
    # Create refund
    # -----------------------------------------------------

    refund = Refund(
        original_sale_id=sale.id,
        branch_id=sale.branch_id,
        processed_by=user.id,
        reason=reason,
        status="COMPLETED",
        total_refund_amount=total_refund
    )

    db.session.add(refund)

    db.session.flush()

    # -----------------------------------------------------
    # Process each returned item
    # -----------------------------------------------------

    for item_data in validated_items:

        sale_item = item_data["sale_item"]
        quantity = item_data["quantity"]
        unit_price = item_data["unit_price"]
        refund_amount = item_data["refund_amount"]
        stock_destination = item_data[
            "stock_destination"
        ]

        refund_item = RefundItem(
            refund_id=refund.id,
            sale_item_id=sale_item.id,
            product_id=sale_item.product_id,
            quantity=quantity,
            unit=sale_item.unit,
            unit_price=unit_price,
            refund_amount=refund_amount,
            stock_destination=stock_destination
        )

        db.session.add(refund_item)

        # -------------------------------------------------
        # SELLABLE RETURN
        # -------------------------------------------------

        if stock_destination == "SELLABLE":

            returned_batch = InventoryBatch(
                product_id=sale_item.product_id,
                branch_id=sale.branch_id,
                quantity_received=quantity,
                quantity_remaining=quantity,
                unit_cost=sale_item.cost_price,
                selling_price=unit_price,
                received_by=user.id,
                status="ACTIVE"
            )

            db.session.add(returned_batch)

            db.session.flush()

            movement = StockMovement(
                product_id=sale_item.product_id,
                branch_id=sale.branch_id,
                movement_type="REFUND",
                quantity=quantity,
                reference=refund.id,
                reason=(
                    f"Refund from sale "
                    f"{sale.id}"
                ),
                created_by=user.id
            )

            db.session.add(movement)

        # -------------------------------------------------
        # DAMAGED RETURN
        # -------------------------------------------------

        else:

            movement = StockMovement(
                product_id=sale_item.product_id,
                branch_id=sale.branch_id,
                movement_type="DAMAGED",
                quantity=quantity,
                reference=refund.id,
                reason=(
                    f"Faulty/defective return "
                    f"from sale {sale.id}"
                ),
                created_by=user.id
            )

            db.session.add(movement)

    # -----------------------------------------------------
    # Commit
    # -----------------------------------------------------

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Refund processed successfully.",
        "refund": serialize_refund(refund)
    }), 201


# ---------------------------------------------------------
# Get refunds
# ---------------------------------------------------------

@refund_bp.get("")
@role_required("admin", "employee")
def get_refunds():

    sale_id = request.args.get(
        "original_sale_id"
    )

    requested_branch_id = request.args.get(
        "branch_id"
    )

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

    query = Refund.query

    if branch_id:
        query = query.filter(
            Refund.branch_id == branch_id
        )

    if sale_id:
        query = query.filter(
            Refund.original_sale_id == sale_id
        )

    refunds = query.order_by(
        Refund.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(refunds),
        "refunds": [
            serialize_refund(refund)
            for refund in refunds
        ]
    }), 200


# ---------------------------------------------------------
# Get one refund
# ---------------------------------------------------------

@refund_bp.get("/<string:refund_id>")
@role_required("admin", "employee")
def get_refund(refund_id):

    refund = db.session.get(
        Refund,
        refund_id
    )

    if not refund:
        return jsonify({
            "success": False,
            "message": "Refund not found."
        }), 404

    if not validate_branch_access(
        refund.branch_id
    ):
        return jsonify({
            "success": False,
            "message": (
                "You do not have access to this refund."
            )
        }), 403

    return jsonify({
        "success": True,
        "refund": serialize_refund(refund)
    }), 200