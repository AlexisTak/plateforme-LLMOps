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

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as db:
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
