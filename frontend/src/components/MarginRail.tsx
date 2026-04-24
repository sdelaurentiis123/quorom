import { PERSONAS, type PersonaId, type SessionState, type SeniorId } from "../types";
import { AgentCard } from "./AgentCard";
import { ChairCard } from "./ChairCard";
import { SeniorLive } from "./SeniorLive";
import "./MarginRail.css";

export function MarginRail({
  state,
  onSelect,
}: {
  state: SessionState;
  onSelect: (id: string) => void;
}) {
  if (state.phase === "intake") {
    return (
      <div className="margin-rail rail-intake">
        <IntakeChecklist log={state.intakeLog} />
        {state.chair.traces.length > 0 && (
          <ChairCard traces={state.chair.traces} live={state.phase === "intake"} />
        )}
      </div>
    );
  }

  if (state.phase === "reading") {
    return (
      <div className="margin-rail rail-reading">
        <ChairCard traces={state.chair.traces} live={true} />
        <ReadingRail vectorIds={new Set(state.vectors.map((v) => v.agent_id))} />
      </div>
    );
  }

  if (state.phase === "converging") {
    return (
      <div className="margin-rail rail-cards">
        <div className="j-mono j-sc j-dim rail-label">senior panel</div>
        {(["CHAIR", "SKEPTIC", "METHOD"] as SeniorId[]).map((sid) => (
          <SeniorLive key={sid} sid={sid} slice={state.senior[sid]} />
        ))}
      </div>
    );
  }

  // Render cards ONLY for personas the Chair actually convened. Reading phase
  // emits vector.identified per chosen seat; STLM is force-appended downstream.
  // Without this filter the rail showed every seat from PERSONAS and un-convened
  // ones sat in "queued" forever — confusing ("5 agents but 1 never runs").
  const convenedIds = new Set(state.vectors.map((v) => v.agent_id));
  const convened = PERSONAS.filter((p) => convenedIds.has(p.id));

  return (
    <div className="margin-rail rail-cards">
      <div className="j-mono j-sc j-dim rail-label">
        margin · panel ({convened.length} reviewer{convened.length === 1 ? "" : "s"})
      </div>
      {convened.length === 0 && (
        <div className="j-dim j-mono j-tiny rail-empty">
          waiting for Chair to convene the panel…
        </div>
      )}
      {convened.map((p) => (
        <AgentCard
          key={p.id}
          persona={p}
          slice={state.agents[p.id]}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function IntakeChecklist({ log }: { log: string[] }) {
  const steps = [
    "parsing PDF",
    "detecting sections",
    "building citation graph",
    "indexing figures",
  ];
  const count = Math.min(steps.length, Math.max(1, log.length));
  return (
    <div>
      <div className="j-mono j-sc j-dim rail-label">intake</div>
      <div className="rail-heading j-serif">Extracting structure…</div>
      <div className="intake-list">
        {steps.map((s, i) => {
          const done = i < count;
          const live = i === count - 1;
          return (
            <div key={s} className={`intake-line j-mono ${done ? "intake-done" : "intake-pending"}`}>
              <span className="intake-tick j-dim">{done ? "✓" : "·"}</span>
              {s}
              {live && <span className="j-caret" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReadingRail({ vectorIds }: { vectorIds: Set<PersonaId> }) {
  return (
    <div>
      <div className="j-mono j-sc j-dim rail-label reading-subheading">panel seats</div>
      <div className="reading-list">
        {PERSONAS.map((p) => {
          const found = vectorIds.has(p.id);
          return (
            <div
              key={p.id}
              className={`reading-row ${found ? "reading-row-found" : ""}`}
              style={{ ["--seat" as string]: `var(--seat-${p.seat})` }}
            >
              <div className="j-mono j-sc reading-id">{p.id}</div>
              <div className="j-serif reading-angle">{found ? p.angle : "———————————"}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
