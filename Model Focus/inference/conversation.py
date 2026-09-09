"""Bounded, alternating chat history; never accept a client-supplied system role."""


def build_messages(system_prompt: str, message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    pairs = []
    pending = None
    for turn in (history or [])[-12:]:
        role, content = turn.get("role"), turn.get("content", "")
        if not content.strip():
            continue
        if role == "user":
            pending = {"role": "user", "content": content}
        elif role == "assistant" and pending is not None:
            pairs.extend([pending, {"role": "assistant", "content": content}])
            pending = None
    return [{"role": "system", "content": system_prompt}, *pairs,
            {"role": "user", "content": message}]
