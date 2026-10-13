"""
Stock transfer routes for BrightSpark.

This module handles transferring stock between BrightSpark branches.

Transfer workflow:

1. Create a transfer.
2. Transfer starts as PENDING.
3. Complete the transfer.
4. Source branch receives TRANSFER_OUT movements.
5. Destination branch receives TRANSFER_IN movements.

Stock is only changed when a transfer is completed.
"""

from decimal import Decimal, InvalidOperation
import uuid

from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import (
    Branch,
    InventoryBatch,
    Product,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    User
)
from app.permissions.auth import (
    get_current_branch_id,
    get_current_role,
    role_required
)


transfers_bp = Blueprint(
    "transfers",
    __name__,
    url_prefix="/api/transfers"
)


def decimal_value(value):
    """
    Convert a value to Decimal safely.
    """

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def serialize_transfer(transfer):
    """
    Convert a StockTransfer model into a JSON-friendly dictionary.
    """

    return {
        "id": transfer.id,
        "source_branch_id": transfer.source_branch_id,
        "destination_branch_id": transfer.destination_branch_id,
        "created_by": transfer.created_by,
        "status": transfer.status,
        "transfer_reference": transfer.transfer_reference,
        "reason": transfer.reason,
        "created_at": (
            transfer.created_at.isoformat()
            if transfer.created_at
            else None
        ),
        "completed_at": (
            transfer.completed_at.isoformat()
            if transfer.completed_at
            else None
        ),
        "source_branch": {
            "id": transfer.source_branch.id,
            "name": transfer.source_branch.name,
            "location": transfer.source_branch.location,
            "code": transfer.source_branch.code,
        },
        "destination_branch": {
            "id": transfer.destination_branch.id,
            "name": transfer.destination_branch.name,
            "location": transfer.destination_branch.location,
            "code": transfer.destination_branch.code,
        },
        "created_by_user": {
            "id": transfer.creator.id,
            "full_name": transfer.creator.full_name,
            "email": transfer.creator.email,
        },
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": float(item.quantity),
                "unit": item.unit,
                "product": {
                    "name": item.product.name,
                    "sku": item.product.sku,
                    "category": item.product.category,
                }
            }
            for item in transfer.items
        ]
    }


def get_available_quantity(product_id, branch_id):
    """
    Calculate currently available sellable stock for a product
    at a specific branch.
    """

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.branch_id == branch_id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).all()

    total = Decimal("0")

    for batch in batches:
        total += Decimal(str(batch.quantity_remaining))

    return total


def validate_source_branch_access(branch_id):
    """
    Employees may only transfer stock from their own branch.

    Administrators can transfer from any active branch.
    """

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "admin":
        return True

    if role == "employee":
        return current_branch_id == branch_id

    return False


@transfers_bp.post("")
@role_required("admin", "employee")
def create_transfer():
    """
    Create a new pending stock transfer.

    Stock is NOT changed at this stage.
    """

    data = request.get_json() or {}

    requested_source_branch_id = data.get("source_branch_id")
    destination_branch_id = data.get("destination_branch_id")
    items = data.get("items", [])
    reason = str(data.get("reason", "")).strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # Employees cannot choose another source branch.
    if role == "employee":
        source_branch_id = current_branch_id
    else:
        source_branch_id = requested_source_branch_id

    if not source_branch_id:
        return jsonify({
            "success": False,
            "message": "Source branch ID is required."
        }), 400

    if not destination_branch_id:
        return jsonify({
            "success": False,
            "message": "Destination branch ID is required."
        }), 400

    if source_branch_id == destination_branch_id:
        return jsonify({
            "success": False,
            "message": "Source and destination branches must be different."
        }), 400

    if not items or not isinstance(items, list):
        return jsonify({
            "success": False,
            "message": "At least one transfer item is required."
        }), 400

    if not validate_source_branch_access(source_branch_id):
        return jsonify({
            "success": False,
            "message": "You do not have access to the source branch."
        }), 403

    source_branch = db.session.get(Branch, source_branch_id)
    destination_branch = db.session.get(Branch, destination_branch_id)

    if not source_branch:
        return jsonify({
            "success": False,
            "message": "Source branch not found."
        }), 404

    if not destination_branch:
        return jsonify({
            "success": False,
            "message": "Destination branch not found."
        }), 404

    if not source_branch.is_active:
        return jsonify({
            "success": False,
            "message": "Source branch is inactive."
        }), 400

    if not destination_branch.is_active:
        return jsonify({
            "success": False,
            "message": "Destination branch is inactive."
        }), 400

    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    validated_items = []

    for item in items:
        product_id = item.get("product_id")
        quantity = decimal_value(item.get("quantity"))

        if not product_id:
            return jsonify({
                "success": False,
                "message": "Each transfer item requires a product ID."
            }), 400

        if quantity is None or quantity <= 0:
            return jsonify({
                "success": False,
                "message": "Transfer quantity must be greater than zero."
            }), 400

        product = db.session.get(Product, product_id)

        if not product:
            return jsonify({
                "success": False,
                "message": f"Product {product_id} was not found."
            }), 404

        if not product.is_active:
            return jsonify({
                "success": False,
                "message": f"Product '{product.name}' is inactive."
            }), 400

        if quantity % Decimal("0.001") != 0:
            return jsonify({
                "success": False,
                "message": (
                    f"Quantity for '{product.name}' can have "
                    "up to three decimal places."
                )
            }), 400

        available = get_available_quantity(
            product.id,
            source_branch.id
        )

        if quantity > available:
            return jsonify({
                "success": False,
                "message": (
                    f"Insufficient stock for '{product.name}'. "
                    f"Available stock: {float(available)} "
                    f"{product.unit}."
                )
            }), 400

        validated_items.append({
            "product": product,
            "quantity": quantity
        })

    transfer_reference = (
        f"TRF-{uuid.uuid4().hex[:10].upper()}"
    )

    transfer = StockTransfer(
        source_branch_id=source_branch.id,
        destination_branch_id=destination_branch.id,
        created_by=user.id,
        status="PENDING",
        transfer_reference=transfer_reference,
        reason=reason or "Stock transfer"
    )

    db.session.add(transfer)

    # Flush so transfer.id is available before adding child records.
    db.session.flush()

    for item in validated_items:
        transfer_item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=item["product"].id,
            quantity=item["quantity"],
            unit=item["product"].unit
        )

        db.session.add(transfer_item)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Stock transfer created successfully.",
        "transfer": serialize_transfer(transfer)
    }), 201


@transfers_bp.get("")
@role_required("admin", "employee")
def get_transfers():
    """
    List stock transfers.

    Employees only see transfers involving their branch.
    Administrators can see all transfers or filter by branch.
    """

    requested_branch_id = request.args.get("branch_id")
    status = request.args.get("status")

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    query = StockTransfer.query

    if role == "employee":
        if not current_branch_id:
            return jsonify({
                "success": False,
                "message": "Employee is not assigned to a branch."
            }), 400

        query = query.filter(
            or_(
                StockTransfer.source_branch_id == current_branch_id,
                StockTransfer.destination_branch_id == current_branch_id
            )
        )

    elif requested_branch_id:
        query = query.filter(
            or_(
                StockTransfer.source_branch_id == requested_branch_id,
                StockTransfer.destination_branch_id == requested_branch_id
            )
        )

    if status:
        query = query.filter(
            StockTransfer.status == status.upper()
        )

    transfers = query.order_by(
        StockTransfer.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(transfers),
        "transfers": [
            serialize_transfer(transfer)
            for transfer in transfers
        ]
    }), 200


@transfers_bp.get("/<string:transfer_id>")
@role_required("admin", "employee")
def get_transfer(transfer_id):
    """
    Get a single stock transfer.
    """

    transfer = db.session.get(
        StockTransfer,
        transfer_id
    )

    if not transfer:
        return jsonify({
            "success": False,
            "message": "Stock transfer not found."
        }), 404

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        if current_branch_id not in {
            transfer.source_branch_id,
            transfer.destination_branch_id
        }:
            return jsonify({
                "success": False,
                "message": "You do not have access to this transfer."
            }), 403

    return jsonify({
        "success": True,
        "transfer": serialize_transfer(transfer)
    }), 200


@transfers_bp.patch("/<string:transfer_id>/complete")
@role_required("admin", "employee")
def complete_transfer(transfer_id):
    """
    Complete a pending stock transfer.

    FIFO is used to remove stock from the source branch.

    New inventory batches are created at the destination branch
    using the original source batch's unit cost and selling price.
    """

    transfer = db.session.get(
        StockTransfer,
        transfer_id
    )

    if not transfer:
        return jsonify({
            "success": False,
            "message": "Stock transfer not found."
        }), 404

    if transfer.status != "PENDING":
        return jsonify({
            "success": False,
            "message": (
                f"Transfer cannot be completed because its "
                f"status is {transfer.status}."
            )
        }), 400

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee" and current_branch_id != transfer.source_branch_id:
        return jsonify({
            "success": False,
            "message": (
                "Only an employee from the source branch "
                "can complete this transfer."
            )
        }), 403

    source_branch = db.session.get(
        Branch,
        transfer.source_branch_id
    )

    destination_branch = db.session.get(
        Branch,
        transfer.destination_branch_id
    )

    if not source_branch or not destination_branch:
        return jsonify({
            "success": False,
            "message": "Transfer branch information is invalid."
        }), 400

    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    try:
        # Process every product in the transfer.
        for transfer_item in transfer.items:

            remaining_to_transfer = Decimal(
                str(transfer_item.quantity)
            )

            product = db.session.get(
                Product,
                transfer_item.product_id
            )

            if not product:
                raise ValueError(
                    f"Product {transfer_item.product_id} was not found."
                )

            available = get_available_quantity(
                product.id,
                source_branch.id
            )

            if remaining_to_transfer > available:
                raise ValueError(
                    f"Insufficient stock for '{product.name}'. "
                    f"Available stock: {float(available)} "
                    f"{product.unit}."
                )

            # FIFO: oldest stock batches are transferred first.
            source_batches = InventoryBatch.query.filter(
                InventoryBatch.product_id == product.id,
                InventoryBatch.branch_id == source_branch.id,
                InventoryBatch.status == "ACTIVE",
                InventoryBatch.quantity_remaining > 0
            ).order_by(
                InventoryBatch.received_at.asc()
            ).all()

            for source_batch in source_batches:

                if remaining_to_transfer <= 0:
                    break

                source_quantity = Decimal(
                    str(source_batch.quantity_remaining)
                )

                quantity_to_transfer = min(
                    source_quantity,
                    remaining_to_transfer
                )

                # Remove quantity from source batch.
                source_batch.quantity_remaining = (
                    source_quantity - quantity_to_transfer
                )

                if source_batch.quantity_remaining == 0:
                    source_batch.status = "DEPLETED"

                # Create corresponding destination batch.
                destination_batch = InventoryBatch(
                    product_id=product.id,
                    branch_id=destination_branch.id,
                    quantity_received=quantity_to_transfer,
                    quantity_remaining=quantity_to_transfer,
                    unit_cost=source_batch.unit_cost,
                    selling_price=source_batch.selling_price,
                    received_by=user.id,
                    status="ACTIVE"
                )

                db.session.add(destination_batch)

                db.session.flush()

                # Source movement.
                source_movement = StockMovement(
                    product_id=product.id,
                    branch_id=source_branch.id,
                    movement_type="TRANSFER_OUT",
                    quantity=quantity_to_transfer,
                    reference=transfer.transfer_reference,
                    reason=(
                        f"Transfer to {destination_branch.name}"
                    ),
                    created_by=user.id
                )

                # Destination movement.
                destination_movement = StockMovement(
                    product_id=product.id,
                    branch_id=destination_branch.id,
                    movement_type="TRANSFER_IN",
                    quantity=quantity_to_transfer,
                    reference=transfer.transfer_reference,
                    reason=(
                        f"Transfer from {source_branch.name}"
                    ),
                    created_by=user.id
                )

                db.session.add(source_movement)
                db.session.add(destination_movement)

                remaining_to_transfer -= quantity_to_transfer

        transfer.status = "COMPLETED"
        transfer.completed_at = db.func.now()

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
                "completing the transfer."
            )
        }), 500

    return jsonify({
        "success": True,
        "message": "Stock transfer completed successfully.",
        "transfer": serialize_transfer(transfer)
    }), 200


@transfers_bp.patch("/<string:transfer_id>/cancel")
@role_required("admin", "employee")
def cancel_transfer(transfer_id):
    """
    Cancel a pending stock transfer.

    Cancelling does not change inventory because inventory
    has not yet been moved.
    """

    transfer = db.session.get(
        StockTransfer,
        transfer_id
    )

    if not transfer:
        return jsonify({
            "success": False,
            "message": "Stock transfer not found."
        }), 404

    if transfer.status != "PENDING":
        return jsonify({
            "success": False,
            "message": (
                f"Transfer cannot be cancelled because its "
                f"status is {transfer.status}."
            )
        }), 400

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        if current_branch_id != transfer.source_branch_id:
            return jsonify({
                "success": False,
                "message": (
                    "Only an employee from the source branch "
                    "can cancel this transfer."
                )
            }), 403

    transfer.status = "CANCELLED"

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Stock transfer cancelled successfully.",
        "transfer": serialize_transfer(transfer)
    }), 200