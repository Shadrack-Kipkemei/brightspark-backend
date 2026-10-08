import uuid
from datetime import datetime

from app.extensions import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = db.Column(
        db.String(200),
        nullable=False
    )

    sku = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    unit = db.Column(
        db.String(50),
        nullable=False,
        default="Piece"
    )

    low_stock_threshold = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=5
    )

    image_url = db.Column(
        db.String(500),
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

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

    inventory_batches = db.relationship(
        "InventoryBatch",
        back_populates="product",
        lazy=True
    )

    stock_movements = db.relationship(
        "StockMovement",
        back_populates="product",
        lazy=True
    )

    def __repr__(self):
        return f"<Product {self.name}>"