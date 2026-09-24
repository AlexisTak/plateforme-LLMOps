"""Environment health checks — catches exactly the kind of silent regression
that broke this project once already: a pip install (llama.cpp's GGUF convert
requirements) quietly downgraded torch to a CPU-only wheel and transformers to
an incompatible version, and it went unnoticed until a training run failed.

Compares installed versions against requirements.txt (the source of truth for
"known good"), checks CUDA is actually usable (not just importable), and
surfaces GPU/disk/Ollama status in one place instead of scattered CLI checks.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Request

from api import outbound
from api.enterprise import actor_from_request, require_role, store
from api.schemas import OfflineStatus, OfflineUpdate, SystemHealth

ROOT = Path(__file__).resolve().parent.parent.parent
REQUIREMENTS_PATH = ROOT / "requirements.txt"
WATCHED_PACKAGES = ["torch", "transformers", "peft", "trl", "bitsandbytes", "accelerate", "datasets"]

router = APIRouter(prefix="/api/system", tags=["system"])


def _parse_pinned_versions() -> dict[str, str]:
    pinned = {}
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        pinned[name.strip().lower()] = version.strip()
    return pinned


def _check_packages() -> list[dict]:
    pinned = _parse_pinned_versions()
    results = []
    for pkg in WATCHED_PACKAGES:
        expected = pinned.get(pkg)
        try:
            module = __import__(pkg)
            installed = getattr(module, "__version__", "unknown")
        except ImportError:
            installed = None
        matches = expected is None or installed == expected or (installed and installed.startswith(expected))
        results.append({"package": pkg, "installed": installed, "expected": expected, "ok": bool(installed) and matches})
    return results


def _check_torch_cuda() -> dict:
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if cuda_available else None
        return {
            "torch_version": torch.__version__,
            "is_cpu_only_build": "+cpu" in torch.__version__,
            "cuda_available": cuda_available,
            "device_name": device_name,
            "ok": cuda_available and "+cpu" not in torch.__version__,
        }
    except ImportError:
        return {"torch_version": None, "is_cpu_only_build": None, "cuda_available": False, "device_name": None, "ok": False}


def _check_gpu() -> dict | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        name, total, used, util = [p.strip() for p in result.stdout.strip().split(",")]
        return {"name": name, "memory_total_mb": int(total), "memory_used_mb": int(used), "utilization_pct": int(util)}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def _check_disk() -> dict:
    usage = shutil.disk_usage(ROOT)
    return {"free_gb": round(usage.free / 1024**3, 1), "total_gb": round(usage.total / 1024**3, 1)}


def _check_ollama() -> dict:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"running": True, "models": models}
    except requests.RequestException:
        return {"running": False, "models": []}


@router.get("/health", response_model=SystemHealth)
def health():
    packages = _check_packages()
    torch_cuda = _check_torch_cuda()
    gpu = _check_gpu()
    disk = _check_disk()
    ollama = _check_ollama()

    package_issues = [p for p in packages if not p["ok"]]
    overall_ok = torch_cuda["ok"] and not package_issues and disk["free_gb"] > 5

    return SystemHealth(
        ok=overall_ok,
        torch_cuda=torch_cuda,
        packages=packages,
        gpu=gpu,
        disk=disk,
        ollama=ollama,
    )


def _offline_status() -> OfflineStatus:
    return OfflineStatus(enabled=outbound.offline_mode(), locked=outbound.offline_locked())


@router.get("/offline", response_model=OfflineStatus)
def get_offline():
    return _offline_status()


@router.put("/offline", response_model=OfflineStatus)
def put_offline(body: OfflineUpdate, request: Request):
    # Platform-wide network policy: admin only, like providers and tools.
    current = actor_from_request(request)
    require_role(current, "admin")
    if not body.enabled and outbound.offline_locked():
        raise HTTPException(409, "Mode hors ligne imposé par BISCUITS_OFFLINE dans l’environnement (.env) — "
                                 "modifiez-le puis redémarrez l’API pour le désactiver")
    outbound.set_offline(body.enabled)
    store.audit(current.id, "system.offline.enabled" if body.enabled else "system.offline.disabled", "system", "offline")
    return _offline_status()
