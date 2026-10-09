"""
Temporary database testing routes.

These routes are only for confirming that Flask can read
data from PostgreSQL.

We will remove/replace these with proper API endpoints
as the backend develops.
"""

from flask import Blueprint, jsonify

from app.models import Branch, User


test_bp = Blueprint(
    "test",
    __name__,
    url_prefix="/api/test"
)


@test_bp.get("/database")
def test_database():
    """
    Return basic information from the PostgreSQL database.

    This allows us to confirm that:
    - Flask is connected to PostgreSQL.
    - Branches were seeded.
    - The administrator exists.
    """

    branches = Branch.query.all()

    admin = User.query.filter_by(
        role="admin"
    ).first()

    return jsonify({
        "success": True,

        "database": {
            "branches_count": len(branches),
            "admin_exists": admin is not None
        },

        "branches": [
            {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
                "code": branch.code
            }
            for branch in branches
        ]
    })