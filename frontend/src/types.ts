/* Mirrors backend/app/types.py one-for-one. */

export type Phase =
  | "idle"
  | "intake"
  | "reading"
  | "deliberation"
  | "converging"
  | "verdict";

export type TraceKind = "read" | "tool" | "think" | "flag" | "commit";
export type Sev = "high" | "med" | "low" | "note";
export type Seat = "a" | "b" | "c" | "d" | "e" | "f";
export type PersonaId = "METH" | "STAT" | "THRY" | "EMPR" | "HIST" | "STLM";
export type SeniorId = "CHAIR" | "SKEPTIC" | "METHOD";

export const PERSONA_IDS: PersonaId[] = ["METH", "STAT", "THRY", "EMPR", "HIST", "STLM"];
export const SENIOR_IDS: SeniorId[] = ["CHAIR", "SKEPTIC", "METHOD"];

export type Section = { id: string; title: string };

export type Paper = {
  id: string;
  title: string;
  authors: string;
  venue: string;
  abstract: string;
  sections: Section[];
  body?: string;
  body_format?: "markdown" | "text";
};

export type Persona = {
  id: PersonaId;
  seat: Seat;
  name: string;
  angle: string;
};

export type TraceEvent = {
  t: number;
  kind: TraceKind;
  text: string;
};

export type Finding = {
  id: string;
  sev: Sev;
  rank: number;
  title: string;
  text: string;
  section: string;
  cites: string[];
};

export type MinExperiment = {
  title: string;
  resolves: string[];
  cost: { gpu_hours: number; gpu_type: string; eval_sweeps: number };
  yaml: string;
};

/* SSE events — names match backend/app/bus.py publish payloads. */
export type SSEEvent =
  | { type: "phase.change"; phase: Phase }
  | { type: "paper.extracted"; paper: Paper }
  | { type: "vector.identified"; agent_id: PersonaId; angle: string }
  | { type: "agent.start"; agent_id: PersonaId }
  | { type: "agent.trace"; agent_id: PersonaId; trace: TraceEvent }
  | { type: "agent.finding"; agent_id: PersonaId; finding: Finding }
  | { type: "chair.trace"; trace: TraceEvent }
  | { type: "senior.start"; senior_id: SeniorId }
  | { type: "senior.progress"; senior_id: SeniorId; p: number }
  | { type: "senior.trace"; senior_id: SeniorId; trace: TraceEvent }
  | { type: "senior.signed"; senior_id: SeniorId }
  | { type: "senior.inconclusive"; senior_id: SeniorId }
  | { type: "verdict.trace"; trace: TraceEvent }
  | { type: "verdict.ready"; ranked: Finding[]; min_experiment: MinExperiment }
  | { type: "error"; where: string; message: string }
  | { type: "_overflow" }
  | { type: "_end" };

export type SSEEnvelope<E extends SSEEvent = SSEEvent> = E & {
  seq: number;
  session_id: string;
  ts: number;
};

/* Canonical persona roster for the UI. Ports prototype J_PERSONAS. */
export const PERSONAS: Persona[] = [
  { id: "METH", seat: "a", name: "The Methodologist", angle: "Experimental design, ablations, controls." },
  { id: "STAT", seat: "b", name: "The Statistician", angle: "Power, significance, confidence intervals." },
  { id: "THRY", seat: "c", name: "The Theorist", angle: "Mechanism, priors, first-principles." },
  { id: "EMPR", seat: "d", name: "The Empiricist", angle: "Replication, adjacent evidence, prior art." },
  { id: "HIST", seat: "e", name: "The Historian", angle: "Lineage of claims, precedent, negative results." },
  { id: "STLM", seat: "f", name: "The Steelman", angle: "Strongest version of the paper's argument." },
];

export const SENIORS = [
  { id: "CHAIR" as SeniorId, name: "Chair", angle: "Synthesizes and rules." },
  { id: "SKEPTIC" as SeniorId, name: "Senior Skeptic", angle: "Cross-examines upheld findings." },
  { id: "METHOD" as SeniorId, name: "Senior Methodologist", angle: "Independent methodology pass." },
];

export type Toast = {
  id: string;
  kind: "success" | "error" | "neutral";
  text: string;
};

/* UI state derived from SSE events. */
export type AgentSlice = {
  state: "queued" | "reading" | "done";
  traces: TraceEvent[];
  progress: number;
  finding: Finding | null;
};

export type SeniorSlice = {
  state: "queued" | "reviewing" | "signed" | "inconclusive";
  progress: number;
  traces: TraceEvent[];
};

export type ChairSlice = {
  traces: TraceEvent[];
};

export type SessionState = {
  sessionId: string | null;
  phase: Phase;
  paper: Paper | null;
  vectors: { agent_id: PersonaId; angle: string }[];
  agents: Partial<Record<PersonaId, AgentSlice>>;
  senior: Partial<Record<SeniorId, SeniorSlice>>;
  chair: ChairSlice;
  verdictTraces: TraceEvent[];
  verdict: { ranked: Finding[]; minExperiment: MinExperiment | null } | null;
  lastSeq: number;
  connectionState: "idle" | "connecting" | "open" | "reconnecting" | "closed";
  toasts: Toast[];
  selectedFindingId: string | null;
  intakeLog: string[];
  activeTab: "trace" | "verdict";
};
