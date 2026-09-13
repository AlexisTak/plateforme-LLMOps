"""Cheap model checks performed before expensive training or evaluation jobs."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=64)
def _hub_metadata(model: str) -> tuple[bool, str | None, int | None, int | None, str | None]:
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(model, files_metadata=True)
        size = sum((getattr(item, "size", 0) or 0) for item in info.siblings)
        safetensors = getattr(info, "safetensors", None)
        parameters = getattr(safetensors, "total", None) if safetensors else None
        architecture = None
        if info.config:
            architecture = (info.config.get("architectures") or [None])[0]
        return True, architecture, parameters, size or None, None
    except Exception as exc:  # Hub exceptions vary for missing, private and offline repos.
        return False, None, None, None, str(exc)


def check_model(model: str) -> dict:
    accessible, architecture, parameters, download_bytes, hub_error = _hub_metadata(model)
    errors: list[str] = []
    warnings: list[str] = []
    if not accessible:
        errors.append("Modèle Hugging Face introuvable, privé sans authentification, ou réseau indisponible.")

    cuda_available = False
    available_vram_gb = None
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            free_bytes, _ = torch.cuda.mem_get_info()
            available_vram_gb = round(free_bytes / 1024**3, 1)
        else:
            errors.append("CUDA n'est pas disponible : l'entraînement 4 bits nécessite un GPU NVIDIA compatible.")
    except ImportError:
        errors.append("PyTorch n'est pas installé dans l'environnement de l'API.")

    estimated_vram_gb = round((parameters * 0.65 / 1024**3) + 1.5, 1) if parameters else None
    if estimated_vram_gb and available_vram_gb and estimated_vram_gb > available_vram_gb:
        errors.append(f"VRAM probablement insuffisante : environ {estimated_vram_gb} Go requis, {available_vram_gb} Go libres.")
    elif estimated_vram_gb is None and accessible:
        warnings.append("Le dépôt ne publie pas son nombre de paramètres : estimation VRAM indisponible.")

    return {
        "model": model,
        "ready": not errors,
        "accessible": accessible,
        "architecture": architecture,
        "parameter_count": parameters,
        "estimated_download_gb": round(download_bytes / 1024**3, 1) if download_bytes else None,
        "estimated_vram_gb": estimated_vram_gb,
        "available_vram_gb": available_vram_gb,
        "cuda_available": cuda_available,
        "warnings": warnings,
        "errors": errors,
        "technical_detail": hub_error,
    }


def require_ready(model: str) -> dict:
    result = check_model(model)
    if not result["ready"]:
        raise ValueError(" ".join(result["errors"]))
    return result
