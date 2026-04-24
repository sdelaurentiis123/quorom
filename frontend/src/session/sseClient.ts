import type { SSEEnvelope } from "../types";

const EVENT_NAMES = [
  "phase.change",
  "paper.extracted",
  "vector.identified",
  "agent.start",
  "agent.trace",
  "agent.finding",
  "senior.start",
  "senior.progress",
  "senior.signed",
  "verdict.ready",
  "error",
  "_overflow",
  "_end",
];

export type ConnectOpts = {
  sessionId: string;
  sinceSeq: number;
  onEvent: (ev: SSEEnvelope) => void;
  onOverflow: () => void; // triggered on _overflow — caller reconnects
  onOpen: () => void;
  onError: () => void; // transport error; caller decides whether to retry
};

/**
 * Opens an EventSource for the given session. Returns a close function.
 *
 * Contract: on _overflow we close + invoke onOverflow so the caller can
 * reopen with since_seq = reducer.lastSeq. On any transport error we close
 * + invoke onError. The reducer's seq gate makes replay idempotent.
 */
export function connectStream(opts: ConnectOpts): () => void {
  const url = `/api/sessions/${opts.sessionId}/stream?since_seq=${opts.sinceSeq}`;
  const es = new EventSource(url);

  es.onopen = () => opts.onOpen();

  for (const name of EVENT_NAMES) {
    es.addEventListener(name, (m: MessageEvent) => {
      try {
        const data = JSON.parse(m.data) as SSEEnvelope;
        opts.onEvent(data);
        if (name === "_overflow") {
          es.close();
          opts.onOverflow();
        }
      } catch {
        // drop; a malformed event shouldn't kill the connection
      }
    });
  }

  es.onerror = () => {
    es.close();
    opts.onError();
  };

  return () => es.close();
}
