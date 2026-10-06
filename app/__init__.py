from flask import Flask, jsonify

from app.config import Config
from app.extensions import cors, db, jwt, migrate


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

    @app.get("/api/health")
    def health_check():
        return jsonify(
            {
                "success": True,
                "message": "BrightSpark backend is running",
            }
        )

    return app