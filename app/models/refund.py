import uuid
from datetime import datetime

from app.extensions import db


class Refund(db.Model):
    """
    Represents a refund against an existing sale.

    The original sale is never deleted.
    Instead, a separate refund transaction is created.
    """

    __tablename__ = "refunds"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Original sale being refunded.
    original_sale_id = db.Column(
        db.String(36),
        db.ForeignKey("sales.id"),
        nullable=False
    )

    # Branch where the refund was processed.
    branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    # Employee/admin who processed the refund.
    processed_by = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    # Reason for the refund.
    reason = db.Column(
        db.Text,
        nullable=False
    )

    # Refund status.
    #
    # COMPLETED = refund successfully processed
    # CANCELLED = refund cancelled before completion
    status = db.Column(
        db.String(30),
        nullable=False,
        default="COMPLETED"
    )

    # Total amount returned to the customer.
    total_refund_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Original sale relationship.
    original_sale = db.relationship(
        "Sale",
        back_populates="refunds"
    )

    # Branch relationship.
    branch = db.relationship(
        "Branch",
        backref=db.backref("refunds", lazy=True)
    )

    # User who processed the refund.
    processor = db.relationship(
        "User",
        foreign_keys=[processed_by],
        backref=db.backref("processed_refunds", lazy=True)
    )

    # Products included in this refund.
    items = db.relationship(
        "RefundItem",
        back_populates="refund",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<Refund {self.id}>"


class RefundItem(db.Model):
    """
    Represents an individual product being returned.

    A returned product can go back into:
    - SELLABLE stock
    - DAMAGED stock
    """

    __tablename__ = "refund_items"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Refund this item belongs to.
    refund_id = db.Column(
        db.String(36),
        db.ForeignKey("refunds.id"),
        nullable=False
    )

    # Original sale item being refunded.
    sale_item_id = db.Column(
        db.String(36),
        db.ForeignKey("sale_items.id"),
        nullable=False
    )

    # Product being returned.
    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id"),
        nullable=False
    )

    # Quantity being returned.
    quantity = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    # Unit of measurement.
    unit = db.Column(
        db.String(50),
        nullable=False
    )

    # Original actual selling price.
    unit_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Refund amount for this item.
    refund_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Where the returned product goes.
    #
    # SELLABLE = can be sold again
    # DAMAGED  = faulty/damaged and cannot be sold normally
    stock_destination = db.Column(
        db.String(30),
        nullable=False
    )

    refund = db.relationship(
        "Refund",
        back_populates="items"
    )

    sale_item = db.relationship(
        "SaleItem",
        back_populates="refund_items"
    )

    product = db.relationship(
        "Product",
        backref=db.backref("refund_items", lazy=True)
    )

    def __repr__(self):
        return f"<RefundItem {self.id}>"