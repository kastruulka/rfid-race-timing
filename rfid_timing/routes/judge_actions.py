from ..database import Database
from ..race_engine import RaceEngine
from .judge_action_decisions import register_judge_decision_routes
from .judge_action_runtime import register_judge_runtime_routes


def register_judge_action_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    require_engine=None,
):
    register_judge_decision_routes(
        app,
        db,
        engine=engine,
        require_engine=require_engine,
    )
    register_judge_runtime_routes(
        app,
        db,
        engine=engine,
        require_engine=require_engine,
    )
