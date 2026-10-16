from flask import Flask, jsonify, send_from_directory

from app.config import Config
from app.extensions import cors, db, jwt, migrate
from app.routes.auth_routes import auth_bp
from app.routes.user_routes import users_bp
from app.routes.test_routes import test_bp
from app.routes.branch_routes import branches_bp
from app.routes.product_routes import products_bp
from app.routes.inventory_routes import inventory_bp
from app.routes.transfer_routes import transfers_bp
from app.routes.sale_routes import sales_bp
from app.routes.refund_routes import refund_bp
from app.routes.expense_routes import expense_bp
from app.routes.report_routes import report_bp
from app.routes.dashboard_routes import dashboard_bp
from app.routes.notification_routes import notifications_bp

import app.models


def create_app(config_class=Config):
    app = Flask(__name__)

    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    cors.init_app(
        app,
        resources={
            r"/api/*": {
                "origins": "*"
            }
        }
    )

    # Register authentication routes.
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(branches_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(transfers_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(refund_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(notifications_bp)

    # Register temporary database testing routes.
    app.register_blueprint(test_bp)

    @app.get("/api/health")
    def health_check():
        return jsonify(
            {
                "success": True,
                "message": "BrightSpark backend is running",
            }
        )

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            filename
        )

    return app