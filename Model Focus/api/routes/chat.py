"""Interactive chat/test endpoint — generates with the currently-loaded model+adapter,
optionally grounded with RAG (inference.assistant.Assistant handles the orchestration).
Scoped to one project: the adapter list, base model and RAG index it draws from
all belong to that project alone."""

from __future__ import annotations

from pathlib import Path
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from api.enterprise import actor_from_request, store

from api.model_manager import manager
from api.paths import project_dir
from api.schemas import ChatRequest, ChatResponse
from inference.assistant import Assistant

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/adapters")
def list_adapters(project: Path = Depends(project_dir)):
    return {"adapters": manager.available_adapters(project)}


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request, project: Path = Depends(project_dir)):
    if body.adapter is not None and body.adapter not in manager.available_adapters(project):
        raise HTTPException(400, "Adapter absent de ce projet")
    assistant = Assistant(project_dir=project, adapter=body.adapter, system_prompt=body.system_prompt)
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    execution_id = store.start_execution(project.name, actor_from_request(request).id,
        meta.get("inference_model") or meta["base_model"], body.adapter, body.rag, len(body.message))
    started = time.perf_counter()
    try:
        result = assistant.run(body.message, rag=body.rag, max_new_tokens=body.max_new_tokens,
                               history=[turn.model_dump() for turn in body.history], user_context=body.user_context)
    except ValueError as exc:
        store.fail_execution(execution_id, "runtime_error", (time.perf_counter() - started) * 1000)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        store.fail_execution(execution_id, "internal_error", (time.perf_counter() - started) * 1000)
        raise
    store.finish_execution(execution_id, len(result.response), result.rag_used, result.rag_chunks,
                           (time.perf_counter() - started) * 1000)
    return ChatResponse(response=result.response, adapter=body.adapter, rag_used=result.rag_used,
                        rag_chunks=result.rag_chunks, execution_id=execution_id)


@router.post("/stream")
def chat_stream(body: ChatRequest, request: Request, project: Path = Depends(project_dir)):
    if body.adapter is not None and body.adapter not in manager.available_adapters(project):
        raise HTTPException(400, "Adapter absent de ce projet")
    assistant = Assistant(project_dir=project, adapter=body.adapter, system_prompt=body.system_prompt)
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    execution_id = store.start_execution(project.name, actor_from_request(request).id,
        meta.get("inference_model") or meta["base_model"], body.adapter, body.rag, len(body.message))
    started = time.perf_counter()
    try:
        iterator, rag_used, rag_chunks = assistant.stream(
            body.message, rag=body.rag, max_new_tokens=body.max_new_tokens,
            history=[turn.model_dump() for turn in body.history], user_context=body.user_context,
        )
    except ValueError as exc:
        store.fail_execution(execution_id, "runtime_error", (time.perf_counter() - started) * 1000)
        raise HTTPException(400, str(exc)) from exc

    def events():
        response_parts: list[str] = []
        first_token = True
        try:
            yield _sse("metadata", {"execution_id": execution_id, "adapter": body.adapter,
                                    "rag_used": rag_used, "rag_chunks": rag_chunks})
            if rag_used:
                store.trace_event(execution_id, "rag.completed", {"documents": rag_chunks})
            for chunk in iterator:
                if first_token:
                    store.trace_event(execution_id, "generation.first_token", {
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
                    first_token = False
                response_parts.append(chunk)
                yield _sse("token", {"text": chunk})
            response = "".join(response_parts).strip()
            duration = (time.perf_counter() - started) * 1000
            store.finish_execution(execution_id, len(response), rag_used, rag_chunks, duration)
            yield _sse("done", {"execution_id": execution_id, "response": response,
                                "duration_ms": round(duration, 2)})
        except ValueError as exc:
            store.fail_execution(execution_id, "runtime_error", (time.perf_counter() - started) * 1000)
            yield _sse("error", {"detail": str(exc)})
        except Exception:
            store.fail_execution(execution_id, "internal_error", (time.perf_counter() - started) * 1000)
            yield _sse("error", {"detail": "La génération a échoué"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
