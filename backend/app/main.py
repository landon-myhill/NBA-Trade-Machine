from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from app.routes import players, teams, trades

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIST),
        static_url_path="",
    )

    app.register_blueprint(teams.bp)
    app.register_blueprint(players.bp)
    app.register_blueprint(trades.bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    def index():
        if not FRONTEND_DIST.exists():
            return (
                "Frontend not built. Run `cd frontend && npm install && npm run build`.",
                503,
            )
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()
