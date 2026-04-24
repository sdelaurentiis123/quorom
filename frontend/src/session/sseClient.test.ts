import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectStream } from "./sseClient";

/** Minimal EventSource stub that records listeners + exposes fire() hooks. */
class MockEventSource {
  static last: MockEventSource | null = null;

  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.last = this;
    queueMicrotask(() => this.onopen?.());
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    (this.listeners[type] ||= []).push(fn);
  }
  close() { this.closed = true; }

  fire(type: string, payload: object) {
    const ev = new MessageEvent("message", { data: JSON.stringify(payload) });
    (this.listeners[type] || []).forEach((fn) => fn(ev));
  }
  triggerError() { this.onerror?.(); }
}

describe("sseClient", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", MockEventSource);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    MockEventSource.last = null;
  });

  it("registers event listeners and forwards parsed events", async () => {
    const events: unknown[] = [];
    const close = connectStream({
      sessionId: "s",
      sinceSeq: 0,
      onEvent: (e) => events.push(e),
      onOverflow: () => {},
      onOpen: () => {},
      onError: () => {},  // signature is (kind) => void, ignored for these tests
    });

    const es = MockEventSource.last!;
    es.fire("phase.change", { type: "phase.change", phase: "intake", seq: 1, session_id: "s", ts: 0 });
    es.fire("agent.trace", { type: "agent.trace", agent_id: "STAT", trace: { t: 0.1, kind: "think", text: "x" }, seq: 2, session_id: "s", ts: 0 });
    expect(events).toHaveLength(2);
    close();
    expect(es.closed).toBe(true);
  });

  it("sinceSeq is encoded in the URL", () => {
    connectStream({
      sessionId: "abc",
      sinceSeq: 42,
      onEvent: () => {},
      onOverflow: () => {},
      onOpen: () => {},
      onError: () => {},  // signature is (kind) => void, ignored for these tests
    });
    expect(MockEventSource.last!.url).toBe("/api/sessions/abc/stream?since_seq=42");
  });

  it("_overflow triggers onOverflow and closes the stream", () => {
    let overflowed = false;
    connectStream({
      sessionId: "s",
      sinceSeq: 0,
      onEvent: () => {},
      onOverflow: () => { overflowed = true; },
      onOpen: () => {},
      onError: () => {},  // signature is (kind) => void, ignored for these tests
    });
    const es = MockEventSource.last!;
    es.fire("_overflow", { type: "_overflow", seq: 99, session_id: "s", ts: 0 });
    expect(overflowed).toBe(true);
    expect(es.closed).toBe(true);
  });

  it("transport error invokes onError and closes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 500 }));
    let kind: string | null = null;
    connectStream({
      sessionId: "s",
      sinceSeq: 0,
      onEvent: () => {},
      onOverflow: () => {},
      onOpen: () => {},
      onError: (k) => { kind = k; },
    });
    const es = MockEventSource.last!;
    es.triggerError();
    await new Promise((r) => setTimeout(r, 5));
    expect(kind).toBe("transient");
    expect(es.closed).toBe(true);
  });

  it("onError reports not_found when backend returns 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404 }));
    let kind: string | null = null;
    connectStream({
      sessionId: "missing",
      sinceSeq: 0,
      onEvent: () => {},
      onOverflow: () => {},
      onOpen: () => {},
      onError: (k) => { kind = k; },
    });
    const es = MockEventSource.last!;
    es.triggerError();
    await new Promise((r) => setTimeout(r, 5));
    expect(kind).toBe("not_found");
  });

  it("drops malformed event payloads without dying", () => {
    const events: unknown[] = [];
    connectStream({
      sessionId: "s",
      sinceSeq: 0,
      onEvent: (e) => events.push(e),
      onOverflow: () => {},
      onOpen: () => {},
      onError: () => {},  // signature is (kind) => void, ignored for these tests
    });
    const es = MockEventSource.last!;
    // Fire a malformed payload: the stub's fire() calls JSON.parse on data.
    // Simulate by directly calling the listener with bad JSON.
    const listeners = (es as unknown as { listeners: Record<string, ((e: MessageEvent) => void)[]> }).listeners;
    const phaseListeners = listeners["phase.change"];
    phaseListeners[0](new MessageEvent("message", { data: "not-json-{" }));
    // Normal event after bad one — should still flow.
    es.fire("phase.change", { type: "phase.change", phase: "intake", seq: 1, session_id: "s", ts: 0 });
    expect(events).toHaveLength(1);
  });
});
