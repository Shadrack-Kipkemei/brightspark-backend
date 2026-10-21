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
from app.models import Product, Branch, InventoryBatch
from app.permissions.auth import role_required
from app.services.image_service import (
    save_product_image, 
    delete_product_image_file
)
from urllib.parse import urlparse


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

def is_valid_image_url(url):
    """
    Validate an external image URL.
    """

    if not url:
        return True
    try:
        parsed = urlparse(url)
        return(
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
        )
    except Exception:
        return False


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

    #-----------------------------------------------------
    # Form data and image upload
    #-----------------------------------------------------

    data = request.form

    name = str(data.get("name", "")).strip()
    sku = str(data.get("sku", "")).strip().upper()
    category = str(data.get("category", "")).strip()
    description = data.get("description")
    unit = str(data.get("unit", "Piece")).strip()

    image_file = request.files.get("image")
    image_url = str(data.get("image_url", "")).strip() or None

    if image_url and not is_valid_image_url(
        image_url
    ):
        return jsonify({
            "success": False,
            "message": (
                "Invalid image URL. "
                "Use a valid HTTP or HTTPS URL."
            )
        }), 400

    # Local upload takes priority over internet URL
    if image_file:
        try:
            image_url = save_product_image(image_file)
        except ValueError as error:
            return jsonify({
                "success": False,
                "message": str(error)
            }), 400

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

    data = request.form
    image_file = request.files.get("image")

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

    image_file = request.files.get("image")
    new_image_url = str(data.get("image_url", "")).strip()
    
    if image_file:
        old_image_url = product.image_url

        try:
            new_image_url = save_product_image(image_file)
        except ValueError as error:
            return jsonify({
                "success": False,
                "message": str(error)
            }), 400

        # Delete previous local image after
        # successfully saving the new one.
        if old_image_url:
            delete_product_image_file(old_image_url)
        product.image_url = new_image_url

    # -----------------------------------------------------
    # Internet Image URL
    # -----------------------------------------------------

    elif new_image_url:

        if not is_valid_image_url(new_image_url):
            return jsonify({
                "success": False,
                "message": (
                    "Invalid image URL. "
                    "Use a valid HTTP or HTTPS URL."
                )
            }), 400
        old_image_url = product.image_url

        # Only delete old local image.
        delete_product_image_file(old_image_url)
        product.image_url = new_image_url

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Product updated successfully.",
        "product": serialize_product(product)
    }), 200

@products_bp.delete("/<string:product_id>/image")
@role_required("admin")
def delete_product_image(product_id):
    """
    Delete a product image.
    
    Local BrightSpark images are physically deleted.
    External internet images are only removed from the database reference.
    """
    product = Product.query.get(product_id)

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    if not product.image_url:
        return jsonify({
            "succcess": False,
            "message": (
                "This product does not have an image."
            )
        }), 400

    # Delete the physical file only when
    # the image belongs to BrightSpark.
    delete_product_image_file(product.image_url)

    product.image_url = None
    db.session.commit()
    return jsonify({
        "success": True,
        "message": (
            "Product image deleted successfully."
        ),
        "product": serialize_product(
            product
        )
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



# =========================================================
# PUBLIC PRODUCT AVAILABILITY BY BRANCH
# =========================================================

@products_bp.get("/<string:product_id>/availability")
def get_public_product_availability(product_id):
    """
    Return sellable stock and the starting selling price
    for a product at a selected active branch.

    Public response deliberately excludes inventory costs,
    batch identifiers, employee details, and profit data.
    """

    branch_id = request.args.get("branch_id", "").strip()

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Please select a branch."
        }), 400

    product = db.session.get(Product, product_id)

    if not product or not product.is_active:
        return jsonify({
            "success": False,
            "message": "Product not found."
        }), 404

    branch = db.session.get(Branch, branch_id)

    if not branch or not branch.is_active:
        return jsonify({
            "success": False,
            "message": "Selected branch is unavailable."
        }), 404

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product.id,
        InventoryBatch.branch_id == branch.id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).order_by(
        InventoryBatch.selling_price.asc(),
        InventoryBatch.received_at.asc()
    ).all()

    quantity = sum(
        (
            Decimal(str(batch.quantity_remaining))
            for batch in batches
        ),
        Decimal("0")
    )

    # The lowest price among currently available batches.
    # The storefront should label this price "From".
    price_from = (
        Decimal(str(batches[0].selling_price))
        if batches
        else None
    )

    return jsonify({
        "success": True,
        "product_id": product.id,
        "branch": {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
        },
        "unit": product.unit,
        "quantity": float(quantity),
        "is_available": quantity > 0,
        "price_from": (
            float(price_from)
            if price_from is not None
            else None
        ),
    }), 200
