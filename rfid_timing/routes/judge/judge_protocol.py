from ...database.database import Database
from ...app.race_engine import RaceEngine
from .judge_protocol_mutations import register_judge_protocol_mutation_routes
from .judge_protocol_read import register_judge_protocol_read_routes


def register_judge_protocol_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    scheduler=None,
    require_engine=None,
):
    register_judge_protocol_read_routes(app, db)
    register_judge_protocol_mutation_routes(
        app,
        db,
        engine=engine,
        scheduler=scheduler,
        require_engine=require_engine,
    )
