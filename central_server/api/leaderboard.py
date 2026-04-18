import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard/{match_id}")
async def get_leaderboard(match_id: str, request: Request):
    store = request.app.state.match_store
    scoring = request.app.state.scoring_engine
    record = await store.get(match_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    board = await scoring.compute(match_id, record.token_weight, record.idle_penalty)
    return scoring.serialize(board)


@router.websocket("/ws/leaderboard/{match_id}")
async def leaderboard_ws(match_id: str, ws: WebSocket, request: Request):
    broadcaster = request.app.state.broadcaster
    store = request.app.state.match_store

    record = await store.get(match_id)
    if record is None:
        await ws.close(code=4004)
        return

    await broadcaster.connect(match_id, ws)
    try:
        # Send current snapshot immediately on connect
        scoring = request.app.state.scoring_engine
        board = await scoring.compute(match_id, record.token_weight, record.idle_penalty)
        await ws.send_json(scoring.serialize(board))

        # Hold connection open; broadcast.py pushes updates as metrics arrive
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(match_id, ws)
        logger.info("WS client disconnected from match %s", match_id)
