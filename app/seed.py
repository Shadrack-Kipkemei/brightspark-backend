"""
BrightSpark database seed script.

This script creates the initial business data required by the application:

1. Roysambu branch
2. Rangau branch
3. Initial system administrator

The script is designed to be safe to run multiple times.
Existing records will not be duplicated.
"""

import os

from app import create_app
from app.extensions import db
from app.models import Branch, User


# ------------------------------------------------------------
# Create the Flask application.
# ------------------------------------------------------------
app = create_app()


def seed_branches():
    """
    Create the two BrightSpark branches if they do not already exist.

    Returns:
        tuple:
            (roysambu_branch, rangau_branch)
    """

    # --------------------------------------------------------
    # Find the Roysambu branch.
    # If it doesn't exist, create it.
    # --------------------------------------------------------
    roysambu = Branch.query.filter_by(
        code="ROYSAMBU"
    ).first()

    if not roysambu:
        roysambu = Branch(
            name="Roysambu Branch",
            location="Lumumba Drive",
            code="ROYSAMBU",
            is_active=True
        )

        db.session.add(roysambu)

        print("Created Roysambu branch.")
    else:
        print("Roysambu branch already exists.")

    # --------------------------------------------------------
    # Find the Rangau branch.
    # If it doesn't exist, create it.
    # --------------------------------------------------------
    rangau = Branch.query.filter_by(
        code="RANGAU"
    ).first()

    if not rangau:
        rangau = Branch(
            name="Rangau Branch",
            location="Rangau Shopping Center",
            code="RANGAU",
            is_active=True
        )

        db.session.add(rangau)

        print("Created Rangau branch.")
    else:
        print("Rangau branch already exists.")

    # --------------------------------------------------------
    # Save the branches before returning them.
    # This ensures their IDs are available.
    # --------------------------------------------------------
    db.session.commit()

    return roysambu, rangau


def seed_admin():
    """
    Create the initial system administrator.

    The administrator is not assigned to a specific branch.
    A NULL branch_id means the administrator has access to
    both/all branches, subject to authorization rules.
    """

    # --------------------------------------------------------
    # Read administrator details from environment variables.
    # --------------------------------------------------------
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_name = os.getenv("ADMIN_NAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    # --------------------------------------------------------
    # Make sure all required values are configured.
    # --------------------------------------------------------
    if not admin_email:
        raise ValueError(
            "ADMIN_EMAIL is missing from the .env file."
        )

    if not admin_name:
        raise ValueError(
            "ADMIN_NAME is missing from the .env file."
        )

    if not admin_password:
        raise ValueError(
            "ADMIN_PASSWORD is missing from the .env file."
        )

    # --------------------------------------------------------
    # Look for an existing administrator.
    # --------------------------------------------------------
    admin = User.query.filter_by(
        email=admin_email.lower()
    ).first()

    if admin:
        print(
            f"Administrator {admin_email} already exists."
        )

        return admin

    # --------------------------------------------------------
    # Create the administrator.
    #
    # branch_id remains NULL because a system administrator
    # can manage both BrightSpark branches.
    # --------------------------------------------------------
    admin = User(
        full_name=admin_name,
        email=admin_email.lower(),
        role="admin",
        branch_id=None,
        is_active=True
    )

    # --------------------------------------------------------
    # Hash the password using Werkzeug.
    #
    # We NEVER store the actual password in PostgreSQL.
    # --------------------------------------------------------
    admin.set_password(admin_password)

    db.session.add(admin)

    db.session.commit()

    print(
        f"Created system administrator: {admin_email}"
    )

    return admin


def seed_database():
    """
    Run all database seed operations.
    """

    print("")
    print("=" * 60)
    print("BrightSpark Database Seeding")
    print("=" * 60)
    print("")

    # --------------------------------------------------------
    # Create branches.
    # --------------------------------------------------------
    seed_branches()

    # --------------------------------------------------------
    # Create initial administrator.
    # --------------------------------------------------------
    seed_admin()

    print("")
    print("=" * 60)
    print("Database seeding completed successfully.")
    print("=" * 60)
    print("")


if __name__ == "__main__":

    # --------------------------------------------------------
    # Flask application context is required because SQLAlchemy
    # needs access to the Flask application configuration.
    # --------------------------------------------------------
    with app.app_context():
        seed_database()