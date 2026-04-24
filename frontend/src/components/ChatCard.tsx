import { useEffect, useRef, useState } from "react";
import type { PersonaId } from "../types";
import { PERSONAS } from "../types";
import "./ChatCard.css";

type ChatTarget = "all" | PersonaId;
type ChatBubble = {
  id: string;
  role: "user" | "assistant";
  agent_id?: string; // for assistant bubbles: which agent, or CHAIR for swarm
  text: string;
  streaming?: boolean;
};

export function ChatCard({
  sessionId,
  committedAgentIds,
}: {
  sessionId: string | null;
  committedAgentIds: PersonaId[];
}) {
  const [target, setTarget] = useState<ChatTarget>("all");
  const [input, setInput] = useState("");
  const [threads, setThreads] = useState<Partial<Record<ChatTarget, ChatBubble[]>>>({ all: [] });
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // autoscroll on new content
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [threads, target]);

  const bubbles: ChatBubble[] = threads[target] || [];

  const targets: ChatTarget[] = ["all", ...committedAgentIds];

  const addBubble = (t: ChatTarget, b: ChatBubble) =>
    setThreads((prev) => ({ ...prev, [t]: [...(prev[t] || []), b] }));
  const patchLastAgent = (t: ChatTarget, agentId: string, mutate: (b: ChatBubble) => ChatBubble) =>
    setThreads((prev) => {
      const arr = [...(prev[t] || [])];
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i].role === "assistant" && arr[i].agent_id === agentId) {
          arr[i] = mutate(arr[i]);
          return { ...prev, [t]: arr };
        }
      }
      return prev;
    });

  const send = async () => {
    if (!sessionId || !input.trim() || busy) return;
    const msg = input.trim();
    setInput("");
    setBusy(true);
    addBubble(target, { id: `u-${Date.now()}`, role: "user", text: msg });

    const activeAgents = new Set<string>();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const resp = await fetch(`/api/sessions/${sessionId}/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target, message: msg }),
        signal: ac.signal,
      });
      if (!resp.ok || !resp.body) {
        addBubble(target, {
          id: `err-${Date.now()}`,
          role: "assistant",
          agent_id: "ERR",
          text: `chat failed: ${resp.status}`,
        });
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // SSE frames: each \n\n-separated frame has "event: X\ndata: {...}"
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const evLine = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const dataLine = frame.match(/^data:\s*(.+)$/m)?.[1]?.trim();
          if (!evLine || !dataLine) continue;
          if (evLine === "chat.finished") continue;
          let payload: { agent_id?: string; delta?: string; text?: string; message?: string } = {};
          try { payload = JSON.parse(dataLine); } catch { continue; }
          const agent = payload.agent_id || "?";
          if (evLine === "chat.start") {
            if (!activeAgents.has(agent)) {
              activeAgents.add(agent);
              addBubble(target, {
                id: `a-${agent}-${Date.now()}`,
                role: "assistant",
                agent_id: agent,
                text: "",
                streaming: true,
              });
            }
          } else if (evLine === "chat.token") {
            patchLastAgent(target, agent, (b) => ({ ...b, text: b.text + (payload.delta || "") }));
          } else if (evLine === "chat.done") {
            patchLastAgent(target, agent, (b) => ({ ...b, text: payload.text || b.text, streaming: false }));
          } else if (evLine === "chat.error") {
            patchLastAgent(target, agent, (b) => ({
              ...b,
              text: (b.text || "") + `\n[error: ${payload.message || "?"}]`,
              streaming: false,
            }));
          }
        }
      }
    } catch {
      // network / aborted — quiet; streaming state will end
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  return (
    <section className="chat-card">
      <header className="chat-card-head">
        <div className="j-mono j-sc chat-card-label">chat with panel</div>
        <div className="chat-card-tabs" role="tablist">
          {targets.map((t) => {
            const persona = t === "all" ? null : PERSONAS.find((p) => p.id === t);
            const label = t === "all" ? "swarm" : t;
            const seat = persona?.seat ?? "a";
            return (
              <button
                key={t}
                className={`chat-tab ${target === t ? "is-active" : ""}`}
                style={t === "all" ? {} : { ["--seat" as string]: `var(--seat-${seat})` }}
                onClick={() => setTarget(t as ChatTarget)}
                role="tab"
                aria-selected={target === t}
              >
                <span className="j-mono j-sc chat-tab-label">{label}</span>
              </button>
            );
          })}
        </div>
      </header>

      <div className="chat-card-messages" ref={scrollRef}>
        {bubbles.length === 0 && (
          <div className="chat-empty j-serif j-dim">
            Ask the {target === "all" ? "panel" : target} anything about the paper or their review.
          </div>
        )}
        {bubbles.map((b) => (
          <Bubble key={b.id} bubble={b} />
        ))}
      </div>

      <form
        className="chat-card-input"
        onSubmit={(e) => { e.preventDefault(); void send(); }}
      >
        <textarea
          className="chat-input j-serif"
          placeholder={target === "all" ? "ask the whole swarm…" : `ask ${target}…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void send();
            }
          }}
          rows={2}
          disabled={!sessionId}
        />
        <button
          type="submit"
          className="btn btn-primary j-mono j-sc chat-send"
          disabled={!sessionId || busy || !input.trim()}
        >
          {busy ? "…" : "send"}
        </button>
      </form>
    </section>
  );
}

function Bubble({ bubble }: { bubble: ChatBubble }) {
  if (bubble.role === "user") {
    return (
      <div className="chat-bubble chat-bubble-user j-serif">{bubble.text}</div>
    );
  }
  const persona = PERSONAS.find((p) => p.id === bubble.agent_id);
  const seat = persona?.seat ?? "a";
  const displayId = bubble.agent_id === "CHAIR" ? "CHAIR" : bubble.agent_id || "?";
  return (
    <div
      className="chat-bubble chat-bubble-agent"
      style={{ ["--seat" as string]: `var(--seat-${seat})` }}
    >
      <div className="chat-bubble-head">
        <span className="j-mono j-sc chat-bubble-id">{displayId}</span>
        {bubble.streaming && <span className="chat-bubble-streaming j-mono j-tiny j-dim">·····</span>}
      </div>
      <div className="chat-bubble-text j-serif">
        {bubble.text}
        {bubble.streaming && <span className="j-caret" />}
      </div>
    </div>
  );
}
