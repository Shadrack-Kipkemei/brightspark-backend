from datetime import datetime

from app.extensions import db
from app.models import (
    Branch,
    InventoryBatch,
    Notification,
    Product,
    User,
)


def get_product_stock(product_id, branch_id):
    """
    Calculate the current sellable quantity for a product
    in a specific branch.
    """

    batches = InventoryBatch.query.filter_by(
        product_id=product_id,
        branch_id=branch_id
    ).all()

    total_stock = sum(
        float(batch.quantity_remaining)
        for batch in batches
        if batch.status == "ACTIVE"
    )

    return total_stock


def create_notification(
    user_id,
    branch_id,
    product_id,
    notification_type,
    title,
    message
):
    """
    Create a notification for a user.

    Duplicate unread notifications for the same
    user/product/type are avoided.
    """

    existing_notification = Notification.query.filter_by(
        user_id=user_id,
        branch_id=branch_id,
        product_id=product_id,
        notification_type=notification_type,
        is_read=False
    ).first()

    if existing_notification:
        return existing_notification

    notification = Notification(
        user_id=user_id,
        branch_id=branch_id,
        product_id=product_id,
        notification_type=notification_type,
        title=title,
        message=message,
        is_read=False
    )

    db.session.add(notification)

    return notification


def notify_low_stock(product_id, branch_id):
    """
    Check a product's stock and create the appropriate
    low-stock or out-of-stock notifications.
    """

    product = db.session.get(Product, product_id)
    branch = db.session.get(Branch, branch_id)

    if not product or not branch:
        return

    if not product.is_active or not branch.is_active:
        return

    current_stock = get_product_stock(
        product_id,
        branch_id
    )

    threshold = float(product.low_stock_threshold)

    if current_stock <= 0:
        notification_type = "OUT_OF_STOCK"

        title = "Product Out of Stock"

        message = (
            f"{product.name} ({product.sku}) is out of stock "
            f"at {branch.name}."
        )

    elif current_stock <= threshold:
        notification_type = "LOW_STOCK"

        title = "Low Stock Alert"

        message = (
            f"{product.name} ({product.sku}) has low stock "
            f"at {branch.name}. "
            f"Current stock: {current_stock} {product.unit}. "
            f"Minimum level: {threshold} {product.unit}."
        )

    else:
        return

    users = User.query.filter(
        User.is_active.is_(True),
        User.role.in_(["admin", "employee"])
    ).all()

    for user in users:

        if user.role == "employee":
            if user.branch_id != branch_id:
                continue

        create_notification(
            user_id=user.id,
            branch_id=branch_id,
            product_id=product_id,
            notification_type=notification_type,
            title=title,
            message=message
        )

    db.session.flush()


def check_product_stock_notification(
    product_id,
    branch_id
):
    """
    Public helper used by inventory-related operations.
    """

    notify_low_stock(
        product_id,
        branch_id
    )