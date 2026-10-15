"""
Financial reporting routes for BrightSpark.

Calculates:

- Gross sales
- Refunds
- Net sales
- COGS
- Gross profit
- Expenses
- Net profit
- Tithe

Reports can be filtered by:

- Branch
- Date range

Administrators can view all branches.
Employees can only view their assigned branch.
"""

from decimal import Decimal
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.extensions import db

from app.models import (
    Sale,
    SaleItem,
    Refund,
    RefundItem,
    Expense,
    Branch
)

from app.permissions.auth import (
    role_required,
    get_current_role,
    get_current_branch_id
)


report_bp = Blueprint(
    "reports",
    __name__,
    url_prefix="/api/reports"
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def parse_date(value):
    """Convert YYYY-MM-DD to a Python date."""

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return None


def money(value):
    """Convert Decimal/database values to float."""

    if value is None:
        return 0.0

    return float(
        Decimal(str(value))
    )


def get_date_range():
    """
    Read date_from and date_to from the request.

    Both dates are required for the financial report.
    """

    date_from_value = request.args.get(
        "date_from"
    )

    date_to_value = request.args.get(
        "date_to"
    )

    if not date_from_value or not date_to_value:
        return None, None, (
            "date_from and date_to are required "
            "in YYYY-MM-DD format."
        )

    date_from = parse_date(
        date_from_value
    )

    date_to = parse_date(
        date_to_value
    )

    if not date_from:
        return None, None, (
            "date_from must use YYYY-MM-DD format."
        )

    if not date_to:
        return None, None, (
            "date_to must use YYYY-MM-DD format."
        )

    if date_to < date_from:
        return None, None, (
            "date_to cannot be earlier than date_from."
        )

    return date_from, date_to, None


def get_branch_id():
    """
    Determine which branch the report should use.

    Employees are restricted to their JWT branch.

    Admins may optionally provide branch_id.
    """

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    requested_branch_id = request.args.get(
        "branch_id"
    )

    if role == "employee":

        return current_branch_id

    return requested_branch_id


def validate_branch(branch_id):
    """Check that a requested branch exists."""

    if not branch_id:
        return None

    return db.session.get(
        Branch,
        branch_id
    )


# ---------------------------------------------------------
# Financial report
# ---------------------------------------------------------

@report_bp.get("/financial")
@role_required("admin", "employee")
def financial_report():

    # -----------------------------------------------------
    # Dates
    # -----------------------------------------------------

    date_from, date_to, error = get_date_range()

    if error:
        return jsonify({
            "success": False,
            "message": error
        }), 400

    # -----------------------------------------------------
    # Branch
    # -----------------------------------------------------

    branch_id = get_branch_id()

    if get_current_role() == "employee" and not branch_id:
        return jsonify({
            "success": False,
            "message": (
                "Employee is not assigned to a branch."
            )
        }), 400

    branch = validate_branch(
        branch_id
    )

    if branch_id and not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    # -----------------------------------------------------
    # Date/time boundaries
    # -----------------------------------------------------

    start_datetime = datetime.combine(
        date_from,
        datetime.min.time()
    )

    end_datetime = datetime.combine(
        date_to + timedelta(days=1),
        datetime.min.time()
    )

    # -----------------------------------------------------
    # SALES
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
    # REFUNDS
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

                cost_price = Decimal(
                    str(sale_item.cost_price)
                )

                refunded_cogs += (
                    quantity * cost_price
                )

    # -----------------------------------------------------
    # NET SALES
    # -----------------------------------------------------

    net_sales = (
        gross_sales
        - total_refunds
    )

    # -----------------------------------------------------
    # NET COGS AFTER REFUNDS
    # -----------------------------------------------------

    net_cogs = (
        total_cogs
        - refunded_cogs
    )

    # Prevent accidental negative COGS.
    if net_cogs < 0:
        net_cogs = Decimal("0")

    # -----------------------------------------------------
    # GROSS PROFIT
    # -----------------------------------------------------

    gross_profit = (
        net_sales
        - net_cogs
    )

    # -----------------------------------------------------
    # EXPENSES
    # -----------------------------------------------------

    expenses_query = Expense.query.filter(
        Expense.expense_date >= date_from,
        Expense.expense_date <= date_to
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
    # NET PROFIT
    # -----------------------------------------------------

    net_profit = (
        gross_profit
        - total_expenses
    )

    # -----------------------------------------------------
    # TITHE
    # -----------------------------------------------------

    if net_profit > 0:

        tithe = (
            net_profit
            * Decimal("0.10")
        )

    else:

        tithe = Decimal("0")

    # -----------------------------------------------------
    # Branch information
    # -----------------------------------------------------

    branch_data = None

    if branch:

        branch_data = {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
            "code": branch.code
        }

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return jsonify({
        "success": True,

        "report": {

            "date_from": (
                date_from.isoformat()
            ),

            "date_to": (
                date_to.isoformat()
            ),

            "branch": branch_data,

            "gross_sales": money(
                gross_sales
            ),

            "refunds": money(
                total_refunds
            ),

            "net_sales": money(
                net_sales
            ),

            "gross_cogs": money(
                total_cogs
            ),

            "refunded_cogs": money(
                refunded_cogs
            ),

            "net_cogs": money(
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