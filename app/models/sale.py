import uuid
from datetime import datetime

from app.extensions import db


class Sale(db.Model):
    """
    Represents a completed or otherwise recorded sale.

    A sale belongs to one branch and is processed by one employee/user.
    The total cost and gross profit are stored so that historical financial
    reports remain accurate even if product costs change later.
    """

    __tablename__ = "sales"

    # Unique identifier for the sale.
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Branch where the sale was made.
    branch_id = db.Column(
        db.String(36),
        db.ForeignKey("branches.id"),
        nullable=False
    )

    # Employee/admin who recorded the sale.
    employee_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False
    )

    # Optional customer reference.
    # We are keeping this nullable because customers do not have to create
    # accounts to purchase products.
    customer_id = db.Column(
        db.String(36),
        nullable=True
    )

    # Total amount actually charged to the customer.
    # This is based on the actual selling prices entered during the sale.
    total_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    # Historical cost of the products sold.
    # This is used to calculate COGS.
    total_cost = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    # Gross profit before expenses.
    #
    # Gross Profit = Total Sales - COGS
    gross_profit = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    # Sale status.
    #
    # COMPLETED = normal completed sale
    # VOIDED    = sale was cancelled/invalidated while preserving history
    status = db.Column(
        db.String(30),
        nullable=False,
        default="COMPLETED"
    )

    # Date and time when the sale was made.
    sold_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
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

    # Relationship to the branch where this sale occurred.
    branch = db.relationship(
        "Branch",
        backref=db.backref("sales", lazy=True)
    )

    # Relationship to the employee who recorded the sale.
    employee = db.relationship(
        "User",
        foreign_keys=[employee_id],
        backref=db.backref("sales", lazy=True)
    )

    # A sale can contain multiple products.
    items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy=True
    )

    # A sale can have one or more payment records.
    payments = db.relationship(
        "SalePayment",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy=True
    )

    # A sale can have one or more refunds.
    refunds = db.relationship(
        "Refund",
        back_populates="original_sale",
        lazy=True
    )

    def __repr__(self):
        return f"<Sale {self.id}>"


class SaleItem(db.Model):
    """
    Represents one product line within a sale.

    IMPORTANT:
    We store the cost price and actual selling price at the time of sale.
    This protects historical profit calculations from future price changes.
    """

    __tablename__ = "sale_items"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # The sale this item belongs to.
    sale_id = db.Column(
        db.String(36),
        db.ForeignKey("sales.id"),
        nullable=False
    )

    # The product being sold.
    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id"),
        nullable=False
    )

    # Quantity sold.
    # Numeric allows values such as:
    # 1, 2.5 metres, 500 millilitres, etc.
    quantity = db.Column(
        db.Numeric(12, 3),
        nullable=False
    )

    # Unit used for this sale.
    # Examples: Piece, Metre, Millilitre, Kilogram.
    unit = db.Column(
        db.String(50),
        nullable=False
    )

    # Cost price at the time this product was sold.
    #
    # This is NOT automatically taken from the current product record.
    # It represents the actual historical cost used for this sale.
    cost_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Actual selling price entered by the employee.
    #
    # This allows negotiated prices.
    actual_selling_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Quantity × actual selling price.
    total = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Relationship back to the sale.
    sale = db.relationship(
        "Sale",
        back_populates="items"
    )

    # Relationship to the product.
    product = db.relationship(
        "Product",
        backref=db.backref("sale_items", lazy=True)
    )

    # Refund items can reference this sale item.
    refund_items = db.relationship(
        "RefundItem",
        back_populates="sale_item",
        lazy=True
    )

    def __repr__(self):
        return f"<SaleItem {self.id}>"


class SalePayment(db.Model):
    """
    Records how a sale was paid.

    Supported methods:
    - CASH
    - MPESA
    - SPLIT

    For split payments, multiple payment rows can be created:
    e.g. KSh 500 CASH + KSh 300 MPESA.

    We intentionally do not store an M-Pesa transaction code because
    BrightSpark's current requirements do not require one.
    """

    __tablename__ = "sale_payments"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Sale associated with this payment.
    sale_id = db.Column(
        db.String(36),
        db.ForeignKey("sales.id"),
        nullable=False
    )

    # CASH or MPESA.
    payment_method = db.Column(
        db.String(30),
        nullable=False
    )

    # Amount paid using this method.
    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    sale = db.relationship(
        "Sale",
        back_populates="payments"
    )

    def __repr__(self):
        return f"<SalePayment {self.payment_method} {self.amount}>"