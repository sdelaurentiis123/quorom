import { describe, expect, it } from "vitest";
import { deriveAgentProgress, initialState, reduce } from "./reducer";
import type { AgentSlice, SSEEnvelope } from "../types";

function env<T extends { type: string }>(ev: T, seq: number, sessionId = "s"): SSEEnvelope {
  return { ...(ev as unknown as SSEEnvelope), seq, session_id: sessionId, ts: Date.now() };
}

describe("reducer", () => {
  it("advances phase on phase.change", () => {
    const s = reduce(initialState, env({ type: "phase.change", phase: "intake" }, 1));
    expect(s.phase).toBe("intake");
    expect(s.lastSeq).toBe(1);
  });

  it("stores paper on paper.extracted", () => {
    const paper = {
      id: "x",
      title: "t",
      authors: "a",
      venue: "v",
      abstract: "abs",
      sections: [{ id: "§1", title: "Intro" }],
    };
    const s = reduce(initialState, env({ type: "paper.extracted", paper }, 1));
    expect(s.paper).toEqual(paper);
  });

  it("creates agent slice on vector.identified", () => {
    const s = reduce(initialState, env({ type: "vector.identified", agent_id: "STAT", angle: "power" }, 1));
    expect(s.vectors).toHaveLength(1);
    expect(s.agents.STAT?.state).toBe("queued");
  });

  it("appends traces and updates progress asymptotically", () => {
    let s = initialState;
    s = reduce(s, env({ type: "vector.identified", agent_id: "STAT", angle: "x" }, 1));
    s = reduce(s, env({ type: "agent.start", agent_id: "STAT" }, 2));
    s = reduce(s, env({ type: "agent.trace", agent_id: "STAT", trace: { t: 0.1, kind: "read", text: "a" } }, 3));
    s = reduce(s, env({ type: "agent.trace", agent_id: "STAT", trace: { t: 0.2, kind: "think", text: "b" } }, 4));
    const p = s.agents.STAT!.progress;
    // 2 traces → 0.1351 (1 - 0.93^2)
    expect(p).toBeGreaterThan(0.12);
    expect(p).toBeLessThan(0.16);
  });

  it("replay of same seq is idempotent", () => {
    let s = initialState;
    s = reduce(s, env({ type: "vector.identified", agent_id: "STAT", angle: "x" }, 1));
    s = reduce(s, env({ type: "agent.trace", agent_id: "STAT", trace: { t: 0.1, kind: "read", text: "a" } }, 2));
    // Replay of seq 2 must not double-append.
    const replayed = reduce(s, env({ type: "agent.trace", agent_id: "STAT", trace: { t: 0.1, kind: "read", text: "a" } }, 2));
    expect(replayed.agents.STAT!.traces).toHaveLength(1);
  });

  it("senior.progress uses raw p value", () => {
    const s1 = reduce(initialState, env({ type: "senior.start", senior_id: "CHAIR" }, 1));
    const s2 = reduce(s1, env({ type: "senior.progress", senior_id: "CHAIR", p: 0.42 }, 2));
    expect(s2.senior.CHAIR?.progress).toBe(0.42);
  });

  it("senior.trace appends to senior slice traces", () => {
    let s = reduce(initialState, env({ type: "senior.start", senior_id: "CHAIR" }, 1));
    s = reduce(s, env({ type: "senior.trace", senior_id: "CHAIR", trace: { t: 0.3, kind: "think", text: "reading" } }, 2));
    expect(s.senior.CHAIR?.traces).toHaveLength(1);
    expect(s.senior.CHAIR?.traces[0].text).toBe("reading");
  });

  it("chair.trace accumulates chair traces", () => {
    const s = reduce(initialState, env({ type: "chair.trace", trace: { t: 0.1, kind: "read", text: "hello" } }, 1));
    expect(s.chair.traces).toHaveLength(1);
  });

  it("senior.inconclusive sets state and does not lie signed", () => {
    let s = reduce(initialState, env({ type: "senior.start", senior_id: "SKEPTIC" }, 1));
    s = reduce(s, env({ type: "senior.inconclusive", senior_id: "SKEPTIC" }, 2));
    expect(s.senior.SKEPTIC?.state).toBe("inconclusive");
  });

  it("verdict.ready flips activeTab to verdict", () => {
    const finding = { id: "STAT-1", sev: "high" as const, rank: 1, title: "t", text: "x", section: "§4", cites: [] };
    const exp = { title: "e", resolves: ["STAT-1"], cost: { gpu_hours: 10, gpu_type: "A100", eval_sweeps: 1 }, yaml: "y" };
    const s = reduce(initialState, env({ type: "verdict.ready", ranked: [finding], min_experiment: exp }, 1));
    expect(s.activeTab).toBe("verdict");
  });

  it("verdict.ready stores ranked + min_experiment", () => {
    const finding = { id: "STAT-1", sev: "high" as const, rank: 1, title: "t", text: "x", section: "§4", cites: [] };
    const exp = { title: "e", resolves: ["STAT-1"], cost: { gpu_hours: 10, gpu_type: "A100", eval_sweeps: 1 }, yaml: "y" };
    const s = reduce(initialState, env({ type: "verdict.ready", ranked: [finding], min_experiment: exp }, 1));
    expect(s.verdict?.ranked[0].id).toBe("STAT-1");
    expect(s.verdict?.minExperiment?.title).toBe("e");
  });

  it("error event surfaces a toast", () => {
    const s = reduce(initialState, env({ type: "error", where: "parse", message: "boom" }, 1));
    expect(s.toasts).toHaveLength(1);
    expect(s.toasts[0].kind).toBe("error");
  });
});

describe("deriveAgentProgress", () => {
  it("returns 0 when queued, 1 when done, asymptotic while reading", () => {
    const q: AgentSlice = { state: "queued", traces: [], progress: 0, finding: null };
    expect(deriveAgentProgress(q)).toBe(0);

    const d: AgentSlice = { state: "done", traces: [], progress: 1, finding: null };
    expect(deriveAgentProgress(d)).toBe(1);

    const r: AgentSlice = {
      state: "reading",
      traces: Array.from({ length: 10 }, (_, i) => ({ t: i / 10, kind: "think" as const, text: "" })),
      progress: 0,
      finding: null,
    };
    const p = deriveAgentProgress(r);
    expect(p).toBeGreaterThan(0.5);
    expect(p).toBeLessThan(0.75);
  });
});
