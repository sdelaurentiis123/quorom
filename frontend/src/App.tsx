import { useSession } from "./session/useSession";
import { Masthead } from "./components/Masthead";
import { PhaseIdle } from "./components/PhaseIdle";
import { TopNav } from "./components/TopNav";
import { PaperBody } from "./components/PaperBody";
import { MarginRail } from "./components/MarginRail";
import { VerdictPage } from "./components/VerdictPage";
import { Toasts } from "./components/Toasts";
import { VerdictComposing } from "./components/VerdictComposing";
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

          {state.activeTab === "verdict" && state.verdict ? (
            <VerdictPage
              verdict={state.verdict}
              paperTitle={state.paper?.title ?? ""}
              sessionId={state.sessionId}
              selected={state.selectedFindingId}
              onSelect={actions.selectFinding}
              onCopyYaml={actions.copyYaml}
              onBackToTrace={() => actions.setTab("trace")}
            />
          ) : (
            <div className="grid">
              <PaperBody paper={state.paper} vectors={state.vectors} />
              <MarginRail state={state} onSelect={actions.selectFinding} />
            </div>
          )}

          {state.phase === "verdict" && !state.verdict && (
            <VerdictComposing traces={state.verdictTraces} />
          )}
        </>
      )}
    </div>
  );
}
