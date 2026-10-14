"""
Expense management routes for BrightSpark.

This module handles:

- Creating expenses
- Viewing expenses
- Viewing a single expense
- Filtering expenses
- Deleting incorrect expenses

Employees can only create and view expenses
for their assigned branch.

Administrators can manage expenses across branches.
"""

from decimal import Decimal, InvalidOperation
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models import Expense, Branch, User

from app.permissions.auth import (
    role_required,
    get_current_role,
    get_current_branch_id
)


expense_bp = Blueprint(
    "expenses",
    __name__,
    url_prefix="/api/expenses"
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

ALLOWED_PAYMENT_METHODS = {
    "CASH",
    "MPESA"
}


ALLOWED_CATEGORIES = {
    "Rent",
    "Electricity",
    "Water",
    "Meals",
    "Internet",
    "Credit",
    "Transport",
    "Delivery",
    "Salaries/Wages",
    "Repairs & Maintenance",
    "Stationery",
    "Packaging",
    "Advertising/Marketing",
    "Bank/M-Pesa Charges",
    "Licenses/Permits",
    "Security",
    "Cleaning",
    "Other"
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def decimal_value(value):
    """Safely convert a value to Decimal."""

    try:
        return Decimal(str(value))

    except (
        InvalidOperation,
        TypeError,
        ValueError
    ):
        return None


def parse_date(value):
    """Convert YYYY-MM-DD into a date object."""

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return None


def validate_branch_access(branch_id):
    """
    Check whether the current user can access
    the requested branch.
    """

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    if role == "admin":
        return True

    if role == "employee":
        return current_branch_id == branch_id

    return False


def serialize_expense(expense):
    """Convert an Expense object into JSON."""

    return {
        "id": expense.id,
        "branch_id": expense.branch_id,
        "employee_id": expense.employee_id,
        "category": expense.category,
        "amount": float(expense.amount),
        "description": expense.description,
        "payment_method": expense.payment_method,
        "expense_date": (
            expense.expense_date.isoformat()
            if expense.expense_date
            else None
        ),
        "created_at": (
            expense.created_at.isoformat()
            if expense.created_at
            else None
        ),
        "updated_at": (
            expense.updated_at.isoformat()
            if expense.updated_at
            else None
        ),
        "branch": (
            {
                "id": expense.branch.id,
                "name": expense.branch.name,
                "location": expense.branch.location,
                "code": expense.branch.code
            }
            if expense.branch
            else None
        ),
        "employee": (
            {
                "id": expense.employee.id,
                "full_name": expense.employee.full_name,
                "email": expense.employee.email
            }
            if expense.employee
            else None
        )
    }


# ---------------------------------------------------------
# Create expense
# ---------------------------------------------------------

@expense_bp.post("")
@role_required("admin", "employee")
def create_expense():

    data = request.get_json() or {}

    category = str(
        data.get("category", "")
    ).strip()

    amount = decimal_value(
        data.get("amount")
    )

    description = str(
        data.get("description", "")
    ).strip()

    payment_method = str(
        data.get("payment_method", "")
    ).upper()

    expense_date_value = data.get(
        "expense_date"
    )

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # -----------------------------------------------------
    # Determine branch
    # -----------------------------------------------------

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = data.get(
            "branch_id"
        )

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    if not branch_id:
        return jsonify({
            "success": False,
            "message": "Branch ID is required."
        }), 400

    if not category:
        return jsonify({
            "success": False,
            "message": "Expense category is required."
        }), 400

    if category not in ALLOWED_CATEGORIES:
        return jsonify({
            "success": False,
            "message": (
                "Invalid expense category."
            ),
            "allowed_categories": sorted(
                ALLOWED_CATEGORIES
            )
        }), 400

    if amount is None or amount <= 0:
        return jsonify({
            "success": False,
            "message": (
                "Expense amount must be greater "
                "than zero."
            )
        }), 400

    if payment_method not in ALLOWED_PAYMENT_METHODS:
        return jsonify({
            "success": False,
            "message": (
                "Payment method must be CASH "
                "or MPESA."
            )
        }), 400

    expense_date = parse_date(
        expense_date_value
    )

    if not expense_date:
        return jsonify({
            "success": False,
            "message": (
                "Expense date is required and "
                "must use YYYY-MM-DD format."
            )
        }), 400

    if not validate_branch_access(branch_id):
        return jsonify({
            "success": False,
            "message": (
                "You do not have access to "
                "this branch."
            )
        }), 403

    # -----------------------------------------------------
    # Verify branch
    # -----------------------------------------------------

    branch = db.session.get(
        Branch,
        branch_id
    )

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    if not branch.is_active:
        return jsonify({
            "success": False,
            "message": (
                "Cannot record an expense "
                "for an inactive branch."
            )
        }), 400

    # -----------------------------------------------------
    # Current user
    # -----------------------------------------------------

    user_id = get_jwt_identity()

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    # -----------------------------------------------------
    # Create expense
    # -----------------------------------------------------

    expense = Expense(
        branch_id=branch.id,
        employee_id=user.id,
        category=category,
        amount=amount,
        description=description or None,
        payment_method=payment_method,
        expense_date=expense_date
    )

    db.session.add(expense)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Expense recorded successfully.",
        "expense": serialize_expense(expense)
    }), 201


# ---------------------------------------------------------
# Get expenses
# ---------------------------------------------------------

@expense_bp.get("")
@role_required("admin", "employee")
def get_expenses():

    requested_branch_id = request.args.get(
        "branch_id"
    )

    category = request.args.get(
        "category"
    )

    payment_method = request.args.get(
        "payment_method"
    )

    date_from_value = request.args.get(
        "date_from"
    )

    date_to_value = request.args.get(
        "date_to"
    )

    search = request.args.get(
        "search",
        ""
    ).strip()

    role = get_current_role()
    current_branch_id = get_current_branch_id()

    # -----------------------------------------------------
    # Branch access
    # -----------------------------------------------------

    if role == "employee":

        branch_id = current_branch_id

    else:

        branch_id = requested_branch_id

    if role == "employee" and not branch_id:
        return jsonify({
            "success": False,
            "message": (
                "Employee is not assigned "
                "to a branch."
            )
        }), 400

    # -----------------------------------------------------
    # Build query
    # -----------------------------------------------------

    query = Expense.query

    if branch_id:

        query = query.filter(
            Expense.branch_id == branch_id
        )

    if category:

        query = query.filter(
            Expense.category == category
        )

    if payment_method:

        query = query.filter(
            Expense.payment_method ==
            payment_method.upper()
        )

    # -----------------------------------------------------
    # Date filters
    # -----------------------------------------------------

    if date_from_value:

        date_from = parse_date(
            date_from_value
        )

        if not date_from:
            return jsonify({
                "success": False,
                "message": (
                    "date_from must use "
                    "YYYY-MM-DD format."
                )
            }), 400

        query = query.filter(
            Expense.expense_date >= date_from
        )

    if date_to_value:

        date_to = parse_date(
            date_to_value
        )

        if not date_to:
            return jsonify({
                "success": False,
                "message": (
                    "date_to must use "
                    "YYYY-MM-DD format."
                )
            }), 400

        query = query.filter(
            Expense.expense_date <= date_to
        )

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    if search:

        search_pattern = (
            f"%{search}%"
        )

        query = query.join(
            User,
            Expense.employee_id == User.id
        ).filter(
            or_(
                Expense.description.ilike(
                    search_pattern
                ),
                Expense.category.ilike(
                    search_pattern
                ),
                User.full_name.ilike(
                    search_pattern
                ),
                User.email.ilike(
                    search_pattern
                )
            )
        )

    expenses = query.order_by(
        Expense.expense_date.desc(),
        Expense.created_at.desc()
    ).all()

    total_amount = Decimal("0")

    for expense in expenses:

        total_amount += Decimal(
            str(expense.amount)
        )

    return jsonify({
        "success": True,
        "count": len(expenses),
        "total_amount": float(total_amount),
        "expenses": [
            serialize_expense(expense)
            for expense in expenses
        ]
    }), 200


# ---------------------------------------------------------
# Get one expense
# ---------------------------------------------------------

@expense_bp.get("/<string:expense_id>")
@role_required("admin", "employee")
def get_expense(expense_id):

    expense = db.session.get(
        Expense,
        expense_id
    )

    if not expense:
        return jsonify({
            "success": False,
            "message": "Expense not found."
        }), 404

    if not validate_branch_access(
        expense.branch_id
    ):
        return jsonify({
            "success": False,
            "message": (
                "You do not have access "
                "to this expense."
            )
        }), 403

    return jsonify({
        "success": True,
        "expense": serialize_expense(
            expense
        )
    }), 200


# ---------------------------------------------------------
# Delete expense
# ---------------------------------------------------------

@expense_bp.delete("/<string:expense_id>")
@role_required("admin", "employee")
def delete_expense(expense_id):

    expense = db.session.get(
        Expense,
        expense_id
    )

    if not expense:
        return jsonify({
            "success": False,
            "message": "Expense not found."
        }), 404

    if not validate_branch_access(
        expense.branch_id
    ):
        return jsonify({
            "success": False,
            "message": (
                "You do not have permission "
                "to delete this expense."
            )
        }), 403

    user_id = get_jwt_identity()

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return jsonify({
            "success": False,
            "message": "Current user not found."
        }), 401

    # -----------------------------------------------------
    # Delete
    # -----------------------------------------------------

    db.session.delete(expense)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Expense deleted successfully.",
        "expense_id": expense_id
    }), 200