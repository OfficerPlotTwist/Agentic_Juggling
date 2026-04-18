from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from match.store import MatchConfig, NodeAssignment, PromptEntry

router = APIRouter(prefix="/match", tags=["admin"])


class PromptEntryIn(BaseModel):
    delay: float
    prompt: str


class NodeAssignmentIn(BaseModel):
    node_id: str
    agentname: str
    schedule: list[PromptEntryIn]


class CreateMatchRequest(BaseModel):
    duration_s: float
    nodes: list[NodeAssignmentIn]
    token_weight: float = 0.01
    idle_penalty: float = 1.0


@router.post("", status_code=201)
async def create_match(body: CreateMatchRequest, request: Request):
    manager = request.app.state.match_manager
    config = MatchConfig(
        duration_s=body.duration_s,
        token_weight=body.token_weight,
        idle_penalty=body.idle_penalty,
        nodes=[
            NodeAssignment(
                node_id=na.node_id,
                agentname=na.agentname,
                schedule=[PromptEntry(p.delay, p.prompt) for p in na.schedule],
            )
            for na in body.nodes
        ],
    )
    record = await manager.create(config)
    return {"match_id": record.match_id, "state": record.state.value}


@router.get("/{match_id}")
async def get_match(match_id: str, request: Request):
    manager = request.app.state.match_manager
    try:
        record = await manager.get(match_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "match_id": record.match_id,
        "state": record.state.value,
        "duration_s": record.duration_s,
        "t0": record.t0,
        "token_weight": record.token_weight,
        "idle_penalty": record.idle_penalty,
    }


@router.get("")
async def list_matches(request: Request):
    store = request.app.state.match_store
    records = await store.list_all()
    return [
        {"match_id": r.match_id, "state": r.state.value, "created_at": r.created_at}
        for r in records
    ]


@router.post("/{match_id}/start")
async def start_match(match_id: str, request: Request):
    manager = request.app.state.match_manager
    try:
        await manager.start(match_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"match_id": match_id, "state": "RUNNING"}


@router.post("/{match_id}/stop")
async def stop_match(match_id: str, request: Request):
    manager = request.app.state.match_manager
    try:
        await manager.stop(match_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"match_id": match_id, "state": "FINISHED"}
