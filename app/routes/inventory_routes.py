"""
Inventory and stock management routes for BrightSpark.

This module handles:

- Receiving stock
- Viewing branch inventory
- Low-stock products
- Stock adjustments
- Damaged stock
- Stock movement history

Inventory is branch-specific.

Employees can only access their assigned branch.
Administrators can access all branches.
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import (
    Product,
    Branch,
    InventoryBatch,
    StockMovement,
    User
)
from app.permissions.auth import (
    role_required,
    get_current_branch_id,
    get_current_role
)


inventory_bp = Blueprint(
    "inventory",
    __name__,
    url_prefix="/api/inventory"
)


# =========================================================
# CONSTANTS
# =========================================================

ALLOWED_MOVEMENT_TYPES = {
    "ADJUSTMENT_IN",
    "ADJUSTMENT_OUT",
    "DAMAGED"
}


# =========================================================
# HELPERS
# =========================================================

def decimal_value(value):
    """
    Safely convert a value to Decimal.
    """

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def serialize_batch(batch):
    """
    Serialize an inventory batch.
    """

    return {
        "id": batch.id,
        "product_id": batch.product_id,
        "branch_id": batch.branch_id,
        "quantity_received": float(batch.quantity_received),
        "quantity_remaining": float(batch.quantity_remaining),
        "unit_cost": float(batch.unit_cost),
        "selling_price": float(batch.selling_price),
        "received_by": batch.received_by,
        "received_at": (
            batch.received_at.isoformat()
            if batch.received_at
            else None
        ),
        "status": batch.status,
        "product": {
            "name": batch.product.name,
            "sku": batch.product.sku,
            "category": batch.product.category,
            "unit": batch.product.unit,
            "image_url": batch.product.image_url,
        },
        "branch": {
            "name": batch.branch.name,
            "location": batch.branch.location,
            "code": batch.branch.code,
        }
    }


def serialize_movement(movement):
    """
    Serialize a stock movement.
    """

    return {
        "id": movement.id,
        "product_id": movement.product_id,
        "branch_id": movement.branch_id,
        "movement_type": movement.movement_type,
        "quantity": float(movement.quantity),
        "reference": movement.reference,
        "reason": movement.reason,
        "created_by": movement.created_by,
        "created_at": (
            movement.created_at.isoformat()
            if movement.created_at
            else None
        ),
        "product": {
            "name": movement.product.name,
            "sku": movement.product.sku,
            "unit": movement.product.unit,
        },
        "branch": {
            "name": movement.branch.name,
            "code": movement.branch.code,
        }
    }


def validate_branch_access(branch_id):
    """
    Ensure the current user is allowed to access
    the requested branch.

    Admins can access all branches.

    Employees can only access their assigned branch.
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
    Calculate current sellable stock.

    Only ACTIVE inventory batches are included.
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


def get_product_branch_stock(product_id, branch_id):
    """
    Return product stock summary for a branch.
    """

    product = db.session.get(Product, product_id)

    if not product:
        return None

    quantity = get_available_quantity(
        product_id,
        branch_id
    )

    return {
        "product_id": product.id,
        "name": product.name,
        "sku": product.sku,
        "category": product.category,
        "unit": product.unit,
        "low_stock_threshold": float(
            product.low_stock_threshold
        ),
        "quantity": float(quantity),
        "is_low_stock": (
            quantity <= Decimal(
                str(product.low_stock_threshold)
            )
        ),
        "branch_id": branch_id,
    }


# =========================================================
# RECEIVE STOCK
# =========================================================

@inventory_bp.post("/receive")
@role_required("admin", "employee")
def receive_stock():
    """
    Receive new inventory into a branch.

    Employees automatically receive stock into their
    assigned branch.

    Administrators may specify a branch_id.
    """

    data = request.get_json() or {}

    product_id = data.get("product_id")
    quantity = decimal_value(data.get("quantity"))
    unit_cost = decimal_value(data.get("unit_cost"))
    selling_price = decimal_value(data.get("selling_price"))
    reason = str(
        data.get("reason", "New stock received")
    ).strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # -----------------------------------------------------
    # Determine branch
    # -----------------------------------------------------

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = data.get("branch_id")

    # -----------------------------------------------------
    # Validate required fields
    # -----------------------------------------------------

    if not product_id:
        return jsonify({
            "success": False,
            "message": "Product ID is required."
        }), 400

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Branch ID is required."
        }), 400

    if quantity is None or quantity <= 0:
        return jsonify({
            "success": False,
            "message": "Quantity must be greater than zero."
        }), 400

    if unit_cost is None or unit_cost < 0:
        return jsonify({
            "success": False,
            "message": "Unit cost must be zero or greater."
        }), 400

    if selling_price is None or selling_price < 0:
        return jsonify({
            "success": False,
            "message": "Selling price must be zero or greater."
        }), 400

    # -----------------------------------------------------
    # Validate branch access
    # -----------------------------------------------------

    if not validate_branch_access(branch_id):
        return jsonify({
            "success": False,
            "message": "You do not have access to this branch."
        }), 403

    # -----------------------------------------------------
    # Find product
    # -----------------------------------------------------

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    if not product.is_active:
        return jsonify({
            "success": False,
            "message": "Cannot receive stock for an inactive product."
        }), 400

    # -----------------------------------------------------
    # Find branch
    # -----------------------------------------------------

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    if not branch.is_active:
        return jsonify({
            "success": False,
            "message": "Cannot receive stock into an inactive branch."
        }), 400

    # -----------------------------------------------------
    # Current user
    # -----------------------------------------------------

    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    # -----------------------------------------------------
    # Create inventory batch
    # -----------------------------------------------------

    batch = InventoryBatch(
        product_id=product.id,
        branch_id=branch.id,
        quantity_received=quantity,
        quantity_remaining=quantity,
        unit_cost=unit_cost,
        selling_price=selling_price,
        received_by=user.id,
        status="ACTIVE"
    )

    db.session.add(batch)

    # -----------------------------------------------------
    # Create stock movement
    # -----------------------------------------------------

    movement = StockMovement(
        product_id=product.id,
        branch_id=branch.id,
        movement_type="STOCK_IN",
        quantity=quantity,
        reference=batch.id,
        reason=reason,
        created_by=user.id
    )

    db.session.add(movement)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Stock received successfully.",
        "batch": serialize_batch(batch),
        "movement": serialize_movement(movement)
    }), 201


# =========================================================
# GET INVENTORY
# =========================================================

@inventory_bp.get("")
@role_required("admin", "employee")
def get_inventory():
    """
    Get current inventory.

    Admin:
        Can optionally provide branch_id.

    Employee:
        Always restricted to assigned branch.
    """

    requested_branch_id = request.args.get("branch_id")
    product_id = request.args.get("product_id")
    search = request.args.get("search", "").strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # -----------------------------------------------------
    # Determine branch
    # -----------------------------------------------------

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = requested_branch_id

    # -----------------------------------------------------
    # Employee must have branch
    # -----------------------------------------------------

    if role == "employee" and not branch_id:
        return jsonify({
            "success": False,
            "message": "Employee is not assigned to a branch."
        }), 400

    # -----------------------------------------------------
    # Build query
    # -----------------------------------------------------

    query = InventoryBatch.query.filter(
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    )

    if branch_id:
        query = query.filter(
            InventoryBatch.branch_id == branch_id
        )

    if product_id:
        query = query.filter(
            InventoryBatch.product_id == product_id
        )

    if search:
        search_pattern = f"%{search}%"

        query = query.join(Product).filter(
            or_(
                Product.name.ilike(search_pattern),
                Product.sku.ilike(search_pattern),
                Product.category.ilike(search_pattern)
            )
        )

    batches = query.order_by(
        InventoryBatch.received_at.asc()
    ).all()

    # -----------------------------------------------------
    # Product summaries
    # -----------------------------------------------------

    summaries = {}

    for batch in batches:

        key = (
            batch.product_id,
            batch.branch_id
        )

        if key not in summaries:

            summaries[key] = {
                "product_id": batch.product_id,
                "branch_id": batch.branch_id,
                "name": batch.product.name,
                "sku": batch.product.sku,
                "category": batch.product.category,
                "unit": batch.product.unit,
                "low_stock_threshold": float(
                    batch.product.low_stock_threshold
                ),
                "quantity": Decimal("0")
            }

        summaries[key]["quantity"] += Decimal(
            str(batch.quantity_remaining)
        )

    inventory = []

    for summary in summaries.values():

        quantity = summary["quantity"]
        threshold = Decimal(
            str(summary["low_stock_threshold"])
        )

        inventory.append({
            **summary,
            "quantity": float(quantity),
            "is_low_stock": quantity <= threshold
        })

    return jsonify({
        "success": True,
        "count": len(inventory),
        "inventory": inventory
    }), 200


# =========================================================
# GET PRODUCT STOCK FOR A BRANCH
# =========================================================

@inventory_bp.get("/product/<string:product_id>")
@role_required("admin", "employee")
def get_product_inventory(product_id):
    """
    Get stock information for one product.

    Employees are restricted to their branch.

    Admins may provide:

    ?branch_id=<branch_id>
    """

    requested_branch_id = request.args.get("branch_id")

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

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

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.branch_id == branch_id,
        InventoryBatch.status == "ACTIVE"
    ).order_by(
        InventoryBatch.received_at.asc()
    ).all()

    total_quantity = Decimal("0")

    for batch in batches:
        total_quantity += Decimal(
            str(batch.quantity_remaining)
        )

    threshold = Decimal(
        str(product.low_stock_threshold)
    )

    return jsonify({
        "success": True,
        "product": {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "unit": product.unit,
            "low_stock_threshold": float(threshold),
            "image_url": product.image_url
        },
        "branch": {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
            "code": branch.code
        },
        "quantity": float(total_quantity),
        "is_low_stock": total_quantity <= threshold,
        "batches": [
            serialize_batch(batch)
            for batch in batches
        ]
    }), 200


# =========================================================
# LOW STOCK
# =========================================================

@inventory_bp.get("/low-stock")
@role_required("admin", "employee")
def get_low_stock():
    """
    Return products whose stock is at or below
    the configured low-stock threshold.
    """

    requested_branch_id = request.args.get("branch_id")

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

    if role == "employee" and not branch_id:
        return jsonify({
            "success": False,
            "message": "Employee is not assigned to a branch."
        }), 400

    # -----------------------------------------------------
    # Get active products
    # -----------------------------------------------------

    products = Product.query.filter_by(
        is_active=True
    ).order_by(
        Product.name.asc()
    ).all()

    low_stock = []

    for product in products:

        if branch_id:

            quantity = get_available_quantity(
                product.id,
                branch_id
            )

            threshold = Decimal(
                str(product.low_stock_threshold)
            )

            if quantity <= threshold:

                low_stock.append({
                    "product_id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "category": product.category,
                    "unit": product.unit,
                    "branch_id": branch_id,
                    "quantity": float(quantity),
                    "low_stock_threshold": float(
                        threshold
                    ),
                    "shortage": float(
                        max(
                            threshold - quantity,
                            Decimal("0")
                        )
                    )
                })

        else:

            branches = Branch.query.filter_by(
                is_active=True
            ).all()

            for branch in branches:

                quantity = get_available_quantity(
                    product.id,
                    branch.id
                )

                threshold = Decimal(
                    str(product.low_stock_threshold)
                )

                if quantity <= threshold:

                    low_stock.append({
                        "product_id": product.id,
                        "name": product.name,
                        "sku": product.sku,
                        "category": product.category,
                        "unit": product.unit,
                        "branch_id": branch.id,
                        "branch": {
                            "name": branch.name,
                            "code": branch.code
                        },
                        "quantity": float(quantity),
                        "low_stock_threshold": float(
                            threshold
                        ),
                        "shortage": float(
                            max(
                                threshold - quantity,
                                Decimal("0")
                            )
                        )
                    })

    return jsonify({
        "success": True,
        "count": len(low_stock),
        "low_stock": low_stock
    }), 200


# =========================================================
# STOCK ADJUSTMENT
# =========================================================

@inventory_bp.post("/adjust")
@role_required("admin", "employee")
def adjust_stock():
    """
    Adjust stock when the physical stock count differs
    from the system.

    Positive quantity:
        ADJUSTMENT_IN

    Negative quantity:
        ADJUSTMENT_OUT

    Employees can only adjust their own branch.
    """

    data = request.get_json() or {}

    product_id = data.get("product_id")
    requested_branch_id = data.get("branch_id")
    quantity = decimal_value(data.get("quantity"))
    reason = str(
        data.get("reason", "")
    ).strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # -----------------------------------------------------
    # Determine branch
    # -----------------------------------------------------

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

    # -----------------------------------------------------
    # Validate
    # -----------------------------------------------------

    if not product_id:
        return jsonify({
            "success": False,
            "message": "Product ID is required."
        }), 400

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Branch ID is required."
        }), 400

    if quantity is None or quantity == 0:
        return jsonify({
            "success": False,
            "message": "Adjustment quantity cannot be zero."
        }), 400

    if not reason:
        return jsonify({
            "success": False,
            "message": "A reason is required for stock adjustment."
        }), 400

    if not validate_branch_access(branch_id):
        return jsonify({
            "success": False,
            "message": "You do not have access to this branch."
        }), 403

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    user_id = get_jwt_identity()

    # -----------------------------------------------------
    # Positive adjustment
    # -----------------------------------------------------

    if quantity > 0:

        # For an adjustment-in, we need a cost basis.
        unit_cost = decimal_value(
            data.get("unit_cost")
        )

        selling_price = decimal_value(
            data.get("selling_price")
        )

        if unit_cost is None or unit_cost < 0:
            return jsonify({
                "success": False,
                "message": (
                    "Unit cost is required for positive "
                    "stock adjustments."
                )
            }), 400

        if selling_price is None or selling_price < 0:
            return jsonify({
                "success": False,
                "message": (
                    "Selling price is required for positive "
                    "stock adjustments."
                )
            }), 400

        batch = InventoryBatch(
            product_id=product.id,
            branch_id=branch.id,
            quantity_received=quantity,
            quantity_remaining=quantity,
            unit_cost=unit_cost,
            selling_price=selling_price,
            received_by=user_id,
            status="ACTIVE"
        )

        db.session.add(batch)

        movement = StockMovement(
            product_id=product.id,
            branch_id=branch.id,
            movement_type="ADJUSTMENT_IN",
            quantity=quantity,
            reference=batch.id,
            reason=reason,
            created_by=user_id
        )

        db.session.add(movement)

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Stock increased successfully.",
            "batch": serialize_batch(batch),
            "movement": serialize_movement(movement)
        }), 201

    # -----------------------------------------------------
    # Negative adjustment
    # -----------------------------------------------------

    adjustment_quantity = abs(quantity)

    available = get_available_quantity(
        product.id,
        branch.id
    )

    if adjustment_quantity > available:

        return jsonify({
            "success": False,
            "message": (
                "Adjustment exceeds available stock. "
                f"Available stock is {float(available)} "
                f"{product.unit}."
            )
        }), 400

    remaining_to_remove = adjustment_quantity

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product.id,
        InventoryBatch.branch_id == branch.id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).order_by(
        InventoryBatch.received_at.asc()
    ).all()

    for batch in batches:

        if remaining_to_remove <= 0:
            break

        batch_quantity = Decimal(
            str(batch.quantity_remaining)
        )

        quantity_to_remove = min(
            batch_quantity,
            remaining_to_remove
        )

        batch.quantity_remaining = (
            batch_quantity - quantity_to_remove
        )

        if batch.quantity_remaining == 0:
            batch.status = "DEPLETED"

        remaining_to_remove -= quantity_to_remove

    movement = StockMovement(
        product_id=product.id,
        branch_id=branch.id,
        movement_type="ADJUSTMENT_OUT",
        quantity=adjustment_quantity,
        reason=reason,
        created_by=user_id
    )

    db.session.add(movement)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Stock reduced successfully.",
        "quantity_removed": float(
            adjustment_quantity
        ),
        "movement": serialize_movement(movement)
    }), 201


# =========================================================
# RECORD DAMAGED STOCK
# =========================================================

@inventory_bp.post("/damage")
@role_required("admin", "employee")
def damage_stock():
    """
    Move sellable stock into damaged/defective stock.

    Damaged stock is removed from sellable inventory.

    It is recorded as a DAMAGED movement.
    """

    data = request.get_json() or {}

    product_id = data.get("product_id")
    requested_branch_id = data.get("branch_id")
    quantity = decimal_value(data.get("quantity"))
    reason = str(
        data.get("reason", "")
    ).strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

    if not product_id:
        return jsonify({
            "success": False,
            "message": "Product ID is required."
        }), 400

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Branch ID is required."
        }), 400

    if quantity is None or quantity <= 0:
        return jsonify({
            "success": False,
            "message": "Quantity must be greater than zero."
        }), 400

    if not reason:
        return jsonify({
            "success": False,
            "message": "A reason is required."
        }), 400

    if not validate_branch_access(branch_id):
        return jsonify({
            "success": False,
            "message": "You do not have access to this branch."
        }), 403

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    available = get_available_quantity(
        product.id,
        branch.id
    )

    if quantity > available:
        return jsonify({
            "success": False,
            "message": (
                "Damaged quantity exceeds available stock."
            )
        }), 400

    remaining_to_remove = quantity

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product.id,
        InventoryBatch.branch_id == branch.id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).order_by(
        InventoryBatch.received_at.asc()
    ).all()

    for batch in batches:

        if remaining_to_remove <= 0:
            break

        batch_quantity = Decimal(
            str(batch.quantity_remaining)
        )

        quantity_to_remove = min(
            batch_quantity,
            remaining_to_remove
        )

        batch.quantity_remaining = (
            batch_quantity - quantity_to_remove
        )

        if batch.quantity_remaining == 0:
            batch.status = "DEPLETED"

        remaining_to_remove -= quantity_to_remove

    user_id = get_jwt_identity()

    movement = StockMovement(
        product_id=product.id,
        branch_id=branch.id,
        movement_type="DAMAGED",
        quantity=quantity,
        reason=reason,
        created_by=user_id
    )

    db.session.add(movement)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Damaged stock recorded successfully.",
        "quantity_damaged": float(quantity),
        "movement": serialize_movement(movement)
    }), 201


# =========================================================
# STOCK MOVEMENTS
# =========================================================

@inventory_bp.get("/movements")
@role_required("admin", "employee")
def get_stock_movements():
    """
    Return stock movement history.

    Employees can only see movements for their branch.
    Admins can optionally filter by branch.
    """

    requested_branch_id = request.args.get("branch_id")
    product_id = request.args.get("product_id")
    movement_type = request.args.get("movement_type")

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "employee":
        branch_id = current_branch_id
    else:
        branch_id = requested_branch_id

    if role == "employee" and not branch_id:
        return jsonify({
            "success": False,
            "message": "Employee is not assigned to a branch."
        }), 400

    query = StockMovement.query

    if branch_id:
        query = query.filter(
            StockMovement.branch_id == branch_id
        )

    if product_id:
        query = query.filter(
            StockMovement.product_id == product_id
        )

    if movement_type:
        query = query.filter(
            StockMovement.movement_type ==
            movement_type.upper()
        )

    movements = query.order_by(
        StockMovement.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(movements),
        "movements": [
            serialize_movement(movement)
            for movement in movements
        ]
    }), 200