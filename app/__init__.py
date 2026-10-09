from flask import Flask, jsonify

from app.config import Config
from app.extensions import cors, db, jwt, migrate
from app.routes.test_routes import test_bp

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