"""Runtime config — env vars, model IDs, caps."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)

# Load from repo-root .env (one up from backend/)
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
S2_API_KEY = os.environ.get("S2_API_KEY", "")

# Model IDs. Opus end-to-end for the reasoning agents. Prompt caching on the
# paper block keeps this inside Tier 1 limits: all 6 reviewers share the
# cached paper prefix, so per-reviewer incremental input is ~persona+user_msg
# (a few hundred tokens), not the full paper. Sectionize fallback stays on
# Haiku — it's a tiny one-shot.
MODEL_ORCHESTRATOR = "claude-opus-4-7"
MODEL_REVIEWER = "claude-opus-4-7"
MODEL_SENIOR = "claude-opus-4-7"
MODEL_VERDICT = "claude-opus-4-7"
MODEL_SECTIONIZE_FALLBACK = "claude-haiku-4-5"

# Parallelism cap. Tier 2 Opus: 1,000 RPM / 450k ITPM / 90k OTPM. 5 parallel
# reviewers fit comfortably — this is the actual "swarm" moment. Drop via
# QUORUM_REVIEWER_PARALLEL if the tier changes.
REVIEWER_PARALLEL = int(os.environ.get("QUORUM_REVIEWER_PARALLEL", "5"))

# Caps
REVIEWER_MAX_TURNS = 10
REVIEWER_MAX_TOKENS = 4096
ORCHESTRATOR_MAX_TOKENS = 2048
VERDICT_MAX_TOKENS = 3000
SENIOR_MAX_TOKENS = 2048

# Sandbox
SANDBOX_IMAGE = "quorum-sandbox:latest"
SANDBOX_CALL_TIMEOUT_S = 30
SANDBOX_DEGRADED = False  # flipped True at startup probe if Docker offline

# Session
SUBSCRIBER_QUEUE_MAX = 1024
BACKLOG_MAXLEN = 10_000
CANCEL_GRACE_S = 30.0

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
