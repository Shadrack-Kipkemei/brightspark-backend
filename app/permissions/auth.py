"""
Authorization helpers for BrightSpark.

These functions help protected API endpoints determine:

1. Whether a user is authenticated.
2. Whether the user has a required role.
3. Which branch the user belongs to.

The actual business rules will be enforced by the backend,
not by the frontend.
"""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.models import User


def role_required(*allowed_roles):
    """
    Require authentication and one of the specified roles.

    Example:

        @role_required("admin")

    or:

        @role_required("admin", "employee")
    """

    def decorator(function):

        @wraps(function)
        @jwt_required()
        def wrapper(*args, **kwargs):

            # ------------------------------------------------
            # Read claims from the authenticated JWT.
            # ------------------------------------------------
            claims = get_jwt()

            role = claims.get("role")

            # ------------------------------------------------
            # Check whether the user's role is allowed.
            # ------------------------------------------------
            if role not in allowed_roles:
                return jsonify({
                    "success": False,
                    "message": "You do not have permission to perform this action."
                }), 403

            # ------------------------------------------------
            # Make sure the user account still exists and is active.
            # ------------------------------------------------
            user_id = get_jwt_identity()

            user = User.query.get(user_id)

            if not user:
                return jsonify({
                    "success": False,
                    "message": "User account no longer exists."
                }), 401

            if not user.is_active:
                return jsonify({
                    "success": False,
                    "message": "Your account has been deactivated."
                }), 403

            return function(*args, **kwargs)

        return wrapper

    return decorator


def get_current_user():
    """
    Return the currently authenticated User object.

    Returns:
        User object or None.
    """

    user_id = get_jwt_identity()

    if not user_id:
        return None

    return User.query.get(user_id)


def get_current_role():
    """
    Return the role from the current JWT.
    """

    claims = get_jwt()

    return claims.get("role")


def get_current_branch_id():
    """
    Return the branch ID from the current JWT.

    Admins have branch_id = None because they can work
    across all branches.
    """

    claims = get_jwt()

    return claims.get("branch_id")