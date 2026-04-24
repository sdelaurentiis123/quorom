import type {
  AgentSlice,
  PersonaId,
  SessionState,
  SSEEnvelope,
  SSEEvent,
  SeniorId,
  Toast,
} from "../types";
import { PERSONA_IDS, SENIOR_IDS } from "../types";

export const initialState: SessionState = {
  sessionId: null,
  phase: "idle",
  paper: null,
  vectors: [],
  agents: {},
  senior: {},
  chair: { traces: [] },
  verdictTraces: [],
  verdict: null,
  lastSeq: 0,
  connectionState: "idle",
  toasts: [],
  selectedFindingId: null,
  intakeLog: [],
  activeTab: "trace",
};

function emptyAgent(): AgentSlice {
  return { state: "queued", traces: [], progress: 0, finding: null };
}

/**
 * Asymptotic progress derivation — addresses the "no deterministic trace count"
 * problem. Feels meaningful without lying about ETA. 2 traces → 0.22, 10 → 0.63.
 */
export function deriveAgentProgress(a: AgentSlice): number {
  if (a.state === "done") return 1;
  if (a.state === "queued") return 0;
  const n = a.traces.length;
  return 1 - Math.pow(0.93, n);
}

function patchAgent(
  state: SessionState,
  id: PersonaId,
  patch: (a: AgentSlice) => AgentSlice,
): SessionState {
  const existing = state.agents[id] ?? emptyAgent();
  const next = patch(existing);
  return { ...state, agents: { ...state.agents, [id]: next } };
}

function patchSenior(
  state: SessionState,
  id: SeniorId,
  patch: (s: NonNullable<SessionState["senior"][SeniorId]>) => NonNullable<SessionState["senior"][SeniorId]>,
): SessionState {
  const existing = state.senior[id] ?? { state: "queued" as const, progress: 0, traces: [] };
  const next = patch(existing);
  return { ...state, senior: { ...state.senior, [id]: next } };
}

function pushToast(state: SessionState, toast: Toast): SessionState {
  return { ...state, toasts: [...state.toasts.slice(-2), toast] };
}

/** Events we dispatch internally (not from SSE wire). */
export type InternalAction =
  | { type: "@@convened"; sessionId: string }
  | { type: "@@connection"; status: SessionState["connectionState"] }
  | { type: "@@toast"; toast: Toast }
  | { type: "@@dismiss-toast"; id: string }
  | { type: "@@select-finding"; findingId: string | null }
  | { type: "@@set-tab"; tab: "trace" | "verdict" }
  | { type: "@@reset" };

export type Action = SSEEnvelope | InternalAction;

export function reduce(state: SessionState, action: Action): SessionState {
  // Internal actions bypass the seq gate.
  if (action.type.startsWith("@@")) {
    const a = action as InternalAction;
    switch (a.type) {
      case "@@convened":
        return { ...initialState, sessionId: a.sessionId, connectionState: "connecting" };
      case "@@connection":
        return { ...state, connectionState: a.status };
      case "@@toast":
        return pushToast(state, a.toast);
      case "@@dismiss-toast":
        return { ...state, toasts: state.toasts.filter((t) => t.id !== a.id) };
      case "@@select-finding":
        return { ...state, selectedFindingId: a.findingId };
      case "@@set-tab":
        return { ...state, activeTab: a.tab };
      case "@@reset":
        return initialState;
    }
  }

  // Seq gate for idempotent replay. Control events (_overflow, _end) bypass.
  const env = action as SSEEnvelope;
  if (typeof env.seq === "number" && env.seq <= state.lastSeq && !env.type.startsWith("_")) {
    return state;
  }
  const withSeq = (s: SessionState): SessionState =>
    typeof env.seq === "number" ? { ...s, lastSeq: env.seq } : s;

  const ev = env as unknown as SSEEvent;
  switch (ev.type) {
    case "phase.change": {
      const logLine = phaseLogLine(ev.phase);
      // Auto-flip to verdict tab the moment the panel enters the verdict phase.
      // We want the composing state visible immediately — not stuck on the trace
      // view while the report generates in the background.
      const activeTab = ev.phase === "verdict" ? "verdict" : state.activeTab;
      return withSeq({
        ...state,
        phase: ev.phase,
        activeTab,
        intakeLog: logLine ? [...state.intakeLog, logLine] : state.intakeLog,
      });
    }
    case "paper.extracted":
      return withSeq({ ...state, paper: ev.paper });
    case "vector.identified": {
      const id = ev.agent_id as PersonaId;
      const vectors = [...state.vectors, { agent_id: id, angle: ev.angle }];
      const agents = { ...state.agents, [id]: state.agents[id] ?? emptyAgent() };
      return withSeq({ ...state, vectors, agents });
    }
    case "agent.start":
      return withSeq(patchAgent(state, ev.agent_id, (a) => ({ ...a, state: "reading" })));
    case "agent.trace": {
      const id = ev.agent_id;
      const existing = state.agents[id] ?? emptyAgent();
      const next: AgentSlice = {
        ...existing,
        state: existing.state === "done" ? "done" : "reading",
        traces: [...existing.traces, ev.trace],
      };
      next.progress = deriveAgentProgress(next);
      return withSeq(patchAgent(state, id, () => next));
    }
    case "agent.finding":
      return withSeq(
        patchAgent(state, ev.agent_id, (a) => ({
          ...a,
          state: "done",
          progress: 1,
          finding: ev.finding,
        })),
      );
    case "senior.start":
      return withSeq(patchSenior(state, ev.senior_id, (s) => ({ ...s, state: "reviewing" })));
    case "senior.progress":
      return withSeq(patchSenior(state, ev.senior_id, (s) => ({ ...s, progress: ev.p })));
    case "senior.trace":
      return withSeq(patchSenior(state, ev.senior_id, (s) => ({ ...s, traces: [...s.traces, ev.trace] })));
    case "senior.signed":
      return withSeq(patchSenior(state, ev.senior_id, (s) => ({ ...s, state: "signed", progress: 1 })));
    case "senior.inconclusive":
      return withSeq(patchSenior(state, ev.senior_id, (s) => ({ ...s, state: "inconclusive", progress: 1 })));
    case "chair.trace":
      return withSeq({ ...state, chair: { traces: [...state.chair.traces, ev.trace] } });
    case "verdict.trace":
      return withSeq({ ...state, verdictTraces: [...state.verdictTraces, ev.trace] });
    case "verdict.ready": {
      return withSeq({
        ...state,
        verdict: {
          ranked: ev.ranked,
          recommendedExperiment: ev.recommended_experiment ?? null,
          reportMarkdown: ev.report_markdown ?? "",
        },
        activeTab: "verdict",
      });
    }
    case "error":
      return withSeq(
        pushToast(state, {
          id: `err-${env.seq ?? Date.now()}`,
          kind: "error",
          text: ev.message || ev.where || "unknown error",
        }),
      );
    case "_overflow":
      // Trigger handled in sseClient (close+reconnect); reducer just no-ops.
      return state;
    case "_end":
      return { ...state, connectionState: "closed" };
    default:
      return state;
  }
}

/* Ensures all personas + seniors exist as known keys so the intake log
   can initialize without ragged conditionals downstream. */
export function ensureRostered(state: SessionState): SessionState {
  const agents = { ...state.agents };
  for (const id of PERSONA_IDS) if (!agents[id]) agents[id] = emptyAgent();
  const senior = { ...state.senior };
  for (const id of SENIOR_IDS) if (!senior[id]) senior[id] = { state: "queued", progress: 0, traces: [] };
  return { ...state, agents, senior };
}

function phaseLogLine(phase: SessionState["phase"]): string | null {
  switch (phase) {
    case "intake": return "› parsing paper structure…";
    case "reading": return "› orchestrator reading manuscript…";
    case "deliberation": return "› panel convened; 6 reviewers working";
    case "converging": return "› senior seats reconciling";
    case "verdict": return "✓ verdict ready";
    default: return null;
  }
}
