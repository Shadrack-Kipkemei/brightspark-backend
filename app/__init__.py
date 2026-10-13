from flask import Flask, jsonify

from app.config import Config
from app.extensions import cors, db, jwt, migrate
from app.routes.auth_routes import auth_bp
from app.routes.user_routes import users_bp
from app.routes.test_routes import test_bp
from app.routes.branch_routes import branches_bp
from app.routes.product_routes import products_bp
from app.routes.inventory_routes import inventory_bp
from app.routes.transfer_routes import transfer_bp

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
    app.register_blueprint(transfer_bp)

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

    return app