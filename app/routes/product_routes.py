"""
Product management routes for BrightSpark.

Products are global across the business.

Branch-specific stock is handled separately through
inventory batches and stock movements.
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import Product
from app.permissions.auth import role_required
from app.services.image_service import save_product_image


products_bp = Blueprint(
    "products",
    __name__,
    url_prefix="/api/products"
)


# =========================================================
# HELPERS
# =========================================================

ALLOWED_UNITS = {
    "Piece",
    "Metre",
    "Millilitre",
    "Litre",
    "Kilogram",
    "Gram",
    "Pack",
    "Pair",
    "Set",
}


def serialize_product(product):
    """
    Convert Product model into JSON.
    """

    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "category": product.category,
        "description": product.description,
        "unit": product.unit,
        "low_stock_threshold": float(
            product.low_stock_threshold
        ) if product.low_stock_threshold is not None else None,
        "image_url": product.image_url,
        "is_active": product.is_active,
        "created_at": (
            product.created_at.isoformat()
            if product.created_at
            else None
        ),
        "updated_at": (
            product.updated_at.isoformat()
            if product.updated_at
            else None
        ),
    }


def parse_threshold(value):
    """
    Convert low-stock threshold into Decimal.
    """

    try:
        threshold = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if threshold < 0:
        return None

    return threshold


# =========================================================
# CREATE PRODUCT
# =========================================================

@products_bp.post("")
@role_required("admin")
def create_product():
    """
    Create a new product.

    Only administrators can create products.
    """

    data = request.get_json() or {}

    name = str(data.get("name", "")).strip()
    sku = str(data.get("sku", "")).strip().upper()
    category = str(data.get("category", "")).strip()
    description = data.get("description")
    unit = str(data.get("unit", "Piece")).strip()
    image_url = data.get("image_url")

    # -----------------------------------------------------
    # Required fields
    # -----------------------------------------------------

    if not name:
        return jsonify({
            "success": False,
            "message": "Product name is required."
        }), 400

    if not sku:
        return jsonify({
            "success": False,
            "message": "SKU is required."
        }), 400

    if not category:
        return jsonify({
            "success": False,
            "message": "Category is required."
        }), 400

    # -----------------------------------------------------
    # Unit validation
    # -----------------------------------------------------

    if unit not in ALLOWED_UNITS:
        return jsonify({
            "success": False,
            "message": (
                "Invalid unit. Allowed units are: "
                + ", ".join(sorted(ALLOWED_UNITS))
            )
        }), 400

    # -----------------------------------------------------
    # Low stock threshold
    # -----------------------------------------------------

    threshold = parse_threshold(
        data.get("low_stock_threshold", 5)
    )

    if threshold is None:
        return jsonify({
            "success": False,
            "message": "Low-stock threshold must be a valid non-negative number."
        }), 400

    # -----------------------------------------------------
    # Check duplicate SKU
    # -----------------------------------------------------

    existing_product = Product.query.filter_by(
        sku=sku
    ).first()

    if existing_product:
        return jsonify({
            "success": False,
            "message": "A product with this SKU already exists."
        }), 409

    # -----------------------------------------------------
    # Create product
    # -----------------------------------------------------

    product = Product(
        name=name,
        sku=sku,
        category=category,
        description=description,
        unit=unit,
        low_stock_threshold=threshold,
        image_url=image_url,
        is_active=True
    )

    db.session.add(product)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Product created successfully.",
        "product": serialize_product(product)
    }), 201


# =========================================================
# GET PRODUCTS
# =========================================================

@products_bp.get("")
@role_required("admin", "employee")
def get_products():
    """
    Return products.

    Optional filters:

    ?search=charger
    ?category=Phone Accessories
    ?is_active=true
    ?is_active=false
    """

    query = Product.query

    search = request.args.get("search", "").strip()
    category = request.args.get("category")
    is_active = request.args.get("is_active")

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    if search:

        search_pattern = f"%{search}%"

        query = query.filter(
            or_(
                Product.name.ilike(search_pattern),
                Product.sku.ilike(search_pattern),
                Product.category.ilike(search_pattern)
            )
        )

    # -----------------------------------------------------
    # Category filter
    # -----------------------------------------------------

    if category:
        query = query.filter_by(
            category=category.strip()
        )

    # -----------------------------------------------------
    # Active status
    # -----------------------------------------------------

    if is_active is not None:

        if is_active.lower() not in {
            "true",
            "false"
        }:
            return jsonify({
                "success": False,
                "message": "is_active must be true or false."
            }), 400

        query = query.filter_by(
            is_active=is_active.lower() == "true"
        )

    products = query.order_by(
        Product.name.asc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(products),
        "products": [
            serialize_product(product)
            for product in products
        ]
    }), 200


# =========================================================
# SEARCH PRODUCTS
# =========================================================

@products_bp.get("/search")
@role_required("admin", "employee")
def search_products():
    """
    Search products by name, SKU or category.

    Intended for the employee sales form.

    Example:

    /api/products/search?q=charger
    """

    search = request.args.get("q", "").strip()

    if not search:
        return jsonify({
            "success": False,
            "message": "Search query is required."
        }), 400

    search_pattern = f"%{search}%"

    products = Product.query.filter(
        Product.is_active.is_(True),
        or_(
            Product.name.ilike(search_pattern),
            Product.sku.ilike(search_pattern),
            Product.category.ilike(search_pattern)
        )
    ).order_by(
        Product.name.asc()
    ).limit(20).all()

    return jsonify({
        "success": True,
        "count": len(products),
        "products": [
            serialize_product(product)
            for product in products
        ]
    }), 200


# =========================================================
# GET SINGLE PRODUCT
# =========================================================

@products_bp.get("/<string:product_id>")
@role_required("admin", "employee")
def get_product(product_id):
    """
    Return one product.
    """

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    return jsonify({
        "success": True,
        "product": serialize_product(product)
    }), 200


# =========================================================
# UPDATE PRODUCT
# =========================================================

@products_bp.put("/<string:product_id>")
@role_required("admin")
def update_product(product_id):
    """
    Update an existing product.

    Stock is NOT modified here.

    Stock changes belong to the inventory system.
    """

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    data = request.get_json() or {}

    # -----------------------------------------------------
    # Name
    # -----------------------------------------------------

    if "name" in data:

        name = str(data["name"]).strip()

        if not name:
            return jsonify({
                "success": False,
                "message": "Product name cannot be empty."
            }), 400

        product.name = name

    # -----------------------------------------------------
    # SKU
    # -----------------------------------------------------

    if "sku" in data:

        sku = str(data["sku"]).strip().upper()

        if not sku:
            return jsonify({
                "success": False,
                "message": "SKU cannot be empty."
            }), 400

        duplicate = Product.query.filter(
            Product.sku == sku,
            Product.id != product.id
        ).first()

        if duplicate:
            return jsonify({
                "success": False,
                "message": "Another product already uses this SKU."
            }), 409

        product.sku = sku

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    if "category" in data:

        category = str(data["category"]).strip()

        if not category:
            return jsonify({
                "success": False,
                "message": "Category cannot be empty."
            }), 400

        product.category = category

    # -----------------------------------------------------
    # Description
    # -----------------------------------------------------

    if "description" in data:
        product.description = data["description"]

    # -----------------------------------------------------
    # Unit
    # -----------------------------------------------------

    if "unit" in data:

        unit = str(data["unit"]).strip()

        if unit not in ALLOWED_UNITS:
            return jsonify({
                "success": False,
                "message": "Invalid product unit."
            }), 400

        product.unit = unit

    # -----------------------------------------------------
    # Low-stock threshold
    # -----------------------------------------------------

    if "low_stock_threshold" in data:

        threshold = parse_threshold(
            data["low_stock_threshold"]
        )

        if threshold is None:
            return jsonify({
                "success": False,
                "message": "Low-stock threshold must be a valid non-negative number."
            }), 400

        product.low_stock_threshold = threshold

    # -----------------------------------------------------
    # Image URL
    # -----------------------------------------------------

    if "image_url" in data:
        product.image_url = data["image_url"]

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Product updated successfully.",
        "product": serialize_product(product)
    }), 200


# =========================================================
# ACTIVATE PRODUCT
# =========================================================

@products_bp.patch("/<string:product_id>/activate")
@role_required("admin")
def activate_product(product_id):
    """
    Activate a product.
    """

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    if product.is_active:
        return jsonify({
            "success": True,
            "message": "Product is already active.",
            "product": serialize_product(product)
        }), 200

    product.is_active = True

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Product activated successfully.",
        "product": serialize_product(product)
    }), 200


# =========================================================
# DEACTIVATE PRODUCT
# =========================================================

@products_bp.patch("/<string:product_id>/deactivate")
@role_required("admin")
def deactivate_product(product_id):
    """
    Deactivate a product.

    We do not physically delete products because existing
    sales and inventory records may reference them.
    """

    product = db.session.get(Product, product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    if not product.is_active:
        return jsonify({
            "success": True,
            "message": "Product is already inactive.",
            "product": serialize_product(product)
        }), 200

    product.is_active = False

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Product deactivated successfully.",
        "product": serialize_product(product)
    }), 200