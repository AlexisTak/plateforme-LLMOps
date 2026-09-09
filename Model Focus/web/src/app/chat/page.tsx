"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, PageHeader } from "@/components/ui";
import { useProject } from "@/lib/project-context";

type Turn = { role: "user" | "assistant"; content: string; ragChunks?: string[] };

// Mirrors docs/OUTPUT_SCHEMA.json's `intent` enum, for a human-readable label.
const INTENT_LABELS: Record<string, string> = {
  task_breakdown: "Découpage de tâches",
  next_action: "Prochaine action",
  prioritization: "Priorisation",
  overwhelm: "Surcharge",
  energy: "Niveau d'énergie",
  resume: "Reprise",
  capture: "Capture",
  safety_redirect: "Redirection sécurité",
};

type StructuredReply = {
  intent?: string;
  summary?: string;
  next_action?: { title?: string; duration_minutes?: number; difficulty?: string; tip?: string };
  tasks?: string[];
  tips?: string[]; // parallel to `tasks`, per docs/OUTPUT_SCHEMA.json
  needs_clarification?: boolean;
};

/** The model answers in JSON per docs/OUTPUT_SCHEMA.json for task/planning
 * requests (that's correct, trained behavior — see inference/router.py) but
 * this chat is meant for a human to read, not an app parsing structured
 * output. So: parse it here and render a readable card instead of dumping
 * raw JSON in the bubble. Anything that isn't valid/matching JSON just
 * falls back to plain text, unchanged. */
function parseStructuredReply(content: string): StructuredReply | null {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{")) return null;
  try {
    const obj = JSON.parse(trimmed);
    if (obj && typeof obj === "object" && typeof obj.intent === "string") return obj as StructuredReply;
  } catch {
    // not valid JSON — fall through to plain text rendering
  }
  return null;
}

function StructuredReplyCard({ reply }: { reply: StructuredReply }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs uppercase tracking-wide text-text-muted font-sans not-italic">
        {INTENT_LABELS[reply.intent ?? ""] ?? reply.intent}
      </p>
      {reply.summary && <p>{reply.summary}</p>}
      {reply.next_action?.title && (
        <div>
          <p>
            → {reply.next_action.title}
            {reply.next_action.duration_minutes != null && ` (${reply.next_action.duration_minutes} min)`}
          </p>
          {reply.next_action.tip && <p className="text-text-muted text-xs mt-0.5">💡 {reply.next_action.tip}</p>}
        </div>
      )}
      {reply.tasks && reply.tasks.length > 0 && (
        <ul className="list-disc list-inside space-y-1.5">
          {reply.tasks.map((t, i) => (
            <li key={i}>
              {t}
              {reply.tips?.[i] && <span className="block text-text-muted text-xs pl-4">💡 {reply.tips[i]}</span>}
            </li>
          ))}
        </ul>
      )}
      {reply.needs_clarification && <p className="text-accent">Une précision serait utile ici.</p>}
    </div>
  );
}

export default function ChatPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectChat key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectChat({ projectId }: { projectId: string }) {
  const [adapters, setAdapters] = useState<string[]>([]);
  const [adapter, setAdapter] = useState<string | null>(null);
  const [rag, setRag] = useState(false);
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preferences, setPreferences] = useState("");

  useEffect(() => {
    let active = true;
    api.chat.adapters(projectId).then((r) => {
      if (!active) return;
      setAdapters(r.adapters);
      try {
        const saved = localStorage.getItem(`biscuits-focus:adapter:${projectId}`);
        setAdapter(saved && r.adapters.includes(saved) ? saved : null);
      } catch { /* storage can be disabled; base model remains available */ }
      setReady(true);
    }).catch((e) => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [projectId]);

  const send = async () => {
    if (!input.trim() || busy || !ready) return;
    const message = input.trim();
    setTurns((t) => [...t, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const history = turns.slice(-12).map(({ role, content }) => ({ role, content }));
      const res = await api.chat.send(projectId, message, adapter, rag, undefined, history,
        preferences.trim() ? { preferences: preferences.trim() } : {});
      setTurns((t) => [...t, { role: "assistant", content: res.response, ragChunks: res.rag_chunks }]);
    } catch (e) {
      setTurns(turns);
      setInput(message);
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      <PageHeader
        title="Chat de test"
        description="Le chat conserve les derniers échanges. Le modèle choisi est mémorisé pour ce projet dans ce navigateur."
        action={
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm text-text-secondary cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rag}
                onChange={(e) => setRag(e.target.checked)}
                className="accent-[var(--accent)]"
              />
              RAG
            </label>
            <select
              value={adapter ?? ""}
              disabled={busy || !ready}
              aria-label="Modèle du projet"
              onChange={(e) => {
                setAdapter(e.target.value || null);
                try { localStorage.setItem(`biscuits-focus:adapter:${projectId}`, e.target.value); } catch { /* optional */ }
              }}
              className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
            >
              <option value="">base (sans LoRA)</option>
              {adapters.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        }
      />

      <details className="mt-3 text-sm text-text-secondary">
        <summary>Préférences pour cette conversation</summary>
        <textarea aria-label="Préférences" maxLength={1000} value={preferences}
          onChange={(e) => setPreferences(e.target.value)} disabled={busy}
          placeholder="Ex. : peu d'énergie, étapes de 5 minutes, réponses courtes…"
          className="w-full mt-2 rounded-md border border-border bg-surface p-2" />
      </details>
      {error && <p role="alert" className="mt-3 text-sm text-error">{error}</p>}

      <div className="flex-1 overflow-y-auto border border-border rounded-lg bg-surface p-4 space-y-3 mt-6">
        {turns.length === 0 && (
          <p className="text-text-muted text-sm text-center py-8">Envoie un message pour commencer.</p>
        )}
        {turns.map((t, i) => {
          const structured = t.role === "assistant" ? parseStructuredReply(t.content) : null;
          return (
            <div key={i} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-xl px-3.5 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
                  t.role === "user" ? "bg-accent-soft text-text-primary" : "bg-surface-hover text-text-primary border border-border"
                }`}
              >
                {structured ? <StructuredReplyCard reply={structured} /> : t.content}
                {t.ragChunks && t.ragChunks.length > 0 && (
                  <p className="mt-2 text-xs text-text-muted font-sans not-italic">📄 sources : {t.ragChunks.join(", ")}</p>
                )}
              </div>
            </div>
          );
        })}
        {busy && <p className="text-text-muted text-xs">…génération en cours</p>}
      </div>

      <div className="flex gap-2 mt-3">
        <input
          value={input}
          maxLength={8000}
          disabled={busy || !ready}
          aria-label="Message"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Écris un message…"
          className="flex-1 bg-surface border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
        />
        <Button variant="accent" onClick={send} disabled={busy || !ready || !input.trim()}>
          Envoyer
        </Button>
      </div>
    </div>
  );
}
