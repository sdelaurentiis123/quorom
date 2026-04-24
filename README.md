# Quorum

Adversarial academic paper review. Drop in a paper, a panel of six reviewer agents + three senior reviewers work in parallel, a verdict comes back.

Localhost-only. Design handoff at `../design_handoff_quorum/`.

## Setup

```bash
# One-time
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
make install
make sandbox-image

# Every session
make dev
```

Then open http://localhost:5173.

## Structure

```
backend/     FastAPI + Anthropic multi-agent orchestrator + Docker-sandboxed tools
frontend/    Vite + React + TS, SSE-driven UI
backend/sandbox/   Dockerfile for code-execution sandbox
```

## Tests

```bash
make test
```
