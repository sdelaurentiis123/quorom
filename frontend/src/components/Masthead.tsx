import { useEffect, useState } from "react";
import type { Phase } from "../types";
import "./Masthead.css";

export function Masthead({ sessionId, phase }: { sessionId: string | null; phase: Phase }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (phase === "verdict" || phase === "idle") return;
    const t = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => window.clearInterval(t);
  }, [phase]);

  useEffect(() => {
    if (phase === "idle") setElapsed(0);
  }, [phase]);

  const right = sessionId
    ? `session ${sessionId.slice(0, 4)} · ${elapsed}s`
    : "no session";

  return (
    <div className="masthead">
      <div className="masthead-left">
        <span className="masthead-title j-serif">Quorum</span>
        <span className="masthead-sub j-mono j-sc j-dim">an academic panel for your paper</span>
      </div>
      <div className="masthead-right j-mono j-sc j-dim">{right}</div>
    </div>
  );
}
