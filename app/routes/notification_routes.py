from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Notification, User


notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/api/notifications"
)


def get_current_user():
    user_id = get_jwt_identity()

    if not user_id:
        return None

    return db.session.get(User, user_id)


def serialize_notification(notification):
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "branch_id": notification.branch_id,
        "product_id": notification.product_id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat()
        if notification.created_at
        else None,
        "read_at": notification.read_at.isoformat()
        if notification.read_at
        else None,
    }


@notifications_bp.get("")
@jwt_required()
def get_notifications():
    """
    Get notifications belonging to the logged-in user.
    """

    user = get_current_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "User account not found."
        }), 401

    unread_only = (
        request.args.get("unread_only", "false").lower()
        == "true"
    )

    limit = request.args.get(
        "limit",
        20,
        type=int
    )

    limit = min(max(limit, 1), 100)

    query = Notification.query.filter_by(
        user_id=user.id
    )

    if unread_only:
        query = query.filter_by(
            is_read=False
        )

    notifications = (
        query
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    unread_count = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()

    return jsonify({
        "success": True,
        "unread_count": unread_count,
        "count": len(notifications),
        "notifications": [
            serialize_notification(notification)
            for notification in notifications
        ]
    })


@notifications_bp.get("/unread-count")
@jwt_required()
def unread_count():
    """
    Return the number of unread notifications.
    """

    user = get_current_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "User account not found."
        }), 401

    count = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()

    return jsonify({
        "success": True,
        "unread_count": count
    })


@notifications_bp.patch("/<notification_id>/read")
@jwt_required()
def mark_notification_read(notification_id):
    """
    Mark one notification as read.
    """

    user = get_current_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "User account not found."
        }), 401

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()

    if not notification:
        return jsonify({
            "success": False,
            "message": "Notification not found."
        }), 404

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()

        db.session.commit()

    return jsonify({
        "success": True,
        "message": "Notification marked as read.",
        "notification": serialize_notification(notification)
    })


@notifications_bp.patch("/read-all")
@jwt_required()
def mark_all_notifications_read():
    """
    Mark all notifications belonging to the
    logged-in user as read.
    """

    user = get_current_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "User account not found."
        }), 401

    notifications = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).all()

    now = datetime.utcnow()

    for notification in notifications:
        notification.is_read = True
        notification.read_at = now

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "All notifications marked as read.",
        "updated_count": len(notifications)
    })