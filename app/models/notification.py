import uuid
from datetime import datetime

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=True
    )

    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id"),
        nullable=True
    )

    notification_type = db.Column(
        db.String(50),
        nullable=False
    )

    title = db.Column(
        db.String(200),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    is_read = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    read_at = db.Column(
        db.DateTime,
        nullable=True
    )

    user = db.relationship(
        "User",
        back_populates="notifications"
    )

    branch = db.relationship(
        "Branch",
        back_populates="notifications"
    )

    product = db.relationship(
        "Product",
        back_populates="notifications"
    )

    def __repr__(self):
        return f"<Notification {self.notification_type}>"