import type { Sev } from "../types";
import "./SevBadge.css";

const LABEL: Record<Sev, string> = {
  high: "HIGH",
  med: "MED",
  low: "LOW",
  note: "NOTE",
};

export function SevBadge({ sev }: { sev: Sev }) {
  return <span className={`sev-badge sev-${sev} j-mono`}>{LABEL[sev]}</span>;
}
