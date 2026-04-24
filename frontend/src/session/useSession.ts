import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, reduce, type Action } from "./reducer";
import { connectStream } from "./sseClient";
import type { SSEEnvelope } from "../types";

type ConvenePayload =
  | { kind: "arxiv"; id: string }
  | { kind: "pdf"; upload_id: string }
  | { kind: "demo" };

const RECONNECT_DELAY_MS = 1200;

export function useSession() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const closeRef = useRef<null | (() => void)>(null);
  const reconnectTimer = useRef<number | null>(null);
  const failureCount = useRef<number>(0);
  const MAX_RECONNECTS = 3;

  const openStream = useCallback((sessionId: string) => {
    const sinceSeq = stateRef.current.lastSeq;
    closeRef.current?.();
    const close = connectStream({
      sessionId,
      sinceSeq,
      onOpen: () => {
        failureCount.current = 0;
        dispatch({ type: "@@connection", status: "open" } as Action);
      },
      onEvent: (ev: SSEEnvelope) => dispatch(ev as Action),
      onOverflow: () => {
        dispatch({ type: "@@connection", status: "reconnecting" } as Action);
        openStream(sessionId);
      },
      onError: (kind) => {
        if (kind === "not_found") {
          // Session doesn't exist on this backend — stop reconnecting, clear state.
          dispatch({ type: "@@connection", status: "closed" } as Action);
          dispatch({
            type: "@@toast",
            toast: {
              id: `sess-gone-${Date.now()}`,
              kind: "neutral",
              text: "session ended — convene a new one",
            },
          } as Action);
          dispatch({ type: "@@reset" } as Action);
          return;
        }
        failureCount.current += 1;
        if (failureCount.current >= MAX_RECONNECTS) {
          dispatch({ type: "@@connection", status: "closed" } as Action);
          dispatch({
            type: "@@toast",
            toast: {
              id: `disc-${Date.now()}`,
              kind: "error",
              text: `disconnected from backend after ${MAX_RECONNECTS} attempts`,
            },
          } as Action);
          return;
        }
        dispatch({ type: "@@connection", status: "reconnecting" } as Action);
        if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = window.setTimeout(
          () => openStream(sessionId),
          RECONNECT_DELAY_MS * failureCount.current,
        );
      },
    });
    closeRef.current = close;
  }, []);

  const convene = useCallback(
    async (payload: ConvenePayload) => {
      dispatch({ type: "@@reset" } as Action);
      const resp = await fetch("/api/sessions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source: payload }),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        dispatch({
          type: "@@toast",
          toast: { id: `err-${Date.now()}`, kind: "error", text: `could not convene: ${text}` },
        } as Action);
        return;
      }
      const data = (await resp.json()) as { session_id: string };
      dispatch({ type: "@@convened", sessionId: data.session_id } as Action);
      openStream(data.session_id);
    },
    [openStream],
  );

  const selectFinding = useCallback(
    (findingId: string | null) =>
      dispatch({ type: "@@select-finding", findingId } as Action),
    [],
  );

  const setTab = useCallback(
    (tab: "trace" | "verdict") =>
      dispatch({ type: "@@set-tab", tab } as Action),
    [],
  );

  const dismissToast = useCallback(
    (id: string) => dispatch({ type: "@@dismiss-toast", id } as Action),
    [],
  );

  const copyYaml = useCallback(async (yaml: string) => {
    try {
      await navigator.clipboard.writeText(yaml);
      dispatch({
        type: "@@toast",
        toast: {
          id: `copy-${Date.now()}`,
          kind: "success",
          text: `experiment.yaml · ${new Blob([yaml]).size} bytes · copied`,
        },
      } as Action);
    } catch {
      dispatch({
        type: "@@toast",
        toast: { id: `copy-${Date.now()}`, kind: "error", text: "copy failed" },
      } as Action);
    }
  }, []);

  useEffect(() => {
    return () => {
      closeRef.current?.();
      if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
    };
  }, []);

  return {
    state,
    actions: { convene, selectFinding, dismissToast, copyYaml, setTab },
  };
}
