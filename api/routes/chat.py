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
from api.enterprise import Actor, actor_from_request, store

from api.model_manager import manager
from api.paths import project_dir
from api.routes.enterprise import enforce_agent_budget
from api.schemas import (ChatRequest, ChatResponse, ConversationCreate, ConversationDetail,
                          ConversationMessage, ConversationRename, ConversationSummary)
from inference.assistant import Assistant

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _title_from_message(message: str) -> str:
    title = " ".join(message.split())[:60]
    return title if len(message) <= 60 else title.rstrip() + "…"


def _resolve_conversation(body: ChatRequest, project_id: str, actor_id: str) -> str | None:
    """Validates the conversation the caller wants to append to (404 if it isn't
    theirs) and returns its id. A *new* conversation (persist=true without an id)
    is deliberately not created here but by _persist_exchange, once the model has
    actually answered — a failed first message must not leave an empty orphan
    conversation behind (F05 — durable history is opt-in, default behaviour for
    existing callers stays unchanged)."""
    if body.conversation_id is not None:
        if not store.conversation(project_id, actor_id, body.conversation_id):
            raise HTTPException(404, "Conversation introuvable")
        return body.conversation_id
    return None


def _persist_exchange(body: ChatRequest, project_id: str, actor_id: str, conversation_id: str | None,
                      response: str, rag_chunks: list[str]) -> str | None:
    """Stores the user turn + the assistant turn together, after a successful
    generation only (both /chat and /chat/stream), creating the conversation on
    the spot when the caller asked for a new one."""
    if conversation_id is None:
        if not body.persist:
            return None
        conversation_id = store.create_conversation(project_id, actor_id, _title_from_message(body.message))
    store.add_message(project_id, conversation_id, "user", body.message)
    store.add_message(project_id, conversation_id, "assistant", response, rag_chunks)
    return conversation_id


def _chat_actor(request: Request, project: Path) -> Actor:
    """Every chat route: authenticate first, then require project membership (same
    gap as the one closed on /rag/* in F07), and only then look at budgets — an
    unauthenticated caller must get a 401, never a 429 that leaks the limits."""
    actor = actor_from_request(request)
    store.require_project_role(project.name, actor)
    return actor


@router.get("/adapters")
def list_adapters(request: Request, project: Path = Depends(project_dir)):
    _chat_actor(request, project)
    return {"adapters": manager.available_adapters(project)}


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(request: Request, project: Path = Depends(project_dir)):
    return store.list_conversations(project.name, _chat_actor(request, project).id)


@router.post("/conversations", response_model=ConversationSummary)
def create_conversation(body: ConversationCreate, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    conversation_id = store.create_conversation(project.name, actor.id, body.title)
    conversation = store.conversation(project.name, actor.id, conversation_id)
    return {**conversation, "message_count": 0}


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    conversation = store.conversation(project.name, actor.id, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation introuvable")
    messages = store.conversation_messages(conversation_id)
    return {**conversation, "message_count": len(messages), "messages": messages}


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(conversation_id: str, body: ConversationRename, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    if not store.rename_conversation(project.name, actor.id, conversation_id, body.title):
        raise HTTPException(404, "Conversation introuvable")
    conversation = store.conversation(project.name, actor.id, conversation_id)
    messages = store.conversation_messages(conversation_id)
    return {**conversation, "message_count": len(messages)}


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    if not store.delete_conversation(project.name, actor.id, conversation_id):
        raise HTTPException(404, "Conversation introuvable")


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    if body.adapter is not None and body.adapter not in manager.available_adapters(project):
        raise HTTPException(400, "Adapter absent de ce projet")
    enforce_agent_budget(project, "tokens")
    enforce_agent_budget(project, "duration")
    conversation_id = _resolve_conversation(body, project.name, actor.id)
    # F07: the same per-category ACL /rag/search applies, so RAG-grounded chat can't
    # surface chunks (or doc ids in rag_chunks) from a category this member can't read.
    allowed = store.rag_categories_allowed(project.name, store.project_role(project.name, actor))
    assistant = Assistant(project_dir=project, adapter=body.adapter, system_prompt=body.system_prompt,
                          allowed_categories=allowed)
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    execution_id = store.start_execution(project.name, actor.id,
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
    conversation_id = _persist_exchange(body, project.name, actor.id, conversation_id, result.response, result.rag_chunks)
    return ChatResponse(response=result.response, adapter=body.adapter, rag_used=result.rag_used,
                        rag_chunks=result.rag_chunks, execution_id=execution_id, conversation_id=conversation_id)


@router.post("/stream")
def chat_stream(body: ChatRequest, request: Request, project: Path = Depends(project_dir)):
    actor = _chat_actor(request, project)
    if body.adapter is not None and body.adapter not in manager.available_adapters(project):
        raise HTTPException(400, "Adapter absent de ce projet")
    enforce_agent_budget(project, "tokens")
    enforce_agent_budget(project, "duration")
    conversation_id = _resolve_conversation(body, project.name, actor.id)
    # F07: the same per-category ACL /rag/search applies, so RAG-grounded chat can't
    # surface chunks (or doc ids in rag_chunks) from a category this member can't read.
    allowed = store.rag_categories_allowed(project.name, store.project_role(project.name, actor))
    assistant = Assistant(project_dir=project, adapter=body.adapter, system_prompt=body.system_prompt,
                          allowed_categories=allowed)
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    execution_id = store.start_execution(project.name, actor.id,
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
    except Exception:
        store.fail_execution(execution_id, "internal_error", (time.perf_counter() - started) * 1000)
        raise

    def events():
        response_parts: list[str] = []
        first_token = True
        try:
            yield _sse("metadata", {"execution_id": execution_id, "conversation_id": conversation_id,
                                    "adapter": body.adapter, "rag_used": rag_used, "rag_chunks": rag_chunks})
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
            # Persisted only now, on success — a new conversation's id therefore only
            # appears in this "done" event (metadata carried None), the web client
            # reads it from either event.
            done_conversation_id = _persist_exchange(body, project.name, actor.id, conversation_id, response, rag_chunks)
            yield _sse("done", {"execution_id": execution_id, "conversation_id": done_conversation_id,
                                "response": response, "duration_ms": round(duration, 2)})
        except ValueError as exc:
            store.fail_execution(execution_id, "runtime_error", (time.perf_counter() - started) * 1000)
            yield _sse("error", {"detail": str(exc)})
        except Exception:
            store.fail_execution(execution_id, "internal_error", (time.perf_counter() - started) * 1000)
            yield _sse("error", {"detail": "La génération a échoué"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
