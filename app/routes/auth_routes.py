"""
Authentication routes for BrightSpark.

This module handles:
    - User login
    - Current authenticated user
    - Access token refresh
    - Logout placeholder

Passwords are verified using Werkzeug.

JWTs are generated using Flask-JWT-Extended.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from app.models import User


# ------------------------------------------------------------
# Authentication blueprint.
#
# All routes in this file will begin with:
#
# /api/auth
# ------------------------------------------------------------
auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


@auth_bp.post("/login")
def login():
    """
    Authenticate a user and return JWT tokens.

    Expected JSON:

    {
        "email": "admin@brightspark.co.ke",
        "password": "BrightSpark@2026"
    }
    """

    # --------------------------------------------------------
    # Get JSON data from the request.
    # --------------------------------------------------------
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "message": "Request body must contain JSON data."
        }), 400

    # --------------------------------------------------------
    # Extract and clean the email.
    # --------------------------------------------------------
    email = data.get("email", "").strip().lower()

    # --------------------------------------------------------
    # Extract password.
    # --------------------------------------------------------
    password = data.get("password", "")

    # --------------------------------------------------------
    # Validate required fields.
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # Find the user.
    #
    # We intentionally do not reveal whether the email exists.
    # This avoids giving attackers useful account information.
    # --------------------------------------------------------
    user = User.query.filter_by(
        email=email
    ).first()

    if not user or not user.check_password(password):
        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    # --------------------------------------------------------
    # Check whether the account is active.
    # --------------------------------------------------------
    if not user.is_active:
        return jsonify({
            "success": False,
            "message": "This account has been deactivated."
        }), 403

    # --------------------------------------------------------
    # Build JWT additional claims.
    #
    # These values will be available to protected routes.
    # --------------------------------------------------------
    claims = {
        "role": user.role,
        "branch_id": user.branch_id,
        "email": user.email,
    }

    # --------------------------------------------------------
    # Create short-lived access token.
    # --------------------------------------------------------
    access_token = create_access_token(
        identity=user.id,
        additional_claims=claims
    )

    # --------------------------------------------------------
    # Create long-lived refresh token.
    # --------------------------------------------------------
    refresh_token = create_refresh_token(
        identity=user.id,
        additional_claims=claims
    )

    # --------------------------------------------------------
    # Return authenticated user information and tokens.
    #
    # NEVER return password_hash.
    # --------------------------------------------------------
    return jsonify({
        "success": True,
        "message": "Login successful.",

        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "branch_id": user.branch_id,
            "is_active": user.is_active,
        },

        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    }), 200


@auth_bp.get("/me")
@jwt_required()
def current_user():
    """
    Return information about the currently authenticated user.

    The user ID comes from the JWT.
    """

    # --------------------------------------------------------
    # Get the authenticated user's ID from JWT.
    # --------------------------------------------------------
    user_id = get_jwt_identity()

    # --------------------------------------------------------
    # Find the user in PostgreSQL.
    # --------------------------------------------------------
    user = User.query.get(user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User account no longer exists."
        }), 404

    # --------------------------------------------------------
    # Make sure a deactivated user cannot continue using the API.
    # --------------------------------------------------------
    if not user.is_active:
        return jsonify({
            "success": False,
            "message": "This account has been deactivated."
        }), 403

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "branch_id": user.branch_id,
            "is_active": user.is_active,
        }
    }), 200


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    Create a new access token using a valid refresh token.
    """

    # --------------------------------------------------------
    # Get user ID from the refresh token.
    # --------------------------------------------------------
    user_id = get_jwt_identity()

    # --------------------------------------------------------
    # Confirm the user still exists.
    # --------------------------------------------------------
    user = User.query.get(user_id)

    if not user:
        return jsonify({
            "success": False,
            "message": "User account no longer exists."
        }), 404

    # --------------------------------------------------------
    # A deactivated user should not receive new access tokens.
    # --------------------------------------------------------
    if not user.is_active:
        return jsonify({
            "success": False,
            "message": "This account has been deactivated."
        }), 403

    # --------------------------------------------------------
    # Rebuild claims from the current database record.
    #
    # This is important because a user's role or branch may
    # have changed since the refresh token was originally issued.
    # --------------------------------------------------------
    claims = {
        "role": user.role,
        "branch_id": user.branch_id,
        "email": user.email,
    }

    # --------------------------------------------------------
    # Create a new access token.
    # --------------------------------------------------------
    access_token = create_access_token(
        identity=user.id,
        additional_claims=claims
    )

    return jsonify({
        "success": True,
        "access_token": access_token
    }), 200


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """
    Logout endpoint.

    JWTs are stateless, so this endpoint currently confirms that
    the token is valid.

    Later we can add a token blocklist/revocation system so that
    access tokens can be actively revoked.
    """

    return jsonify({
        "success": True,
        "message": "Logout successful."
    }), 200