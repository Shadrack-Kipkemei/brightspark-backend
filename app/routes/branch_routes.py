"""
Branch management routes for BrightSpark.

Branches are created during the initial system setup.
Administrators can view and activate/deactivate branches.

Employees cannot manage branches.
"""

from flask import Blueprint, jsonify
from app.extensions import db
from app.models import Branch
from app.permissions.auth import role_required


branches_bp = Blueprint(
    "branches",
    __name__,
    url_prefix="/api/branches"
)


def serialize_branch(branch):
    """
    Convert a Branch model into a safe JSON response.
    """

    return {
        "id": branch.id,
        "name": branch.name,
        "location": branch.location,
        "code": branch.code,
        "is_active": branch.is_active,
        "created_at": (
            branch.created_at.isoformat()
            if branch.created_at
            else None
        ),
        "updated_at": (
            branch.updated_at.isoformat()
            if branch.updated_at
            else None
        ),
    }


# =========================================================
# GET ALL BRANCHES
# =========================================================

@branches_bp.get("")
@role_required("admin", "employee")
def get_branches():
    """
    Return all branches.

    Employees can view branches, but cannot modify them.
    """

    branches = Branch.query.order_by(Branch.name.asc()).all()

    return jsonify({
        "success": True,
        "count": len(branches),
        "branches": [
            serialize_branch(branch)
            for branch in branches
        ]
    }), 200


# =========================================================
# GET SINGLE BRANCH
# =========================================================

@branches_bp.get("/<string:branch_id>")
@role_required("admin", "employee")
def get_branch(branch_id):
    """
    Return one branch.
    """

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    return jsonify({
        "success": True,
        "branch": serialize_branch(branch)
    }), 200


# =========================================================
# ACTIVATE BRANCH
# =========================================================

@branches_bp.patch("/<string:branch_id>/activate")
@role_required("admin")
def activate_branch(branch_id):
    """
    Activate a branch.

    Only administrators can perform this action.
    """

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    if branch.is_active:
        return jsonify({
            "success": True,
            "message": "Branch is already active.",
            "branch": serialize_branch(branch)
        }), 200

    branch.is_active = True

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Branch activated successfully.",
        "branch": serialize_branch(branch)
    }), 200


# =========================================================
# DEACTIVATE BRANCH
# =========================================================

@branches_bp.patch("/<string:branch_id>/deactivate")
@role_required("admin")
def deactivate_branch(branch_id):
    """
    Deactivate a branch.

    We do not delete branches because historical sales,
    expenses, inventory and stock movements may reference them.
    """

    branch = db.session.get(Branch, branch_id)

    if not branch:
        return jsonify({
            "success": False,
            "message": "Branch not found."
        }), 404

    if not branch.is_active:
        return jsonify({
            "success": True,
            "message": "Branch is already inactive.",
            "branch": serialize_branch(branch)
        }), 200

    branch.is_active = False

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Branch deactivated successfully.",
        "branch": serialize_branch(branch)
    }), 200



# =========================================================
# PUBLIC ACTIVE BRANCHES
# =========================================================

@branches_bp.get("/public")
def get_public_branches():
    """
    Return active branches for the public storefront.

    No login is required.
    Only basic branch information is exposed.
    """

    branches = Branch.query.filter_by(
        is_active=True
    ).order_by(
        Branch.name.asc()
    ).all()

    return jsonify({
        "success": True,
        "count": len(branches),
        "branches": [
            {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
                "code": branch.code,
            }
            for branch in branches
        ]
    }), 200
