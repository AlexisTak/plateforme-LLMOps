"""Interactive chat/test endpoint — generates with the currently-loaded model+adapter,
optionally grounded with RAG (inference.assistant.Assistant handles the orchestration).
Scoped to one project: the adapter list, base model and RAG index it draws from
all belong to that project alone."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.model_manager import manager
from api.paths import project_dir
from api.schemas import ChatRequest, ChatResponse
from inference.assistant import Assistant

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


@router.get("/adapters")
def list_adapters(project: Path = Depends(project_dir)):
    return {"adapters": manager.available_adapters(project)}


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, project: Path = Depends(project_dir)):
    if body.adapter is not None and body.adapter not in manager.available_adapters(project):
        raise HTTPException(400, "Adapter absent de ce projet")
    assistant = Assistant(project_dir=project, adapter=body.adapter, system_prompt=body.system_prompt)
    try:
        result = assistant.run(body.message, rag=body.rag, max_new_tokens=body.max_new_tokens,
                               history=[turn.model_dump() for turn in body.history], user_context=body.user_context)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ChatResponse(response=result.response, adapter=body.adapter, rag_used=result.rag_used, rag_chunks=result.rag_chunks)
