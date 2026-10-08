import uuid
from datetime import datetime

from app.extensions import db


class Branch(db.Model):
    __tablename__ = "branches"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = db.Column(db.String(100), nullable=False, unique=True)

    location = db.Column(db.String(255), nullable=False)

    code = db.Column(db.String(50), nullable=False, unique=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    users = db.relationship(
        "User",
        back_populates="branch",
        lazy=True
    )

    inventory_batches = db.relationship(
        "InventoryBatch",
        back_populates="branch",
        lazy=True
    )

    stock_movements = db.relationship(
        "StockMovement",
        back_populates="branch",
        lazy=True
    )

    def __repr__(self):
        return f"<Branch {self.name}>"