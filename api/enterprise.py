"""Local enterprise control-plane primitives.

SQLite is the durable default so the console remains self-contained. Identity
can be supplied by a trusted reverse proxy (Entra ID, Okta, Auth0, …); local
development deliberately falls back to an administrator account.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("BISCUITS_ENTERPRISE_DB", ROOT / ".enterprise" / "control-plane.db"))
ROLES = {"viewer": 0, "operator": 1, "reviewer": 2, "admin": 3}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Actor:
    id: str
    email: str
    role: str
    name: str


def actor_from_request(request: Request) -> Actor:
    mode = os.getenv("BISCUITS_AUTH_MODE", "local").lower()
    if mode == "local":
        return Actor("local-admin", "local@biscuits.invalid", "admin", "Administrateur local")
    if mode != "proxy":
        raise HTTPException(503, "BISCUITS_AUTH_MODE doit valoir local ou proxy")
    expected = os.getenv("BISCUITS_PROXY_SECRET", "")
    if not expected or request.headers.get("x-biscuits-proxy-secret") != expected:
        raise HTTPException(401, "Identité du proxy absente ou non fiable")
    actor_id = request.headers.get("x-biscuits-user-id", "").strip()
    email = request.headers.get("x-biscuits-user-email", "").strip()
    role = request.headers.get("x-biscuits-role", "viewer").strip().lower()
    if not actor_id or not email or role not in ROLES:
        raise HTTPException(401, "En-têtes d’identité incomplets")
    return Actor(actor_id, email, role, request.headers.get("x-biscuits-user-name", email))


def require_role(actor: Actor, minimum: str) -> None:
    if ROLES.get(actor.role, -1) < ROLES[minimum]:
        raise HTTPException(403, f"Rôle {minimum} requis")


class EnterpriseStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS audit_events (
                  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, actor_id TEXT NOT NULL,
                  action TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT,
                  project_id TEXT, details_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
                  event_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS model_versions (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, version TEXT NOT NULL,
                  status TEXT NOT NULL, model TEXT NOT NULL, dataset_version TEXT,
                  benchmark_generated_at TEXT, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
                  approved_at TEXT, approved_by TEXT, notes TEXT NOT NULL,
                  UNIQUE(project_id, version)
                );
                CREATE TABLE IF NOT EXISTS quotas (
                  project_id TEXT PRIMARY KEY, max_concurrent_jobs INTEGER NOT NULL DEFAULT 2,
                  max_daily_jobs INTEGER NOT NULL DEFAULT 25, max_storage_gb REAL NOT NULL DEFAULT 50
                );
                CREATE TABLE IF NOT EXISTS project_members (
                  project_id TEXT NOT NULL, actor_id TEXT NOT NULL, email TEXT NOT NULL,
                  name TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY(project_id, actor_id)
                );
                CREATE TABLE IF NOT EXISTS executions (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                  status TEXT NOT NULL, model TEXT NOT NULL, adapter TEXT, rag_requested INTEGER NOT NULL,
                  rag_used INTEGER NOT NULL DEFAULT 0, prompt_chars INTEGER NOT NULL,
                  response_chars INTEGER, estimated_tokens INTEGER, duration_ms REAL,
                  started_at TEXT NOT NULL, finished_at TEXT, error_code TEXT
                );
                CREATE TABLE IF NOT EXISTS trace_events (
                  execution_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL,
                  payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY(execution_id, seq)
                );
                CREATE TABLE IF NOT EXISTS providers (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                  type TEXT NOT NULL, base_url TEXT NOT NULL, model TEXT NOT NULL,
                  api_key_env TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                  UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS tools (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                  method TEXT NOT NULL, url TEXT NOT NULL, approval_required INTEGER NOT NULL,
                  timeout_seconds INTEGER NOT NULL, max_response_bytes INTEGER NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                  UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS mcp_servers (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                  url TEXT NOT NULL, api_key_env TEXT, enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL, UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tool_id TEXT NOT NULL,
                  requester_id TEXT NOT NULL, status TEXT NOT NULL, arguments_json TEXT NOT NULL,
                  result_json TEXT, created_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_policies (
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                  effect TEXT NOT NULL, tool_id TEXT, priority INTEGER NOT NULL DEFAULT 100,
                  enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                  UNIQUE(project_id, name)
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(tools)").fetchall()}
            for name, definition in {
                "connector_type": "TEXT NOT NULL DEFAULT 'http'",
                "connector_id": "TEXT",
                "action": "TEXT",
                "description": "TEXT",
                "input_schema_json": "TEXT",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE tools ADD COLUMN {name} {definition}")
            db.executescript("""
                CREATE INDEX IF NOT EXISTS executions_project_started ON executions(project_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS approvals_project_created ON approvals(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS policies_project_target ON tool_policies(project_id, enabled, tool_id);
                CREATE INDEX IF NOT EXISTS audit_project ON audit_events(project_id);
                CREATE INDEX IF NOT EXISTS tools_project_connector ON tools(project_id, connector_id);
            """)

    @staticmethod
    def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def audit(self, actor_id: str, action: str, resource_type: str, resource_id: str | None = None,
              project_id: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            previous = db.execute("SELECT event_hash FROM audit_events ORDER BY rowid DESC LIMIT 1").fetchone()
            previous_hash = previous[0] if previous else "GENESIS"
            event = {
                "id": str(uuid.uuid4()), "created_at": now(), "actor_id": actor_id,
                "action": action, "resource_type": resource_type, "resource_id": resource_id,
                "project_id": project_id, "details": details or {}, "previous_hash": previous_hash,
            }
            canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            event_hash = hashlib.sha256(canonical.encode()).hexdigest()
            db.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event["id"], event["created_at"], actor_id, action, resource_type, resource_id,
                 project_id, json.dumps(event["details"], ensure_ascii=False), previous_hash, event_hash),
            )
            return {**event, "event_hash": event_hash}

    def audits(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_events"
        args: list[Any] = []
        if project_id:
            query += " WHERE project_id=?"
            args.append(project_id)
        query += " ORDER BY rowid DESC LIMIT ?"
        args.append(min(max(limit, 1), 500))
        with self._connect() as db:
            result = self._rows(db.execute(query, args).fetchall())
        for row in result:
            row["details"] = json.loads(row.pop("details_json"))
        return result

    def verify_audit_chain(self) -> bool:
        with self._connect() as db:
            rows = self._rows(db.execute("SELECT * FROM audit_events ORDER BY rowid").fetchall())
        previous = "GENESIS"
        for row in rows:
            event = {key: row[key] for key in ("id", "created_at", "actor_id", "action", "resource_type", "resource_id", "project_id")}
            event["details"] = json.loads(row["details_json"])
            event["previous_hash"] = previous
            digest = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != digest:
                return False
            previous = digest
        return True

    def versions(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute("SELECT * FROM model_versions WHERE project_id=? ORDER BY rowid DESC", (project_id,)).fetchall())

    def create_version(self, project_id: str, version: str, model: str, dataset_version: str | None,
                       benchmark_at: str | None, actor: Actor, notes: str) -> dict[str, Any]:
        item_id = str(uuid.uuid4())
        with self._connect() as db:
            try:
                db.execute("INSERT INTO model_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (item_id, project_id, version, "draft", model, dataset_version, benchmark_at,
                            now(), actor.id, None, None, notes))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, f"La version {version} existe déjà") from exc
        return self.versions(project_id)[0]

    def transition(self, project_id: str, item_id: str, status: str, actor: Actor) -> dict[str, Any]:
        allowed = {"draft": {"evaluated", "archived"}, "evaluated": {"approved", "draft", "archived"},
                   "approved": {"production", "archived"}, "production": {"archived"}, "archived": {"production"}}
        with self._connect() as db:
            row = db.execute("SELECT * FROM model_versions WHERE id=? AND project_id=?", (item_id, project_id)).fetchone()
            if not row:
                raise HTTPException(404, "Version inconnue")
            if status not in allowed[row["status"]]:
                raise HTTPException(409, f"Transition {row['status']} → {status} non autorisée")
            if status in {"approved", "production"} and not row["benchmark_generated_at"]:
                raise HTTPException(409, "Un benchmark est requis avant l’approbation")
            if status == "approved" and os.getenv("BISCUITS_AUTH_MODE", "local").lower() == "proxy" and row["created_by"] == actor.id:
                raise HTTPException(409, "La personne qui crée une version ne peut pas aussi l’approuver")
            if status == "production" and not row["approved_at"]:
                raise HTTPException(409, "La version doit avoir été approuvée avant sa mise en production")
            approved_at = now() if status == "approved" else row["approved_at"]
            approved_by = actor.id if status == "approved" else row["approved_by"]
            if status == "production":
                db.execute("UPDATE model_versions SET status='archived' WHERE project_id=? AND status='production'", (project_id,))
            db.execute("UPDATE model_versions SET status=?, approved_at=?, approved_by=? WHERE id=?",
                       (status, approved_at, approved_by, item_id))
            return dict(db.execute("SELECT * FROM model_versions WHERE id=?", (item_id,)).fetchone())

    def quota(self, project_id: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO quotas(project_id) VALUES (?)", (project_id,))
            return dict(db.execute("SELECT * FROM quotas WHERE project_id=?", (project_id,)).fetchone())

    def set_quota(self, project_id: str, concurrent: int, daily: int, storage: float) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("INSERT INTO quotas VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET max_concurrent_jobs=excluded.max_concurrent_jobs,max_daily_jobs=excluded.max_daily_jobs,max_storage_gb=excluded.max_storage_gb",
                       (project_id, concurrent, daily, storage))
        return self.quota(project_id)

    def members(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute("SELECT * FROM project_members WHERE project_id=? ORDER BY role DESC,name", (project_id,)).fetchall())

    def set_member(self, project_id: str, actor_id: str, email: str, name: str, role: str) -> dict[str, Any]:
        if role not in ROLES:
            raise HTTPException(400, "Rôle inconnu")
        with self._connect() as db:
            db.execute("INSERT INTO project_members VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,actor_id) DO UPDATE SET email=excluded.email,name=excluded.name,role=excluded.role",
                       (project_id, actor_id, email, name, role, now()))
            return dict(db.execute("SELECT * FROM project_members WHERE project_id=? AND actor_id=?", (project_id, actor_id)).fetchone())

    def remove_member(self, project_id: str, actor_id: str) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM project_members WHERE project_id=? AND actor_id=?", (project_id, actor_id)).rowcount > 0

    def project_role(self, project_id: str, actor: Actor) -> str | None:
        if os.getenv("BISCUITS_AUTH_MODE", "local").lower() == "local" or actor.role == "admin":
            return actor.role
        with self._connect() as db:
            row = db.execute("SELECT role FROM project_members WHERE project_id=? AND actor_id=?", (project_id, actor.id)).fetchone()
        return row[0] if row else None

    def require_project_role(self, project_id: str, actor: Actor, minimum: str = "viewer") -> None:
        role = self.project_role(project_id, actor)
        if role is None or ROLES.get(role, -1) < ROLES[minimum]:
            raise HTTPException(403, "Tu n’es pas membre de ce projet ou ton rôle est insuffisant")

    def start_execution(self, project_id: str, actor_id: str, model: str, adapter: str | None,
                        rag_requested: bool, prompt_chars: int) -> str:
        execution_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("INSERT INTO executions(id,project_id,actor_id,status,model,adapter,rag_requested,prompt_chars,started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (execution_id, project_id, actor_id, "running", model, adapter, int(rag_requested), prompt_chars, now()))
            db.execute("INSERT INTO trace_events VALUES (?,?,?,?,?)", (execution_id, 1, "execution.started",
                       json.dumps({"model": model, "adapter": adapter, "rag_requested": rag_requested, "prompt_chars": prompt_chars}), now()))
        return execution_id

    def finish_execution(self, execution_id: str, response_chars: int, rag_used: bool,
                         rag_documents: list[str], duration_ms: float) -> None:
        estimated_tokens = max(1, round(response_chars / 4))
        with self._connect() as db:
            db.execute("UPDATE executions SET status='completed',rag_used=?,response_chars=?,estimated_tokens=?,duration_ms=?,finished_at=? WHERE id=?",
                       (int(rag_used), response_chars, estimated_tokens, round(duration_ms, 2), now(), execution_id))
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM trace_events WHERE execution_id=?", (execution_id,)).fetchone()[0]
            db.execute("INSERT INTO trace_events VALUES (?,?,?,?,?)", (execution_id, seq, "execution.completed",
                       json.dumps({"rag_used": rag_used, "rag_documents": rag_documents, "response_chars": response_chars,
                                   "estimated_tokens": estimated_tokens, "duration_ms": round(duration_ms, 2)}), now()))

    def fail_execution(self, execution_id: str, error_code: str, duration_ms: float) -> None:
        with self._connect() as db:
            db.execute("UPDATE executions SET status='failed',duration_ms=?,finished_at=?,error_code=? WHERE id=?",
                       (round(duration_ms, 2), now(), error_code, execution_id))
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM trace_events WHERE execution_id=?", (execution_id,)).fetchone()[0]
            db.execute("INSERT INTO trace_events VALUES (?,?,?,?,?)", (execution_id, seq, "execution.failed",
                       json.dumps({"error_code": error_code, "duration_ms": round(duration_ms, 2)}), now()))

    def trace_event(self, execution_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM trace_events WHERE execution_id=?", (execution_id,)).fetchone()[0]
            db.execute("INSERT INTO trace_events VALUES (?,?,?,?,?)",
                       (execution_id, seq, event_type, json.dumps(payload), now()))

    def executions(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute("SELECT * FROM executions WHERE project_id=? ORDER BY started_at DESC LIMIT ?", (project_id, min(max(limit, 1), 500))).fetchall())

    def execution(self, project_id: str, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM executions WHERE project_id=? AND id=?", (project_id, execution_id)).fetchone()
            if not row:
                return None
            result = dict(row)
            events = self._rows(db.execute("SELECT * FROM trace_events WHERE execution_id=? ORDER BY seq", (execution_id,)).fetchall())
        for event in events:
            event["payload"] = json.loads(event.pop("payload_json"))
        result["events"] = events
        return result

    def providers(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute("SELECT * FROM providers WHERE project_id=? ORDER BY name", (project_id,)).fetchall())

    def set_provider(self, project_id: str, name: str, provider_type: str, base_url: str,
                     model: str, api_key_env: str | None, enabled: bool) -> dict[str, Any]:
        with self._connect() as db:
            existing = db.execute("SELECT id,created_at FROM providers WHERE project_id=? AND name=?", (project_id, name)).fetchone()
            provider_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
            db.execute("INSERT INTO providers VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET type=excluded.type,base_url=excluded.base_url,model=excluded.model,api_key_env=excluded.api_key_env,enabled=excluded.enabled",
                       (provider_id, project_id, name, provider_type, base_url, model, api_key_env, int(enabled), created_at))
            return dict(db.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone())

    def remove_provider(self, project_id: str, provider_id: str) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM providers WHERE project_id=? AND id=?", (project_id, provider_id)).rowcount > 0

    def tools(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = self._rows(db.execute("SELECT * FROM tools WHERE project_id=? ORDER BY name", (project_id,)).fetchall())
        for row in rows:
            row["input_schema"] = json.loads(row.pop("input_schema_json")) if row.get("input_schema_json") else None
        return rows

    def tool(self, project_id: str, tool_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tools WHERE project_id=? AND id=?", (project_id, tool_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        schema = result.pop("input_schema_json")
        result["input_schema"] = json.loads(schema) if schema else None
        return result

    def set_tool(self, project_id: str, name: str, method: str, url: str, approval_required: bool,
                 timeout_seconds: int, max_response_bytes: int) -> dict[str, Any]:
        with self._connect() as db:
            existing = db.execute("SELECT id,created_at FROM tools WHERE project_id=? AND name=?", (project_id, name)).fetchone()
            tool_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
            db.execute("INSERT INTO tools(id,project_id,name,method,url,approval_required,timeout_seconds,max_response_bytes,enabled,created_at,connector_type) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET method=excluded.method,url=excluded.url,approval_required=excluded.approval_required,timeout_seconds=excluded.timeout_seconds,max_response_bytes=excluded.max_response_bytes,connector_type='http',connector_id=NULL,action=NULL,description=NULL,input_schema_json=NULL",
                       (tool_id, project_id, name, method, url, int(approval_required), timeout_seconds, max_response_bytes, 1, created_at, "http"))
            return dict(db.execute("SELECT * FROM tools WHERE id=?", (tool_id,)).fetchone())

    def mcp_servers(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute("SELECT * FROM mcp_servers WHERE project_id=? ORDER BY name", (project_id,)).fetchall())

    def set_mcp_server(self, project_id: str, name: str, url: str,
                       api_key_env: str | None, enabled: bool) -> dict[str, Any]:
        with self._connect() as db:
            existing = db.execute("SELECT id,created_at FROM mcp_servers WHERE project_id=? AND name=?", (project_id, name)).fetchone()
            server_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
            db.execute("INSERT INTO mcp_servers VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET url=excluded.url,api_key_env=excluded.api_key_env,enabled=excluded.enabled",
                       (server_id, project_id, name, url, api_key_env, int(enabled), created_at))
        return next(item for item in self.mcp_servers(project_id) if item["id"] == server_id)

    def sync_mcp_tools(self, project_id: str, server_id: str,
                       remote_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        server = next((item for item in self.mcp_servers(project_id) if item["id"] == server_id), None)
        if not server:
            raise HTTPException(404, "Serveur MCP inconnu")
        imported_ids: list[str] = []
        with self._connect() as db:
            for remote in remote_tools:
                annotations = remote.get("annotations") if isinstance(remote.get("annotations"), dict) else {}
                if annotations.get("readOnlyHint") is not True or not isinstance(remote.get("name"), str):
                    continue
                display_name = f"{server['name']}: {remote['name']}"
                existing = db.execute("SELECT id,created_at FROM tools WHERE project_id=? AND name=?", (project_id, display_name)).fetchone()
                tool_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
                schema = remote.get("inputSchema") if isinstance(remote.get("inputSchema"), dict) else {"type": "object"}
                db.execute("INSERT INTO tools(id,project_id,name,method,url,approval_required,timeout_seconds,max_response_bytes,enabled,created_at,connector_type,connector_id,action,description,input_schema_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET url=excluded.url,enabled=1,connector_type='mcp',connector_id=excluded.connector_id,action=excluded.action,description=excluded.description,input_schema_json=excluded.input_schema_json",
                           (tool_id, project_id, display_name, "MCP", server["url"], 0, 10, 100000, 1, created_at,
                            "mcp", server_id, remote["name"], str(remote.get("description", ""))[:2000], json.dumps(schema)))
                imported_ids.append(tool_id)
            if imported_ids:
                placeholders = ",".join("?" for _ in imported_ids)
                db.execute(f"UPDATE tools SET enabled=0 WHERE project_id=? AND connector_id=? AND id NOT IN ({placeholders})",
                           (project_id, server_id, *imported_ids))
            else:
                db.execute("UPDATE tools SET enabled=0 WHERE project_id=? AND connector_id=?", (project_id, server_id))
        imported_id_set = set(imported_ids)
        return [tool for tool in self.tools(project_id) if tool["id"] in imported_id_set]

    def policies(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute(
                "SELECT tool_policies.*,tools.name AS tool_name FROM tool_policies "
                "LEFT JOIN tools ON tools.id=tool_policies.tool_id "
                "WHERE tool_policies.project_id=? ORDER BY priority DESC,name",
                (project_id,),
            ).fetchall())

    def set_policy(self, project_id: str, name: str, effect: str, tool_id: str | None,
                   priority: int, enabled: bool) -> dict[str, Any]:
        if effect not in {"allow", "deny", "require_approval"}:
            raise HTTPException(400, "Effet de politique inconnu")
        with self._connect() as db:
            if tool_id and not db.execute(
                "SELECT 1 FROM tools WHERE project_id=? AND id=?", (project_id, tool_id)
            ).fetchone():
                raise HTTPException(400, "L’outil ciblé n’existe pas dans ce projet")
            existing = db.execute(
                "SELECT id,created_at FROM tool_policies WHERE project_id=? AND name=?",
                (project_id, name),
            ).fetchone()
            policy_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
            db.execute(
                "INSERT INTO tool_policies VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(project_id,name) DO UPDATE SET effect=excluded.effect,"
                "tool_id=excluded.tool_id,priority=excluded.priority,enabled=excluded.enabled",
                (policy_id, project_id, name, effect, tool_id, priority, int(enabled), created_at),
            )
        return next(item for item in self.policies(project_id) if item["id"] == policy_id)

    def remove_policy(self, project_id: str, policy_id: str) -> bool:
        with self._connect() as db:
            return db.execute(
                "DELETE FROM tool_policies WHERE project_id=? AND id=?", (project_id, policy_id)
            ).rowcount > 0

    def evaluate_tool_policy(self, project_id: str, tool_id: str) -> dict[str, Any]:
        tool = self.tool(project_id, tool_id)
        if not tool:
            raise HTTPException(404, "Outil inconnu")
        with self._connect() as db:
            matching = self._rows(db.execute(
                "SELECT * FROM tool_policies WHERE project_id=? AND enabled=1 "
                "AND (tool_id IS NULL OR tool_id=?) ORDER BY priority DESC,name",
                (project_id, tool_id),
            ).fetchall())
        denied = [item for item in matching if item["effect"] == "deny"]
        if denied:
            selected = max(denied, key=lambda item: (item["priority"], item["created_at"]))
        elif matching:
            rank = {"allow": 0, "require_approval": 1}
            selected = max(matching, key=lambda item: (item["priority"], rank[item["effect"]], item["created_at"]))
        else:
            effect = "require_approval" if tool["approval_required"] else "allow"
            return {"effect": effect, "policy_id": None, "policy_name": None,
                    "reason": "Configuration par défaut de l’outil"}
        return {"effect": selected["effect"], "policy_id": selected["id"],
                "policy_name": selected["name"],
                "reason": f"Politique « {selected['name']} » (priorité {selected['priority']})"}

    def request_approval(self, project_id: str, tool_id: str, requester_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?)", (approval_id, project_id, tool_id,
                       requester_id, "pending", json.dumps(arguments), None, now(), None, None))
        return self.approval(project_id, approval_id)

    def approvals(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = self._rows(db.execute("SELECT approvals.*,tools.name AS tool_name FROM approvals JOIN tools ON tools.id=approvals.tool_id WHERE approvals.project_id=? ORDER BY approvals.created_at DESC", (project_id,)).fetchall())
        for row in rows:
            row["arguments"] = json.loads(row.pop("arguments_json"))
            payload = row.pop("result_json")
            row["result"] = json.loads(payload) if payload else None
        return rows

    def approval(self, project_id: str, approval_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT approvals.*,tools.name AS tool_name FROM approvals "
                "JOIN tools ON tools.id=approvals.tool_id WHERE approvals.project_id=? AND approvals.id=?",
                (project_id, approval_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["arguments"] = json.loads(result.pop("arguments_json"))
        payload = result.pop("result_json")
        result["result"] = json.loads(payload) if payload else None
        return result

    def decide_approval(self, project_id: str, approval_id: str, decision: str, actor_id: str,
                        result: dict[str, Any] | None = None) -> dict[str, Any]:
        if decision not in {"approved", "denied"}:
            raise HTTPException(400, "Décision inconnue")
        with self._connect() as db:
            expected = "processing" if decision == "approved" else "pending"
            changed = db.execute(
                "UPDATE approvals SET status=?,result_json=?,decided_at=?,decided_by=? "
                "WHERE project_id=? AND id=? AND status=?",
                (decision, json.dumps(result) if result is not None else None, now(), actor_id,
                 project_id, approval_id, expected),
            ).rowcount
            if not changed:
                exists = db.execute("SELECT 1 FROM approvals WHERE project_id=? AND id=?", (project_id, approval_id)).fetchone()
                if not exists:
                    raise HTTPException(404, "Approbation inconnue")
                raise HTTPException(409, "Cette demande a déjà été traitée")
        return self.approval(project_id, approval_id)

    def claim_approval(self, project_id: str, approval_id: str) -> None:
        with self._connect() as db:
            changed = db.execute("UPDATE approvals SET status='processing' WHERE project_id=? AND id=? AND status='pending'",
                                 (project_id, approval_id)).rowcount
        if not changed:
            raise HTTPException(409, "Cette demande a déjà été traitée")

    def fail_claimed_approval(self, project_id: str, approval_id: str, actor_id: str,
                              message: str) -> dict[str, Any]:
        with self._connect() as db:
            changed = db.execute(
                "UPDATE approvals SET status='failed',result_json=?,decided_at=?,decided_by=? "
                "WHERE project_id=? AND id=? AND status='processing'",
                (json.dumps({"error": message}), now(), actor_id, project_id, approval_id),
            ).rowcount
        if not changed:
            raise HTTPException(409, "Cette demande n’est pas en cours d’exécution")
        return self.approval(project_id, approval_id)


class Metrics:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.latencies: deque[float] = deque(maxlen=2000)

    def observe(self, method: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.counts["requests_total"] += 1
            self.counts[f"status_{status // 100}xx"] += 1
            self.counts[f"method_{method.lower()}"] += 1
            self.latencies.append(duration_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = sorted(self.latencies)
            p95 = values[min(len(values) - 1, int(len(values) * .95))] if values else 0
            return {**self.counts, "uptime_seconds": round(time.time() - self.started_at),
                    "latency_avg_ms": round(sum(values) / len(values), 2) if values else 0,
                    "latency_p95_ms": round(p95, 2)}


store = EnterpriseStore()
metrics = Metrics()
