import uuid
from datetime import datetime

from app.extensions import db


class InventoryBatch(db.Model):
    __tablename__ = "inventory_batches"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id"),
        nullable=False
    )

    branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    quantity_received = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    quantity_remaining = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    unit_cost = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    selling_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    received_by = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    received_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    status = db.Column(
        db.String(30),
        default="ACTIVE",
        nullable=False
    )

    product = db.relationship(
        "Product",
        back_populates="inventory_batches"
    )

    branch = db.relationship(
        "Branch",
        back_populates="inventory_batches"
    )

    receiver = db.relationship(
        "User",
        foreign_keys=[received_by]
    )

    def __repr__(self):
        return f"<InventoryBatch {self.id}>"