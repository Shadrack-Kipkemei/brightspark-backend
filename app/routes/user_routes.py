"""
User and employee management routes.

Only administrators can manage users.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import User, Branch
from app.permissions.auth import role_required


users_bp = Blueprint(
    "users",
    __name__,
    url_prefix="/api/users"
)


def serialize_user(user):
    """
    Convert a User model into a safe JSON response.

    Never return password_hash.
    """

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "branch": (
            {
                "id": user.branch.id,
                "name": user.branch.name,
                "location": user.branch.location,
                "code": user.branch.code,
            }
            if user.branch
            else None
        ),
        "branch_id": user.branch_id,
        "is_active": user.is_active,
        "created_at": (
            user.created_at.isoformat()
            if user.created_at
            else None
        ),
        "updated_at": (
            user.updated_at.isoformat()
            if user.updated_at
            else None
        ),
    }


# =========================================================
# CREATE USER
# =========================================================

@users_bp.post("")
@role_required("admin")
def create_user():
    """
    Create a new administrator or employee.
    """

    data = request.get_json() or {}

    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "employee").strip().lower()
    branch_id = data.get("branch_id")

    # -----------------------------------------------------
    # Validate required fields
    # -----------------------------------------------------

    if not full_name:
        return jsonify({
            "success": False,
            "message": "Full name is required."
        }), 400

    if not email:
        return jsonify({
            "success": False,
            "message": "Email is required."
        }), 400

    if not password:
        return jsonify({
            "success": False,
            "message": "Password is required."
        }), 400

    if len(password) < 8:
        return jsonify({
            "success": False,
            "message": "Password must be at least 8 characters long."
        }), 400

    # -----------------------------------------------------
    # Validate role
    # -----------------------------------------------------

    allowed_roles = {"admin", "employee"}

    if role not in allowed_roles:
        return jsonify({
            "success": False,
            "message": "Role must be either admin or employee."
        }), 400

    # -----------------------------------------------------
    # Validate email uniqueness
    # -----------------------------------------------------

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        return jsonify({
            "success": False,
            "message": "A user with this email already exists."
        }), 409

    # -----------------------------------------------------
    # Validate branch
    # -----------------------------------------------------

    if role == "employee":
        if not branch_id:
            return jsonify({
                "success": False,
                "message": "Employees must be assigned to a branch."
            }), 400

        branch = db.session.get(Branch, branch_id)

        if not branch:
            return jsonify({
                "success": False,
                "message": "Selected branch does not exist."
            }), 404

        if not branch.is_active:
            return jsonify({
                "success": False,
                "message": "Selected branch is inactive."
            }), 400

    else:
        # Administrators are not required to belong to one branch.
        branch_id = None

    # -----------------------------------------------------
    # Create user
    # -----------------------------------------------------

    user = User(
        full_name=full_name,
        email=email,
        role=role,
        branch_id=branch_id,
        is_active=True
    )

    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "User created successfully.",
        "user": serialize_user(user)
    }), 201


# =========================================================
# GET ALL USERS
# =========================================================

@users_bp.get("")
@role_required("admin")
def get_users():
    """
    Return all users.

    Optional filters:

    ?role=employee
    ?role=admin
    ?branch_id=<branch_id>
    ?is_active=true
    ?is_active=false
    """

    query = User.query

    role = request.args.get("role")
    branch_id = request.args.get("branch_id")
    is_active = request.args.get("is_active")

    # -----------------------------------------------------
    # Role filter
    # -----------------------------------------------------

    if role:
        role = role.strip().lower()

        if role not in {"admin", "employee"}:
            return jsonify({
                "success": False,
                "message": "Invalid role filter."
            }), 400

        query = query.filter_by(role=role)

    # -----------------------------------------------------
    # Branch filter
    # -----------------------------------------------------

    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    # -----------------------------------------------------
    # Active status filter
    # -----------------------------------------------------

    if is_active is not None:
        if is_active.lower() not in {"true", "false"}:
            return jsonify({
                "success": False,
                "message": "is_active must be true or false."
            }), 400

        query = query.filter_by(
            is_active=is_active.lower() == "true"
        )

    users = query.order_by(User.created_at.desc()).all()

    return jsonify({
        "success": True,
        "count": len(users),
        "users": [
            serialize_user(user)
            for user in users
        ]
    }), 200


# =========================================================
# GET SINGLE USER
# =========================================================

@users_bp.get("/<string:user_id>")
@role_required("admin")
def get_user(user_id):
    """
    Return one user.
    """

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    return jsonify({
        "success": True,
        "user": serialize_user(user)
    }), 200


# =========================================================
# UPDATE USER
# =========================================================

@users_bp.put("/<string:user_id>")
@role_required("admin")
def update_user(user_id):
    """
    Update user information.

    Editable:
    - full_name
    - email
    - role
    - branch_id
    - password
    """

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    data = request.get_json() or {}

    current_admin_id = get_jwt_identity()

    # -----------------------------------------------------
    # Full name
    # -----------------------------------------------------

    if "full_name" in data:

        full_name = str(data["full_name"]).strip()

        if not full_name:
            return jsonify({
                "success": False,
                "message": "Full name cannot be empty."
            }), 400

        user.full_name = full_name

    # -----------------------------------------------------
    # Email
    # -----------------------------------------------------

    if "email" in data:

        email = str(data["email"]).strip().lower()

        if not email:
            return jsonify({
                "success": False,
                "message": "Email cannot be empty."
            }), 400

        existing_user = User.query.filter(
            User.email == email,
            User.id != user.id
        ).first()

        if existing_user:
            return jsonify({
                "success": False,
                "message": "A user with this email already exists."
            }), 409

        user.email = email

    # -----------------------------------------------------
    # Role
    # -----------------------------------------------------

    if "role" in data:

        role = str(data["role"]).strip().lower()

        if role not in {"admin", "employee"}:
            return jsonify({
                "success": False,
                "message": "Role must be either admin or employee."
            }), 400

        # Prevent current admin from changing their own
        # role away from admin.
        if user.id == current_admin_id and role != "admin":
            return jsonify({
                "success": False,
                "message": "You cannot remove administrator privileges from your own account."
            }), 400

        user.role = role

    # -----------------------------------------------------
    # Branch
    # -----------------------------------------------------

    if "branch_id" in data:

        branch_id = data.get("branch_id")

        if user.role == "employee":

            if not branch_id:
                return jsonify({
                    "success": False,
                    "message": "Employees must be assigned to a branch."
                }), 400

            branch = db.session.get(Branch, branch_id)

            if not branch:
                return jsonify({
                    "success": False,
                    "message": "Selected branch does not exist."
                }), 404

            if not branch.is_active:
                return jsonify({
                    "success": False,
                    "message": "Selected branch is inactive."
                }), 400

            user.branch_id = branch_id

        else:
            # Admins can operate across branches.
            user.branch_id = None

    # -----------------------------------------------------
    # If role changed to admin, remove branch assignment
    # -----------------------------------------------------

    if user.role == "admin":
        user.branch_id = None

    # -----------------------------------------------------
    # Password
    # -----------------------------------------------------

    if "password" in data:

        password = data.get("password", "")

        if not password:
            return jsonify({
                "success": False,
                "message": "Password cannot be empty."
            }), 400

        if len(password) < 8:
            return jsonify({
                "success": False,
                "message": "Password must be at least 8 characters long."
            }), 400

        user.set_password(password)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "User updated successfully.",
        "user": serialize_user(user)
    }), 200


# =========================================================
# ACTIVATE USER
# =========================================================

@users_bp.patch("/<string:user_id>/activate")
@role_required("admin")
def activate_user(user_id):
    """
    Activate a user account.
    """

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    if user.is_active:
        return jsonify({
            "success": True,
            "message": "User is already active.",
            "user": serialize_user(user)
        }), 200

    user.is_active = True

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "User activated successfully.",
        "user": serialize_user(user)
    }), 200


# =========================================================
# DEACTIVATE USER
# =========================================================

@users_bp.patch("/<string:user_id>/deactivate")
@role_required("admin")
def deactivate_user(user_id):
    """
    Deactivate a user account.

    An administrator cannot deactivate their own account.
    """

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    current_admin_id = get_jwt_identity()

    if user.id == current_admin_id:
        return jsonify({
            "success": False,
            "message": "You cannot deactivate your own account."
        }), 400

    if not user.is_active:
        return jsonify({
            "success": True,
            "message": "User is already inactive.",
            "user": serialize_user(user)
        }), 200

    user.is_active = False

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "User deactivated successfully.",
        "user": serialize_user(user)
    }), 200