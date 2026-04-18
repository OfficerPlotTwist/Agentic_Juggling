from fastapi import FastAPI

from api.admin import router as admin_router
from api.leaderboard import router as leaderboard_router


def create_app(
    match_manager,
    match_store,
    scoring_engine,
    broadcaster,
) -> FastAPI:
    app = FastAPI(title="Agentic Juggling — Central Server")

    app.state.match_manager = match_manager
    app.state.match_store = match_store
    app.state.scoring_engine = scoring_engine
    app.state.broadcaster = broadcaster

    app.include_router(admin_router)
    app.include_router(leaderboard_router)

    return app
