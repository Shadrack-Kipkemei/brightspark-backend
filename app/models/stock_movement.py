import uuid
from datetime import datetime

from app.extensions import db


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

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

    movement_type = db.Column(
        db.String(50),
        nullable=False
    )

    quantity = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    reference = db.Column(
        db.String(100),
        nullable=True
    )

    reason = db.Column(
        db.Text,
        nullable=True
    )

    created_by = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    product = db.relationship(
        "Product",
        back_populates="stock_movements"
    )

    branch = db.relationship(
        "Branch",
        back_populates="stock_movements"
    )

    creator = db.relationship(
        "User",
        foreign_keys=[created_by]
    )

    def __repr__(self):
        return f"<StockMovement {self.movement_type}>"