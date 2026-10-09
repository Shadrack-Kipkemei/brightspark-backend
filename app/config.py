"""
Application configuration for BrightSpark.

Environment-specific secrets and database credentials are loaded
from the .env file during development and from deployment
environment variables in production.
"""

import os

from dotenv import load_dotenv


# Load environment variables from .env during local development.
load_dotenv()


class Config:
    """
    Base Flask configuration.
    """

    # --------------------------------------------------------
    # Flask application secret.
    # Used by Flask for application-level security features.
    # --------------------------------------------------------
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "change-this-secret-key"
    )

    # --------------------------------------------------------
    # Secret used by Flask-JWT-Extended to sign JWT tokens.
    # --------------------------------------------------------
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        "change-this-jwt-secret-key"
    )

    # --------------------------------------------------------
    # PostgreSQL database connection.
    # --------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/brightspark"
    )

    # Disable SQLAlchemy modification tracking because it is
    # unnecessary for our application and consumes resources.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --------------------------------------------------------
    # JWT configuration
    # --------------------------------------------------------

    # Access tokens are intentionally short-lived.
    # Users will use the refresh token to obtain a new access token.
    JWT_ACCESS_TOKEN_EXPIRES = 15 * 60

    # Refresh tokens live considerably longer.
    JWT_REFRESH_TOKEN_EXPIRES = 30 * 24 * 60 * 60

    # We are currently returning tokens as JSON because the
    # Next.js frontend will consume the REST API directly.
    JWT_TOKEN_LOCATION = ["headers"]

    # JWTs will normally be sent using:
    #
    # Authorization: Bearer <access_token>
    #
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"