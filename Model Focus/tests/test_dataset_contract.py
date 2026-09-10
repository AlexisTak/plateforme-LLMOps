"""Fast, CPU-only tests for the dataset contract and the split logic.

These are the tests Jenkins runs on every build (`pytest -m "not gpu"`). Nothing
here loads a model — the whole file should stay under a few seconds so there is
never a reason to skip it.

Covers the two things that silently corrupt an experiment if they break:
  - validate_dataset's rules (a malformed example that slips through ends up in
    training data)
  - prepare_dataset's split (a leak between train and test makes every eval
    number meaningless, and nothing downstream would notice)
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import prepare_dataset as prepare_mod
from scripts import validate_dataset as validate_mod


def _example(user: str = "Je suis débordé", assistant: str = "On découpe en trois.") -> dict:
    return {"messages": [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]}


def _levels(findings) -> list[str]:
    return [f.level for f in findings]


# --- validate_dataset -------------------------------------------------------


def test_valid_example_produces_no_error():
    findings = validate_mod.validate_example(_example(), "test.jsonl", 1)
    assert "error" not in _levels(findings)


def test_missing_messages_key_is_an_error():
    findings = validate_mod.validate_example({"text": "nope"}, "test.jsonl", 1)
    assert "error" in _levels(findings)


def test_empty_messages_list_is_an_error():
    findings = validate_mod.validate_example({"messages": []}, "test.jsonl", 1)
    assert "error" in _levels(findings)


def test_message_missing_role_is_an_error():
    obj = {"messages": [{"content": "orphan message"}]}
    findings = validate_mod.validate_example(obj, "test.jsonl", 1)
    assert "error" in _levels(findings)


def test_medical_claim_in_assistant_turn_is_flagged():
    """The safety boundary of the whole project: the model must never assert a
    diagnosis, so such an example must never reach the training data."""
    findings = validate_mod.validate_example(
        _example(assistant="D'apres ce que tu decris, tu as un TDAH."), "test.jsonl", 1
    )
    assert findings, "a diagnosis claim in an assistant turn was not flagged at all"


def test_domain_neutral_project_can_disable_medical_specific_validation():
    findings = validate_mod.validate_example(
        _example(assistant="Je te diagnostique une panne du service HTTP."),
        "developer.jsonl",
        1,
        medical_safety=False,
        max_assistant_chars=8000,
    )
    assert "error" not in _levels(findings)


def test_example_key_is_stable_and_distinguishes_content():
    a = validate_mod.example_key(_example())
    b = validate_mod.example_key(_example())
    c = validate_mod.example_key(_example(user="Autre chose"))
    assert a == b, "same content must hash identically (dedupe relies on this)"
    assert a != c


def test_near_duplicate_scan_finds_close_text_without_false_positive():
    examples = [
        (_example(user="Je suis débordé par toutes mes tâches aujourd'hui"), "a.jsonl", 1),
        (_example(user="Je suis débordé par toutes mes tâches aujourd’hui !"), "b.jsonl", 2),
        (_example(user="Comment préparer un gâteau au chocolat ?", assistant="Mélange les ingrédients."), "c.jsonl", 3),
    ]

    pairs, skipped = validate_mod.find_near_duplicates(examples, threshold=0.85)

    assert not skipped
    assert [(pair[0], pair[2]) for pair in pairs] == [("a.jsonl", "b.jsonl")]


def test_near_duplicate_scan_handles_a_dashboard_sized_dataset_quickly():
    examples = [
        (_example(user=hashlib.sha256(f"user-{i}".encode()).hexdigest(), assistant=hashlib.sha256(f"assistant-{i}".encode()).hexdigest()), "data.jsonl", i + 1)
        for i in range(600)
    ]

    pairs, skipped = validate_mod.find_near_duplicates(examples)

    assert not skipped
    assert pairs == []


# --- prepare_dataset --------------------------------------------------------


def _corpus(n_per_category: int = 12) -> list[tuple[dict, str]]:
    categories = ["tasks", "overwhelm", "planning", "safety"]
    return [
        (_example(user=f"{cat} prompt {i}"), cat)
        for cat in categories
        for i in range(n_per_category)
    ]


def test_split_keeps_every_example():
    corpus = _corpus()
    train, val, test = prepare_mod.stratified_split(corpus, seed=42)
    assert len(train) + len(val) + len(test) == len(corpus)


def test_split_has_no_leakage_between_train_and_test():
    """A duplicate across train/test inflates every eval metric and no downstream
    step would catch it — this is the single most damaging silent failure here."""
    train, val, test = prepare_mod.stratified_split(_corpus(), seed=42)
    train_keys = {validate_mod.example_key(o) for o in train}
    test_keys = {validate_mod.example_key(o) for o in test}
    val_keys = {validate_mod.example_key(o) for o in val}
    assert not (train_keys & test_keys), "example present in both train and test"
    assert not (train_keys & val_keys), "example present in both train and validation"


def test_split_is_deterministic_for_a_given_seed():
    a_train, _, a_test = prepare_mod.stratified_split(_corpus(), seed=42)
    b_train, _, b_test = prepare_mod.stratified_split(_corpus(), seed=42)
    assert [validate_mod.example_key(o) for o in a_train] == [validate_mod.example_key(o) for o in b_train]
    assert [validate_mod.example_key(o) for o in a_test] == [validate_mod.example_key(o) for o in b_test]
