"""
Admin dashboard routes for BrightSpark.

This module provides the data required by the
administrative dashboard.

The dashboard includes:

- Financial summary
- Branch summaries
- Recent sales
- Low-stock products
- Today's activity

All values are calculated from the database.
"""

from decimal import Decimal
from datetime import datetime, date, timedelta

from flask import Blueprint, jsonify, request

from app.extensions import db

from app.models import (
    Sale,
    SaleItem,
    Refund,
    RefundItem,
    Expense,
    Branch,
    Product,
    InventoryBatch
)

from app.permissions.auth import (
    role_required,
    get_current_role,
    get_current_branch_id
)


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/api/dashboard"
)


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def money(value):
    """Convert a database numeric value to float."""

    if value is None:
        return 0.0

    return float(
        Decimal(str(value))
    )


def get_available_quantity(
    product_id,
    branch_id
):
    """
    Calculate the current sellable quantity
    for a product in a branch.
    """

    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.branch_id == branch_id,
        InventoryBatch.status == "ACTIVE",
        InventoryBatch.quantity_remaining > 0
    ).all()

    quantity = Decimal("0")

    for batch in batches:

        quantity += Decimal(
            str(batch.quantity_remaining)
        )

    return quantity


def serialize_recent_sale(sale):
    """Serialize a sale for the dashboard."""

    items = []

    for item in sale.items:

        items.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": (
                item.product.name
                if item.product
                else None
            ),
            "sku": (
                item.product.sku
                if item.product
                else None
            ),
            "quantity": money(
                item.quantity
            ),
            "unit": item.unit,
            "actual_selling_price": money(
                item.actual_selling_price
            ),
            "total": money(
                item.total
            )
        })

    return {
        "id": sale.id,
        "branch_id": sale.branch_id,
        "branch": (
            {
                "id": sale.branch.id,
                "name": sale.branch.name,
                "code": sale.branch.code
            }
            if sale.branch
            else None
        ),
        "employee_id": sale.employee_id,
        "employee": (
            sale.employee.full_name
            if sale.employee
            else None
        ),
        "total_amount": money(
            sale.total_amount
        ),
        "total_cost": money(
            sale.total_cost
        ),
        "gross_profit": money(
            sale.gross_profit
        ),
        "status": sale.status,
        "sold_at": (
            sale.sold_at.isoformat()
            if sale.sold_at
            else None
        ),
        "items": items
    }


# ---------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------

@dashboard_bp.get("/summary")
@role_required("admin", "employee")
def dashboard_summary():

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    requested_branch_id = request.args.get(
        "branch_id"
    )

    # -----------------------------------------------------
    # Branch selection
    # -----------------------------------------------------

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = requested_branch_id

    # -----------------------------------------------------
    # Today's date
    # -----------------------------------------------------

    today = date.today()

    start_datetime = datetime.combine(
        today,
        datetime.min.time()
    )

    end_datetime = datetime.combine(
        today + timedelta(days=1),
        datetime.min.time()
    )

    # -----------------------------------------------------
    # Sales
    # -----------------------------------------------------

    sales_query = Sale.query.filter(
        Sale.status == "COMPLETED",
        Sale.sold_at >= start_datetime,
        Sale.sold_at < end_datetime
    )

    if branch_id:

        sales_query = sales_query.filter(
            Sale.branch_id == branch_id
        )

    sales = sales_query.all()

    gross_sales = Decimal("0")
    total_cogs = Decimal("0")

    for sale in sales:

        gross_sales += Decimal(
            str(sale.total_amount)
        )

        total_cogs += Decimal(
            str(sale.total_cost)
        )

    # -----------------------------------------------------
    # Refunds
    # -----------------------------------------------------

    refunds_query = Refund.query.filter(
        Refund.status == "COMPLETED",
        Refund.created_at >= start_datetime,
        Refund.created_at < end_datetime
    )

    if branch_id:

        refunds_query = refunds_query.filter(
            Refund.branch_id == branch_id
        )

    refunds = refunds_query.all()

    total_refunds = Decimal("0")
    refunded_cogs = Decimal("0")

    for refund in refunds:

        total_refunds += Decimal(
            str(refund.total_refund_amount)
        )

        for refund_item in refund.items:

            quantity = Decimal(
                str(refund_item.quantity)
            )

            sale_item = refund_item.sale_item

            if sale_item:

                refunded_cogs += (
                    quantity
                    * Decimal(
                        str(
                            sale_item.cost_price
                        )
                    )
                )

    # -----------------------------------------------------
    # Net sales
    # -----------------------------------------------------

    net_sales = (
        gross_sales
        - total_refunds
    )

    # -----------------------------------------------------
    # Net COGS
    # -----------------------------------------------------

    net_cogs = (
        total_cogs
        - refunded_cogs
    )

    if net_cogs < 0:

        net_cogs = Decimal("0")

    # -----------------------------------------------------
    # Gross profit
    # -----------------------------------------------------

    gross_profit = (
        net_sales
        - net_cogs
    )

    # -----------------------------------------------------
    # Expenses
    # -----------------------------------------------------

    expenses_query = Expense.query.filter(
        Expense.expense_date == today
    )

    if branch_id:

        expenses_query = expenses_query.filter(
            Expense.branch_id == branch_id
        )

    expenses = expenses_query.all()

    total_expenses = Decimal("0")

    for expense in expenses:

        total_expenses += Decimal(
            str(expense.amount)
        )

    # -----------------------------------------------------
    # Net profit
    # -----------------------------------------------------

    net_profit = (
        gross_profit
        - total_expenses
    )

    # -----------------------------------------------------
    # Tithe
    # -----------------------------------------------------

    tithe = (
        net_profit * Decimal("0.10")
        if net_profit > 0
        else Decimal("0")
    )

    return jsonify({
        "success": True,
        "summary": {
            "date": today.isoformat(),
            "branch_id": branch_id,
            "gross_sales": money(
                gross_sales
            ),
            "refunds": money(
                total_refunds
            ),
            "net_sales": money(
                net_sales
            ),
            "cogs": money(
                net_cogs
            ),
            "gross_profit": money(
                gross_profit
            ),
            "expenses": money(
                total_expenses
            ),
            "net_profit": money(
                net_profit
            ),
            "tithe": money(
                tithe
            ),
            "sales_count": len(
                sales
            ),
            "refund_count": len(
                refunds
            ),
            "expense_count": len(
                expenses
            )
        }
    }), 200


# ---------------------------------------------------------
# Branch summaries
# ---------------------------------------------------------

@dashboard_bp.get("/branches")
@role_required("admin")
def dashboard_branches():

    branches = Branch.query.filter_by(
        is_active=True
    ).order_by(
        Branch.name.asc()
    ).all()

    today = date.today()

    start_datetime = datetime.combine(
        today,
        datetime.min.time()
    )

    end_datetime = datetime.combine(
        today + timedelta(days=1),
        datetime.min.time()
    )

    results = []

    for branch in branches:

        # -------------------------------------------------
        # Sales
        # -------------------------------------------------

        sales = Sale.query.filter(
            Sale.branch_id == branch.id,
            Sale.status == "COMPLETED",
            Sale.sold_at >= start_datetime,
            Sale.sold_at < end_datetime
        ).all()

        total_sales = Decimal("0")

        for sale in sales:

            total_sales += Decimal(
                str(sale.total_amount)
            )

        # -------------------------------------------------
        # Inventory
        # -------------------------------------------------

        batches = InventoryBatch.query.filter(
            InventoryBatch.branch_id == branch.id,
            InventoryBatch.status == "ACTIVE",
            InventoryBatch.quantity_remaining > 0
        ).all()

        product_quantities = {}

        for batch in batches:

            product_quantities.setdefault(
                batch.product_id,
                Decimal("0")
            )

            product_quantities[
                batch.product_id
            ] += Decimal(
                str(
                    batch.quantity_remaining
                )
            )

        # -------------------------------------------------
        # Low stock
        # -------------------------------------------------

        low_stock_count = 0

        products = Product.query.filter_by(
            is_active=True
        ).all()

        for product in products:

            quantity = product_quantities.get(
                product.id,
                Decimal("0")
            )

            threshold = Decimal(
                str(
                    product.low_stock_threshold
                )
            )

            if quantity <= threshold:

                low_stock_count += 1

        # -------------------------------------------------
        # Count products with stock
        # -------------------------------------------------

        products_with_stock = 0

        for quantity in product_quantities.values():

            if quantity > 0:

                products_with_stock += 1

        results.append({

            "id": branch.id,

            "name": branch.name,

            "location": branch.location,

            "code": branch.code,

            "sales_today": money(
                total_sales
            ),

            "products_in_stock":
                products_with_stock,

            "low_stock_count":
                low_stock_count,

            "sales_count":
                len(sales)
        })

    return jsonify({
        "success": True,
        "branches": results
    }), 200


# ---------------------------------------------------------
# Recent sales
# ---------------------------------------------------------

@dashboard_bp.get("/recent-sales")
@role_required("admin", "employee")
def recent_sales():

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    requested_branch_id = request.args.get(
        "branch_id"
    )

    limit_value = request.args.get(
        "limit",
        "10"
    )

    try:

        limit = int(
            limit_value
        )

    except ValueError:

        limit = 10

    limit = max(
        1,
        min(
            limit,
            50
        )
    )

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = requested_branch_id

    query = Sale.query.filter(
        Sale.status == "COMPLETED"
    )

    if branch_id:

        query = query.filter(
            Sale.branch_id == branch_id
        )

    sales = query.order_by(
        Sale.sold_at.desc()
    ).limit(
        limit
    ).all()

    return jsonify({
        "success": True,
        "count": len(sales),
        "sales": [
            serialize_recent_sale(sale)
            for sale in sales
        ]
    }), 200


# ---------------------------------------------------------
# Low-stock products
# ---------------------------------------------------------

@dashboard_bp.get("/low-stock")
@role_required("admin", "employee")
def dashboard_low_stock():

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    requested_branch_id = request.args.get(
        "branch_id"
    )

    if role == "employee":

        branch_ids = [
            current_branch_id
        ]

    elif requested_branch_id:

        branch_ids = [
            requested_branch_id
        ]

    else:

        branch_ids = [
            branch.id
            for branch in Branch.query.filter_by(
                is_active=True
            ).all()
        ]

    products = Product.query.filter_by(
        is_active=True
    ).order_by(
        Product.name.asc()
    ).all()

    results = []

    for branch_id in branch_ids:

        branch = db.session.get(
            Branch,
            branch_id
        )

        if not branch:
            continue

        for product in products:

            quantity = get_available_quantity(
                product.id,
                branch.id
            )

            threshold = Decimal(
                str(
                    product.low_stock_threshold
                )
            )

            if quantity <= threshold:

                shortage = (
                    threshold - quantity
                )

                if shortage < 0:
                    shortage = Decimal("0")

                results.append({

                    "product_id":
                        product.id,

                    "product_name":
                        product.name,

                    "sku":
                        product.sku,

                    "category":
                        product.category,

                    "unit":
                        product.unit,

                    "branch_id":
                        branch.id,

                    "branch_name":
                        branch.name,

                    "branch_code":
                        branch.code,

                    "quantity":
                        money(quantity),

                    "low_stock_threshold":
                        money(threshold),

                    "shortage":
                        money(shortage),

                    "image_url":
                        product.image_url
                })

    return jsonify({
        "success": True,
        "count": len(results),
        "low_stock_products": results
    }), 200