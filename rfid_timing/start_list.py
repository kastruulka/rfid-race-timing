from flask import render_template

from .database import Database
from .race_engine import RaceEngine
from .routes.start_list_categories import register_start_list_category_routes
from .routes.start_list_riders import register_start_list_rider_routes


def register_start_list(app, db: Database, engine: RaceEngine = None):
    @app.route("/start-list")
    def start_list_page():
        return render_template("start_list.html")

    register_start_list_category_routes(app, db)
    register_start_list_rider_routes(app, db, engine=engine)
