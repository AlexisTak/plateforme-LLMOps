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

from api.opportunities_seed import SEED_OPPORTUNITIES

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
                CREATE TABLE IF NOT EXISTS agent_budgets (
                  project_id TEXT PRIMARY KEY, max_tokens_per_day INTEGER NOT NULL DEFAULT 200000,
                  max_duration_ms_per_day INTEGER NOT NULL DEFAULT 7200000,
                  max_tool_calls_per_day INTEGER NOT NULL DEFAULT 500
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
                CREATE TABLE IF NOT EXISTS opportunities (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                  customer_problem TEXT NOT NULL DEFAULT '', proposed_solution TEXT NOT NULL DEFAULT '',
                  target_customer TEXT NOT NULL DEFAULT '', sector TEXT NOT NULL DEFAULT '',
                  value_proposition TEXT NOT NULL DEFAULT '', technologies_json TEXT NOT NULL DEFAULT '[]',
                  maturity TEXT NOT NULL DEFAULT '', dev_difficulty INTEGER NOT NULL DEFAULT 3,
                  sales_difficulty INTEGER NOT NULL DEFAULT 3, competition TEXT NOT NULL DEFAULT '',
                  differentiation TEXT NOT NULL DEFAULT '', business_model TEXT NOT NULL DEFAULT '',
                  setup_cost REAL NOT NULL DEFAULT 0, monthly_cost REAL NOT NULL DEFAULT 0,
                  setup_price REAL NOT NULL DEFAULT 0, monthly_price REAL NOT NULL DEFAULT 0,
                  estimated_margin_pct REAL NOT NULL DEFAULT 0, recurring_revenue_potential REAL NOT NULL DEFAULT 0,
                  risks_json TEXT NOT NULL DEFAULT '[]', regulatory_constraints TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'idee', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  created_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS opportunity_scores (
                  opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
                  market INTEGER NOT NULL DEFAULT 0, profitability INTEGER NOT NULL DEFAULT 0,
                  feasibility INTEGER NOT NULL DEFAULT 0, commercialization INTEGER NOT NULL DEFAULT 0,
                  scalability INTEGER NOT NULL DEFAULT 0, retention INTEGER NOT NULL DEFAULT 0,
                  risk INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS opportunity_kpis (
                  id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
                  category TEXT NOT NULL, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT '',
                  current_value REAL, target_value REAL, previous_value REAL, measured_at TEXT,
                  higher_is_better INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                  UNIQUE(opportunity_id, name)
                );
                CREATE TABLE IF NOT EXISTS opportunity_ai_analyses (
                  id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
                  project_id TEXT NOT NULL, provider_id TEXT NOT NULL, result_json TEXT NOT NULL,
                  recommended_score INTEGER, created_at TEXT NOT NULL, created_by TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(tools)").fetchall()}
            for name, definition in {
                "connector_type": "TEXT NOT NULL DEFAULT 'http'",
                "connector_id": "TEXT",
                "action": "TEXT",
                "description": "TEXT",
                "input_schema_json": "TEXT",
                "risk_level": "TEXT NOT NULL DEFAULT 'medium'",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE tools ADD COLUMN {name} {definition}")
            model_version_columns = {row["name"] for row in db.execute("PRAGMA table_info(model_versions)").fetchall()}
            for name, definition in {
                "adapter": "TEXT",
                "quantization": "TEXT",
                "rag_version": "TEXT",
                "environment": "TEXT NOT NULL DEFAULT 'local'",
                "artifacts_json": "TEXT NOT NULL DEFAULT '{}'",
            }.items():
                if name not in model_version_columns:
                    db.execute(f"ALTER TABLE model_versions ADD COLUMN {name} {definition}")
            db.executescript("""
                CREATE INDEX IF NOT EXISTS executions_project_started ON executions(project_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS approvals_project_created ON approvals(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS policies_project_target ON tool_policies(project_id, enabled, tool_id);
                CREATE INDEX IF NOT EXISTS audit_project ON audit_events(project_id);
                CREATE INDEX IF NOT EXISTS tools_project_connector ON tools(project_id, connector_id);
                CREATE INDEX IF NOT EXISTS opportunity_kpis_opportunity ON opportunity_kpis(opportunity_id);
                CREATE INDEX IF NOT EXISTS opportunity_analyses_opportunity ON opportunity_ai_analyses(opportunity_id, created_at DESC);
            """)
        self._seed_opportunities_if_empty()

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
            rows = self._rows(db.execute("SELECT * FROM model_versions WHERE project_id=? ORDER BY rowid DESC", (project_id,)).fetchall())
        for row in rows:
            row["artifacts"] = json.loads(row.pop("artifacts_json"))
        return rows

    def create_version(self, project_id: str, version: str, model: str, dataset_version: str | None,
                       benchmark_at: str | None, actor: Actor, notes: str, *, adapter: str | None = None,
                       quantization: str | None = None, rag_version: str | None = None,
                       environment: str = "local", artifacts: dict[str, Any] | None = None) -> dict[str, Any]:
        item_id = str(uuid.uuid4())
        with self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO model_versions "
                    "(id,project_id,version,status,model,dataset_version,benchmark_generated_at,"
                    "created_at,created_by,approved_at,approved_by,notes,adapter,quantization,"
                    "rag_version,environment,artifacts_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item_id, project_id, version, "draft", model, dataset_version, benchmark_at,
                     now(), actor.id, None, None, notes, adapter, quantization, rag_version,
                     environment, json.dumps(artifacts or {}, ensure_ascii=False)),
                )
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
            result = dict(db.execute("SELECT * FROM model_versions WHERE id=?", (item_id,)).fetchone())
            result["artifacts"] = json.loads(result.pop("artifacts_json"))
            return result

    def quota(self, project_id: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO quotas(project_id) VALUES (?)", (project_id,))
            return dict(db.execute("SELECT * FROM quotas WHERE project_id=?", (project_id,)).fetchone())

    def set_quota(self, project_id: str, concurrent: int, daily: int, storage: float) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("INSERT INTO quotas VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET max_concurrent_jobs=excluded.max_concurrent_jobs,max_daily_jobs=excluded.max_daily_jobs,max_storage_gb=excluded.max_storage_gb",
                       (project_id, concurrent, daily, storage))
        return self.quota(project_id)

    def agent_budget(self, project_id: str) -> dict[str, Any]:
        """F14 "Budgets par agent en jetons, durée et nombre d'appels d'outils" — an
        "agent" in this app is a project (F03). Same insert-if-missing pattern as
        quota()/set_quota() above."""
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO agent_budgets(project_id) VALUES (?)", (project_id,))
            return dict(db.execute("SELECT * FROM agent_budgets WHERE project_id=?", (project_id,)).fetchone())

    def set_agent_budget(self, project_id: str, max_tokens_per_day: int, max_duration_ms_per_day: int,
                         max_tool_calls_per_day: int) -> dict[str, Any]:
        with self._connect() as db:
            db.execute(
                "INSERT INTO agent_budgets VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
                "max_tokens_per_day=excluded.max_tokens_per_day,max_duration_ms_per_day=excluded.max_duration_ms_per_day,"
                "max_tool_calls_per_day=excluded.max_tool_calls_per_day",
                (project_id, max_tokens_per_day, max_duration_ms_per_day, max_tool_calls_per_day),
            )
        return self.agent_budget(project_id)

    def agent_budget_usage(self, project_id: str) -> dict[str, Any]:
        """Cumulative usage for the current UTC day — tokens/duration from executions
        (chat), tool calls from the audit log (covers both the direct-allow path and
        the approve-then-execute path, api/routes/enterprise.py::execute_tool /
        decide_approval — neither writes to a dedicated "tool call" table)."""
        today = now()[:10]
        with self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(estimated_tokens),0) AS tokens, COALESCE(SUM(duration_ms),0) AS duration_ms "
                "FROM executions WHERE project_id=? AND started_at>=?", (project_id, today),
            ).fetchone()
            tool_calls = db.execute(
                "SELECT COUNT(*) FROM audit_events WHERE project_id=? AND created_at>=? "
                "AND action IN ('tool.executed','tool.approval.approved')", (project_id, today),
            ).fetchone()[0]
        return {"tokens_used": row["tokens"] or 0, "duration_ms_used": row["duration_ms"] or 0, "tool_calls_used": tool_calls}

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
                 timeout_seconds: int, max_response_bytes: int, risk_level: str = "medium") -> dict[str, Any]:
        with self._connect() as db:
            existing = db.execute("SELECT id,created_at FROM tools WHERE project_id=? AND name=?", (project_id, name)).fetchone()
            tool_id, created_at = (existing["id"], existing["created_at"]) if existing else (str(uuid.uuid4()), now())
            db.execute("INSERT INTO tools(id,project_id,name,method,url,approval_required,timeout_seconds,max_response_bytes,enabled,created_at,connector_type,risk_level) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET method=excluded.method,url=excluded.url,approval_required=excluded.approval_required,timeout_seconds=excluded.timeout_seconds,max_response_bytes=excluded.max_response_bytes,connector_type='http',connector_id=NULL,action=NULL,description=NULL,input_schema_json=NULL,risk_level=excluded.risk_level",
                       (tool_id, project_id, name, method, url, int(approval_required), timeout_seconds, max_response_bytes, 1, created_at, "http", risk_level))
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
            result = {"effect": selected["effect"], "policy_id": selected["id"], "policy_name": selected["name"],
                      "reason": f"Politique « {selected['name']} » (priorité {selected['priority']})"}
        elif matching:
            rank = {"allow": 0, "require_approval": 1}
            selected = max(matching, key=lambda item: (item["priority"], rank[item["effect"]], item["created_at"]))
            result = {"effect": selected["effect"], "policy_id": selected["id"], "policy_name": selected["name"],
                      "reason": f"Politique « {selected['name']} » (priorité {selected['priority']})"}
        else:
            effect = "require_approval" if tool["approval_required"] else "allow"
            result = {"effect": effect, "policy_id": None, "policy_name": None,
                      "reason": "Configuration par défaut de l’outil"}
        # Defense in depth: a CRITICAL-risk tool must never run on an LLM's say-so alone, even
        # if an "allow" policy matches — only an explicit "deny" policy can skip the approval gate.
        if tool["risk_level"] == "critical" and result["effect"] == "allow":
            return {**result, "effect": "require_approval",
                    "reason": result["reason"] + " (approbation forcée : outil à risque critique)"}
        return result

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

    OPPORTUNITY_SCORE_FIELDS = ("market", "profitability", "feasibility", "commercialization",
                                "scalability", "retention", "risk")

    def _opportunity_row(self, db, opportunity_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["technologies"] = json.loads(result.pop("technologies_json"))
        result["risks"] = json.loads(result.pop("risks_json"))
        scores_row = db.execute("SELECT * FROM opportunity_scores WHERE opportunity_id=?", (opportunity_id,)).fetchone()
        result["scores"] = {key: scores_row[key] for key in self.OPPORTUNITY_SCORE_FIELDS} if scores_row \
            else {key: 0 for key in self.OPPORTUNITY_SCORE_FIELDS}
        return result

    def list_opportunities(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM opportunities ORDER BY created_at").fetchall()]
            return [self._opportunity_row(db, item_id) for item_id in ids]

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            return self._opportunity_row(db, opportunity_id)

    def create_opportunity(self, data: dict[str, Any], actor: Actor) -> dict[str, Any]:
        opportunity_id = str(uuid.uuid4())
        timestamp = now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO opportunities(id,name,description,customer_problem,proposed_solution,"
                "target_customer,sector,value_proposition,technologies_json,maturity,dev_difficulty,"
                "sales_difficulty,competition,differentiation,business_model,setup_cost,monthly_cost,"
                "setup_price,monthly_price,estimated_margin_pct,recurring_revenue_potential,risks_json,"
                "regulatory_constraints,status,created_at,updated_at,created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (opportunity_id, data["name"], data["description"], data["customer_problem"],
                 data["proposed_solution"], data["target_customer"], data["sector"],
                 data["value_proposition"], json.dumps(data["technologies"]), data["maturity"],
                 data["dev_difficulty"], data["sales_difficulty"], data["competition"],
                 data["differentiation"], data["business_model"], data["setup_cost"],
                 data["monthly_cost"], data["setup_price"], data["monthly_price"],
                 data["estimated_margin_pct"], data["recurring_revenue_potential"],
                 json.dumps(data["risks"]), data["regulatory_constraints"], "idee",
                 timestamp, timestamp, actor.id),
            )
            db.execute(
                "INSERT INTO opportunity_scores(opportunity_id,market,profitability,feasibility,"
                "commercialization,scalability,retention,risk,updated_at) VALUES (?,0,0,0,0,0,0,0,?)",
                (opportunity_id, timestamp),
            )
            return self._opportunity_row(db, opportunity_id)

    def update_opportunity(self, opportunity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            db.execute(
                "UPDATE opportunities SET name=?,description=?,customer_problem=?,proposed_solution=?,"
                "target_customer=?,sector=?,value_proposition=?,technologies_json=?,maturity=?,"
                "dev_difficulty=?,sales_difficulty=?,competition=?,differentiation=?,business_model=?,"
                "setup_cost=?,monthly_cost=?,setup_price=?,monthly_price=?,estimated_margin_pct=?,"
                "recurring_revenue_potential=?,risks_json=?,regulatory_constraints=?,updated_at=? WHERE id=?",
                (data["name"], data["description"], data["customer_problem"], data["proposed_solution"],
                 data["target_customer"], data["sector"], data["value_proposition"],
                 json.dumps(data["technologies"]), data["maturity"], data["dev_difficulty"],
                 data["sales_difficulty"], data["competition"], data["differentiation"],
                 data["business_model"], data["setup_cost"], data["monthly_cost"], data["setup_price"],
                 data["monthly_price"], data["estimated_margin_pct"], data["recurring_revenue_potential"],
                 json.dumps(data["risks"]), data["regulatory_constraints"], now(), opportunity_id),
            )
            return self._opportunity_row(db, opportunity_id)

    def update_opportunity_status(self, opportunity_id: str, status: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("UPDATE opportunities SET status=?, updated_at=? WHERE id=?", (status, now(), opportunity_id))
            return self._opportunity_row(db, opportunity_id)

    def update_opportunity_scores(self, opportunity_id: str, scores: dict[str, int]) -> dict[str, Any]:
        with self._connect() as db:
            db.execute(
                "UPDATE opportunity_scores SET market=?,profitability=?,feasibility=?,commercialization=?,"
                "scalability=?,retention=?,risk=?,updated_at=? WHERE opportunity_id=?",
                (scores["market"], scores["profitability"], scores["feasibility"], scores["commercialization"],
                 scores["scalability"], scores["retention"], scores["risk"], now(), opportunity_id),
            )
            return self._opportunity_row(db, opportunity_id)

    def delete_opportunity(self, opportunity_id: str) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM opportunities WHERE id=?", (opportunity_id,)).rowcount > 0

    def list_kpis(self, opportunity_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return self._rows(db.execute(
                "SELECT * FROM opportunity_kpis WHERE opportunity_id=? ORDER BY category,name",
                (opportunity_id,),
            ).fetchall())

    def upsert_kpi(self, opportunity_id: str, name: str, category: str, unit: str,
                   current_value: float | None, target_value: float | None,
                   higher_is_better: bool) -> dict[str, Any]:
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM opportunity_kpis WHERE opportunity_id=? AND name=?",
                (opportunity_id, name),
            ).fetchone()
            if existing:
                kpi_id = existing["id"]
                db.execute(
                    "UPDATE opportunity_kpis SET category=?,unit=?,current_value=?,previous_value=?,"
                    "target_value=?,higher_is_better=?,measured_at=? WHERE id=?",
                    (category, unit, current_value, existing["current_value"], target_value,
                     int(higher_is_better), now(), kpi_id),
                )
            else:
                kpi_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO opportunity_kpis(id,opportunity_id,category,name,unit,current_value,"
                    "target_value,previous_value,measured_at,higher_is_better,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (kpi_id, opportunity_id, category, name, unit, current_value, target_value,
                     None, now(), int(higher_is_better), now()),
                )
            return dict(db.execute("SELECT * FROM opportunity_kpis WHERE id=?", (kpi_id,)).fetchone())

    def save_ai_analysis(self, opportunity_id: str, project_id: str, provider_id: str,
                         result: dict[str, Any], recommended_score: int | None,
                         actor_id: str) -> dict[str, Any]:
        analysis_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO opportunity_ai_analyses(id,opportunity_id,project_id,provider_id,"
                "result_json,recommended_score,created_at,created_by) VALUES (?,?,?,?,?,?,?,?)",
                (analysis_id, opportunity_id, project_id, provider_id, json.dumps(result),
                 recommended_score, now(), actor_id),
            )
            row = dict(db.execute("SELECT * FROM opportunity_ai_analyses WHERE id=?", (analysis_id,)).fetchone())
            row["result"] = json.loads(row.pop("result_json"))
            return row

    def list_ai_analyses(self, opportunity_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = self._rows(db.execute(
                "SELECT * FROM opportunity_ai_analyses WHERE opportunity_id=? ORDER BY created_at DESC",
                (opportunity_id,),
            ).fetchall())
        for row in rows:
            row["result"] = json.loads(row.pop("result_json"))
        return rows

    def _seed_opportunities_if_empty(self) -> None:
        with self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        if count:
            return
        system_actor = Actor("system-seed", "seed@biscuits.invalid", "admin", "Amorçage système")
        for seed in SEED_OPPORTUNITIES:
            opportunity = self.create_opportunity(seed, system_actor)
            self.update_opportunity_scores(opportunity["id"], seed["scores"])
            self.update_opportunity_status(opportunity["id"], seed["status"])
            for kpi in seed["kpis"]:
                if kpi.get("previous_value") is not None:
                    self.upsert_kpi(opportunity["id"], kpi["name"], kpi["category"], kpi["unit"],
                                     kpi["previous_value"], kpi["target_value"], kpi["higher_is_better"])
                self.upsert_kpi(opportunity["id"], kpi["name"], kpi["category"], kpi["unit"],
                                 kpi["current_value"], kpi["target_value"], kpi["higher_is_better"])


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
