import json
from pathlib import Path

from api.schemas import UpdateProjectSettingsRequest


def _project(tmp_path: Path) -> Path:
    (tmp_path / "training" / "configs").mkdir(parents=True)
    (tmp_path / "meta.json").write_text(json.dumps({
        "id": "demo", "label": "Demo", "project_type": "general", "purpose": "Mission initiale",
        "output_mode": "natural", "base_model": "org/base", "inference_model": "org/base",
        "added_at": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")
    (tmp_path / "training" / "configs" / "system_prompt.txt").write_text("Ancien prompt\n", encoding="utf-8")
    return tmp_path


def test_project_settings_read_and_update(tmp_path: Path, monkeypatch):
    from api.routes import projects
    root = _project(tmp_path)
    monkeypatch.setattr(projects, "project_dir", lambda _project_id: root)
    monkeypatch.setattr(projects, "require_ready", lambda _model: None)

    before = projects.get_settings("demo")
    assert before.system_prompt == "Ancien prompt"
    updated = projects.update_settings(UpdateProjectSettingsRequest(
        label="Support", project_type="business", purpose="Répondre aux clients",
        output_mode="json", inference_model="org/inference", system_prompt="Nouveau prompt",
        max_assistant_chars=2500,
    ), "demo")
    assert updated.label == "Support"
    assert updated.base_model == "org/base"
    assert updated.inference_model == "org/inference"
    assert updated.max_assistant_chars == 2500
    assert (root / "training/configs/system_prompt.txt").read_text(encoding="utf-8") == "Nouveau prompt\n"


def test_project_settings_skip_preflight_when_model_unchanged(tmp_path: Path, monkeypatch):
    from api.routes import projects
    root = _project(tmp_path)
    monkeypatch.setattr(projects, "project_dir", lambda _project_id: root)
    monkeypatch.setattr(projects, "require_ready", lambda _model: (_ for _ in ()).throw(AssertionError("unexpected")))
    current = projects.get_settings("demo")
    projects.update_settings(UpdateProjectSettingsRequest(**{
        key: value for key, value in current.model_dump().items() if key not in {"id", "base_model"}
    }), "demo")
