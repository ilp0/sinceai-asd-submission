"""Parse the pump manuals into numbered clauses and select the sections for a fault type."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent / "manuals"
SECTION_RE = re.compile(r"^## (\d+) (.+)$")
CLAUSE_RE = re.compile(r"^(\d+\.\d+) (.+)$")
CITE_RE = re.compile(r"\[(\d+\.\d+)\]")

# Fault type -> manual sections, most specific first. Section 4 (monitoring, alerts and escalation)
# is in every list; section 2 (safety) and 3 (limits) are in every machine-fault list.
FAULT_SECTIONS = {
    "BEARING_WEAR": [8, 3, 4, 2],
    "SUCTION_STRAINER_CLOGGING": [5, 6, 3, 4, 2, 15],
    "CAVITATION": [6, 5, 3, 4, 2],
    "DISCHARGE_RESTRICTION": [7, 3, 4, 2, 15],
    "MISALIGNMENT": [9, 8, 3, 4, 2],
    "IMBALANCE": [10, 9, 3, 4, 2],
    "IMPELLER_WEAR": [11, 6, 3, 4, 2],
    "AIR_ENTRAINMENT": [12, 6, 4, 2, 15],
    "SENSOR_DRIFT": [13, 4],
    "SENSOR_STUCK": [13, 4],
    "SENSOR_CALIBRATION_SHIFT": [13, 4],
    "SENSOR_NOISE_SPIKES": [13, 4],
    "COMMUNICATION_LOSS": [14, 4, 13],
}


@dataclass
class Section:
    num: int
    title: str
    clauses: dict[str, str] = field(default_factory=dict)


@dataclass
class Manual:
    asset_id: str
    title: str
    header: str
    note: str
    sections: dict[int, Section]

    def clause(self, cid: str) -> str | None:
        sec = self.sections.get(int(cid.split(".")[0]))
        return sec.clauses.get(cid) if sec else None

    def render(self, nums: list[int] | None = None) -> str:
        nums = nums or sorted(self.sections)
        out = [f"MANUAL: {self.title}", self.header, ""]
        for n in sorted(nums):
            s = self.sections[n]
            out.append(f"Section {n}: {s.title}")
            out += [f"[{cid}] {text}" for cid, text in s.clauses.items()]
            out.append("")
        return "\n".join(out).strip()

    def to_json(self) -> dict:
        return {
            "asset_id": self.asset_id, "title": self.title, "header": self.header, "note": self.note,
            "sections": [{"num": s.num, "title": s.title, "clauses": [{"id": k, "text": v} for k, v in s.clauses.items()]}
                         for s in self.sections.values()],
        }


@lru_cache
def load(asset_id: str) -> Manual:
    lines = (DIR / f"{asset_id}.md").read_text().splitlines()
    title = lines[0].lstrip("# ").strip()
    header, note = lines[2].strip(), lines[4].strip()
    sections: dict[int, Section] = {}
    cur = None
    for line in lines[5:]:
        if m := SECTION_RE.match(line):
            cur = sections.setdefault(int(m[1]), Section(int(m[1]), m[2].strip()))
        elif cur and (m := CLAUSE_RE.match(line)):
            cur.clauses[m[1]] = m[2].strip()
    return Manual(asset_id, title, header, note, sections)


def sections_for(fault_type: str) -> list[int]:
    return FAULT_SECTIONS.get(fault_type, [4, 2, 3])
