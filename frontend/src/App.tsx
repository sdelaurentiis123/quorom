import { useSession } from "./session/useSession";
import { Masthead } from "./components/Masthead";
import { PhaseIdle } from "./components/PhaseIdle";
import { TopNav } from "./components/TopNav";
import { PaperPDF } from "./components/PaperPDF";
import { MarginRail } from "./components/MarginRail";
import { VerdictPage } from "./components/VerdictPage";
import { Toasts } from "./components/Toasts";
import { TopProgress } from "./components/TopProgress";
import "./App.css";

export default function App() {
  const { state, actions } = useSession();
  const inSession = state.phase !== "idle";
  const verdictReady = state.verdict !== null;

  return (
    <div className="app">
      <Toasts toasts={state.toasts} onDismiss={actions.dismissToast} />

      {!inSession ? (
        <PhaseIdle onConvene={actions.convene} />
      ) : (
        <>
          <Masthead sessionId={state.sessionId} phase={state.phase} />
          <TopNav
            phase={state.phase}
            activeTab={state.activeTab}
            verdictReady={verdictReady}
            onSetTab={actions.setTab}
          />
          <TopProgress
            phase={state.phase}
            verdictReady={verdictReady}
            verdictTraces={state.verdictTraces}
          />

          {state.activeTab === "verdict" ? (
            <VerdictPage
              verdict={state.verdict}
              verdictTraces={state.verdictTraces}
              phase={state.phase}
              paper={state.paper}
              sessionId={state.sessionId}
              selected={state.selectedFindingId}
              committedAgentIds={Object.entries(state.agents)
                .filter(([, slice]) => slice?.state === "done" && slice?.finding)
                .map(([id]) => id as import("./types").PersonaId)}
              onSelect={actions.selectFinding}
              onBackToTrace={() => actions.setTab("trace")}
            />
          ) : (
            <div className="grid">
              <PaperPDF paper={state.paper} sessionId={state.sessionId} />
              <MarginRail state={state} onSelect={actions.selectFinding} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
