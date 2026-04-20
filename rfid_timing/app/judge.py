from flask import render_template

from ..database.database import Database
from ..routes.judge.judge_actions import register_judge_action_routes
from ..routes.judge.judge_protocol import register_judge_protocol_routes
from .race_engine import RaceEngine
from ..http.request_helpers import make_require_engine
from ..integrations.start_protocol_worker import get_start_protocol_worker


def register_judge(app, db: Database, engine: RaceEngine = None):
    require_engine = make_require_engine(engine)
    scheduler = get_start_protocol_worker(db, engine) if engine else None

    @app.route("/judge")
    def judge_page():
        return render_template("judge.html")

    register_judge_protocol_routes(
        app,
        db,
        engine=engine,
        scheduler=scheduler,
        require_engine=require_engine,
    )
    register_judge_action_routes(
        app,
        db,
        engine=engine,
        require_engine=require_engine,
    )
