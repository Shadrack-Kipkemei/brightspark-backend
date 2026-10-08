import uuid
from datetime import datetime

from app.extensions import db


class StockTransfer(db.Model):
    """
    Represents a stock transfer between two BrightSpark branches.

    Example:
        Roysambu -> Rangau
        20 pieces of Phone Chargers

    The transfer itself records the business transaction while the
    stock movement table records the actual inventory changes.
    """

    __tablename__ = "stock_transfers"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Branch sending the stock.
    source_branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    # Branch receiving the stock.
    destination_branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    # User who created the transfer.
    created_by = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    # Transfer status.
    #
    # PENDING   = created but not completed
    # COMPLETED = stock successfully transferred
    # CANCELLED = transfer cancelled
    status = db.Column(
        db.String(30),
        nullable=False,
        default="PENDING"
    )

    # Optional human-readable transfer reference.
    transfer_reference = db.Column(
        db.String(100),
        nullable=True,
        unique=True
    )

    # Optional reason for the transfer.
    reason = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # Relationships to branches.
    source_branch = db.relationship(
        "Branch",
        foreign_keys=[source_branch_id],
        backref=db.backref("outgoing_transfers", lazy=True)
    )

    destination_branch = db.relationship(
        "Branch",
        foreign_keys=[destination_branch_id],
        backref=db.backref("incoming_transfers", lazy=True)
    )

    # User who created the transfer.
    creator = db.relationship(
        "User",
        foreign_keys=[created_by],
        backref=db.backref("stock_transfers_created", lazy=True)
    )

    # Products included in this transfer.
    items = db.relationship(
        "StockTransferItem",
        back_populates="transfer",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<StockTransfer {self.id}>"


class StockTransferItem(db.Model):
    """
    Represents a product and quantity included in a stock transfer.
    """

    __tablename__ = "stock_transfer_items"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Transfer this item belongs to.
    transfer_id = db.Column(
        db.String(36),
        db.ForeignKey("stock_transfers.id"),
        nullable=False
    )

    # Product being transferred.
    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id"),
        nullable=False
    )

    # Quantity being transferred.
    quantity = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    # Unit of measurement.
    unit = db.Column(
        db.String(50),
        nullable=False
    )

    transfer = db.relationship(
        "StockTransfer",
        back_populates="items"
    )

    product = db.relationship(
        "Product",
        backref=db.backref("stock_transfer_items", lazy=True)
    )

    def __repr__(self):
        return f"<StockTransferItem {self.id}>"