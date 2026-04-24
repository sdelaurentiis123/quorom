"""TypedDicts mirroring frontend/src/types.ts one-for-one.

These are documentation + lint aid only; FastAPI does not validate them.
"""
from __future__ import annotations

from typing import Literal, TypedDict

Phase = Literal["idle", "intake", "reading", "deliberation", "converging", "verdict"]
TraceKind = Literal["read", "tool", "think", "flag", "commit"]
Sev = Literal["high", "med", "low", "note"]
Seat = Literal["a", "b", "c", "d", "e", "f"]
PersonaId = Literal["METH", "STAT", "THRY", "EMPR", "HIST", "STLM"]
SeniorId = Literal["CHAIR", "SKEPTIC", "METHOD"]

PERSONA_IDS: tuple[str, ...] = ("METH", "STAT", "THRY", "EMPR", "HIST", "STLM")
SENIOR_IDS: tuple[str, ...] = ("CHAIR", "SKEPTIC", "METHOD")


class Section(TypedDict):
    id: str
    title: str


class Paper(TypedDict, total=False):
    id: str
    title: str
    authors: str
    venue: str
    abstract: str
    sections: list[Section]
    body: str          # full-ish body text (markdown-ish); may be truncated
    body_format: str   # "markdown" or "text"


class Persona(TypedDict):
    id: str
    seat: Seat
    name: str
    angle: str


class TraceEvent(TypedDict):
    t: float
    kind: TraceKind
    text: str


class Finding(TypedDict):
    id: str
    sev: Sev
    rank: int
    title: str
    text: str
    section: str
    cites: list[str]


class Cost(TypedDict):
    gpu_hours: float
    gpu_type: str
    eval_sweeps: int


class MinExperiment(TypedDict):
    title: str
    resolves: list[str]
    cost: Cost
    yaml: str


# Canonical persona roster. Mirrors prototype's J_PERSONAS.
PERSONAS: list[Persona] = [
    {"id": "METH", "seat": "a", "name": "The Methodologist", "angle": "Experimental design, ablations, controls."},
    {"id": "STAT", "seat": "b", "name": "The Statistician", "angle": "Power, significance, confidence intervals."},
    {"id": "THRY", "seat": "c", "name": "The Theorist", "angle": "Mechanism, priors, first-principles."},
    {"id": "EMPR", "seat": "d", "name": "The Empiricist", "angle": "Replication, adjacent evidence, prior art."},
    {"id": "HIST", "seat": "e", "name": "The Historian", "angle": "Lineage of claims, precedent, negative results."},
    {"id": "STLM", "seat": "f", "name": "The Steelman", "angle": "Strongest version of the paper's argument."},
]

SENIORS = [
    {"id": "CHAIR", "name": "Chair", "angle": "Synthesizes and rules."},
    {"id": "SKEPTIC", "name": "Senior Skeptic", "angle": "Cross-examines upheld findings."},
    {"id": "METHOD", "name": "Senior Methodologist", "angle": "Independent methodology pass."},
]
