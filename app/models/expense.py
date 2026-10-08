import uuid
from datetime import datetime

from app.extensions import db


class Expense(db.Model):
    """
    Represents a business expense.

    IMPORTANT:
    Expenses do not have a VOIDED status.

    If an expense was entered incorrectly, the authorized user will
    actually delete the expense through the API.
    """

    __tablename__ = "expenses"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Branch where the expense occurred.
    branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    # Employee/admin who recorded the expense.
    employee_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    # Expense category.
    #
    # Examples:
    # Rent
    # Electricity
    # Water
    # Transport
    # Repairs & Maintenance
    # Salaries/Wages
    # Advertising/Marketing
    # Other
    category = db.Column(
        db.String(100),
        nullable=False
    )

    # Amount spent.
    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Description explaining the expense.
    description = db.Column(
        db.Text,
        nullable=True
    )

    # Payment method used.
    #
    # Currently:
    # CASH
    # MPESA
    payment_method = db.Column(
        db.String(30),
        nullable=False
    )

    # Date on which the expense occurred.
    expense_date = db.Column(
        db.Date,
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

    branch = db.relationship(
        "Branch",
        backref=db.backref("expenses", lazy=True)
    )

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id],
        backref=db.backref("expenses", lazy=True)
    )

    def __repr__(self):
        return f"<Expense {self.category} {self.amount}>"