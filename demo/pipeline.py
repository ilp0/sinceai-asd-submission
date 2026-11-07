"""Alert -> manual sections -> cited guide -> citation check -> accepted guide (or fallback summary).

1. The fault type of the alert selects the manual sections (manuals.FAULT_SECTIONS).
2. The writer LLM gets the alert and these sections, and writes a guide in which each action cites clauses.
3. The checker LLM (same model, same sections) checks each cited claim and returns a structured verdict.
   The code also rejects a clause number that is not in the given sections, and an action without a citation.
4. Rejected: back to step 2 with the checker feedback. Two rejections in a row: the LLM writes only a
   summary of the alert and the values, without advice.
"""

from __future__ import annotations

import json
import re
import time
from typing import Iterator

import llm
import manuals

MAX_ATTEMPTS = llm.CONFIG.get("max_attempts", 2)
CID = {"type": "string", "pattern": "^[0-9]{1,2}\\.[0-9]{1,2}$"}

GUIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "maxLength": 400},
        "actions": {
            "type": "array", "minItems": 3, "maxItems": 5,
            "items": {"type": "object", "properties": {
                "text": {"type": "string", "maxLength": 300},
                "citations": {"type": "array", "minItems": 1, "maxItems": 2, "items": CID},
            }, "required": ["text", "citations"]},
        },
        "escalate_if": {"type": "object", "properties": {
            "text": {"type": "string", "maxLength": 300},
            "citations": {"type": "array", "minItems": 1, "maxItems": 3, "items": CID},
        }, "required": ["text", "citations"]},
    },
    "required": ["summary", "actions", "escalate_if"],
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "claim": {"type": "string", "maxLength": 12},
                "reason": {"type": "string", "maxLength": 300},
                "supported": {"type": "boolean"},
            }, "required": ["claim", "reason", "supported"]},
        },
        "feedback": {"type": "string", "maxLength": 700},
    },
    "required": ["checks", "feedback"],
}

SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string", "maxLength": 700}}, "required": ["summary"]}

WRITER_SYSTEM = """You are the maintenance assistant in a pump condition-monitoring system.
A fault model raised an alert. Write a short guide for the duty engineer from the MANUAL EXCERPT only.

Rules:
- Each action is one short sentence that does one thing. Take the wording from the clause that you cite.
- Cite one or two clause numbers per action, for example "5.3". Cite only clause numbers that appear in square brackets in the excerpt.
- Every part of an action must be stated in a cited clause. If a step needs a second clause, write a second action.
- Use only limits and intervals that are written in the cited clauses. If an action uses a limit from one clause and a step from another clause, cite both.
- The alert is a probable fault, not a confirmed diagnosis. Order: checks first, then corrective work with its safety steps, then verification.
- Call the pump only by its asset ID from the ALERT data (for example PUMP-08). Do not use other pump or site names.
- summary: one or two sentences. Say what the alert means for this pump and which measured value supports it. Use the values of the ALERT data exactly.
- actions: three to five steps.
- escalate_if: one sentence. Take the condition from a limit clause and the action from an escalation or changeover clause, and cite both.

Example of the style (from another manual):
Excerpt: [21.4] Check the oil level in the sight glass every watch. [21.5] Add oil of grade VG68 when the level is below the mark.
Action: {"text": "Check the oil level in the sight glass.", "citations": ["21.4"]}
Action: {"text": "If the level is below the mark, add VG68 oil.", "citations": ["21.5"]}"""

CHECKER_SYSTEM = """You are the citation checker of a maintenance system. You get the ALERT data, a MANUAL EXCERPT and numbered CLAIMS.
Each claim cites clauses of the manual in square brackets.

For each claim:
- Read the text of each cited clause in the excerpt.
- reason: one short sentence (at most 25 words) that compares the claim with the cited clause text.
- supported = true if the cited clauses together state the action of the claim. A paraphrase or a shorter form is correct.
- The ALERT data are facts. A claim can mention them (pump name, measured values, the alert) without a citation.
- A claim that starts with "Escalate if" is supported if its condition is in a cited clause or in the ALERT data, and its action (for example start the standby pump, stop the pump, call the engineer) is in a cited clause. The two clauses do not have to refer to each other.
- supported = false if a cited clause is about a different subject, if the claim contains a step that no cited clause contains, or if the claim states a limit or interval that differs from the clause.

feedback: if a claim is not supported, tell the writer how to correct it and which clause to use. If all claims are supported, write "OK"."""

SUMMARY_SYSTEM = """You are the maintenance assistant in a pump condition-monitoring system.
The advice of the system could not be verified against the manual. Do not give advice or actions.
Write a factual summary in two or three sentences: which pump (by its asset ID only), which probable fault and with which probability,
and which measured values differ from the baseline. Use only the ALERT data."""


def _fmt(v, unit=""):
    if v is None:
        return "no data"
    return f"{v:g} {unit}".strip()


def alert_text(alert: dict) -> str:
    lines = [
        "ALERT",
        f"Pump: {alert['asset_id']}",
        f"Time: {alert['time']}",
        f"Probable fault: {alert['fault_type']} ({alert['event_class'].lower()} fault), model probability {alert['confidence']:.2f}",
        f"Strongest evidence signal: {alert.get('evidence_signal') or 'not given'}",
        f"Alert rule: {alert['rule']}",
        "Measured values (mean of the last 15 min) against the baseline (median of the first 24 h while running):",
    ]
    for v in alert["values"]:
        d = "" if v["delta_pct"] is None else f" ({v['delta_pct']:+.1f} %)"
        lines.append(f"- {v['label']}: {_fmt(v['now'], v['unit'])}, baseline {_fmt(v['baseline'], v['unit'])}{d}")
    if alert.get("other_probabilities"):
        lines.append("Other fault probabilities: " + ", ".join(f"{o['fault_type']} {o['p']:.2f}" for o in alert["other_probabilities"]))
    return "\n".join(lines)


def claims_of(guide: dict) -> list[dict]:
    out = [{"id": f"C{i}", "text": a["text"], "citations": a["citations"]} for i, a in enumerate(guide["actions"], 1)]
    out.append({"id": f"C{len(out) + 1}", "text": "Escalate if: " + guide["escalate_if"]["text"],
                "citations": guide["escalate_if"]["citations"]})
    return out


def code_check(guide: dict, allowed: set[str]) -> list[str]:
    issues = []
    for c in claims_of(guide):
        if not c["citations"]:
            issues.append(f"{c['id']} has no citation.")
        for cid in c["citations"]:
            if cid not in allowed:
                issues.append(f"{c['id']} cites [{cid}], which is not in the given manual sections.")
    return issues


def corrupt(guide: dict, man: manuals.Manual, nums: list[int]) -> tuple[dict, str]:
    """Test of the checker: give the first action a real clause from an unrelated section of the excerpt."""
    g = json.loads(json.dumps(guide))
    used = {c for a in g["actions"] for c in a["citations"]}
    own = {c.split(".")[0] for c in g["actions"][0]["citations"]}
    pool = [cid for n in nums for cid in man.sections[n].clauses
            if cid not in used and cid.split(".")[0] not in own and n not in (2, 3)]
    pool = pool or [cid for n in nums for cid in man.sections[n].clauses if cid not in used]
    wrong = pool[-1]
    before = ", ".join(g["actions"][0]["citations"])
    g["actions"][0]["citations"] = [wrong]
    return g, f"Test: the citation of action 1 was changed from [{before}] to [{wrong}]."


def run(alert: dict, inject_fault: bool = False, use_cache: bool = True) -> Iterator[dict]:
    t_start = time.perf_counter()
    man = manuals.load(alert["asset_id"])
    nums = manuals.sections_for(alert["fault_type"])
    excerpt = man.render(nums)
    allowed = {cid for n in nums for cid in man.sections[n].clauses}
    atext = alert_text(alert)
    yield {"stage": "manual", "document": man.title, "sections": [{"num": n, "title": man.sections[n].title} for n in nums],
           "clauses": len(allowed)}

    feedback = None
    previous = None
    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        yield {"stage": "draft", "attempt": attempt, "status": "running"}
        messages = [{"role": "system", "content": WRITER_SYSTEM},
                    {"role": "user", "content": f"{atext}\n\nMANUAL EXCERPT\n{excerpt}"}]
        if previous:
            messages += [{"role": "assistant", "content": json.dumps(previous)},
                         {"role": "user", "content": "The citation checker rejected this guide:\n" + feedback +
                          "\nWrite the complete guide again. Correct or remove the rejected claims. Keep the supported claims."}]
        try:
            guide, meta = llm.chat_json(messages, GUIDE_SCHEMA, use_cache=use_cache)
        except ValueError:
            yield {"stage": "draft", "attempt": attempt, "status": "done", "guide": None, "meta": None, "test_note": None}
            feedback, previous = "Your reply was not valid JSON. Write a short guide.", None
            attempts.append({"attempt": attempt, "accepted": False})
            continue
        except Exception as exc:  # noqa: BLE001 - shown to the operator as a model error
            yield {"stage": "error", "message": f"Language model not available ({exc.__class__.__name__})."}
            return
        note = None
        if inject_fault and attempt == 1:
            guide, note = corrupt(guide, man, nums)
        yield {"stage": "draft", "attempt": attempt, "status": "done", "guide": guide, "meta": meta, "test_note": note}

        yield {"stage": "verify", "attempt": attempt, "status": "running"}
        claims = claims_of(guide)
        issues = code_check(guide, allowed)
        claim_text = "\n".join(f"{c['id']}: {c['text']} " + " ".join(f"[{x}]" for x in c["citations"]) for c in claims)
        user = f"{atext}\n\nMANUAL EXCERPT\n{excerpt}\n\nCLAIMS\n{claim_text}"
        try:
            verdict, vmeta = llm.chat_json([{"role": "system", "content": CHECKER_SYSTEM}, {"role": "user", "content": user}],
                                           VERDICT_SCHEMA, use_cache=use_cache, think=llm.CONFIG.get("think_verifier", False))
        except ValueError:  # no valid verdict: the guide is not accepted
            verdict, vmeta = {"checks": [], "feedback": ""}, {"cached": False, "ms": 0}
            issues.append("The checker did not return a valid verdict.")
        raw_checks = verdict.get("checks", [])
        by_claim = {}
        for rc in raw_checks:  # the model writes "C1", "1", "C1: text", ...
            if m := re.search(r"\d+", rc.get("claim", "")):
                by_claim.setdefault(f"C{int(m[0])}", rc)
        if len(by_claim) < len(claims) and len(raw_checks) == len(claims):
            by_claim = {c["id"]: rc for c, rc in zip(claims, raw_checks)}
        checks = []
        for c in claims:
            v = by_claim.get(c["id"])
            bad_ids = [x for x in c["citations"] if x not in allowed]
            checks.append({**c, "supported": bool(v and v["supported"]) and not bad_ids,
                           "reason": (v or {}).get("reason", "The checker gave no result for this claim."),
                           "checked": v is not None, "unknown_citations": bad_ids})
        # acceptance comes from the structured per-claim verdicts and the code check
        accepted = all(c["supported"] for c in checks) and not issues
        fb_parts = issues + [f"{c['id']} ({c['text']}): {c['reason']}" for c in checks if not c["supported"]]
        if not accepted and verdict.get("feedback", "OK").strip() != "OK":
            fb_parts.append(verdict["feedback"])
        feedback = "\n".join(fb_parts)
        previous = guide
        attempts.append({"attempt": attempt, "accepted": accepted})
        yield {"stage": "verify", "attempt": attempt, "status": "done", "accepted": accepted, "checks": checks,
               "code_issues": issues, "feedback": None if accepted else feedback, "meta": vmeta}
        if accepted:
            yield {"stage": "final", "status": "accepted", "guide": guide, "attempts": attempt,
                   "seconds": round(time.perf_counter() - t_start, 1)}
            return

    yield {"stage": "fallback", "status": "running"}
    summary, smeta = llm.chat_json([{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": atext}],
                                   SUMMARY_SCHEMA, use_cache=use_cache, max_tokens=300)
    yield {"stage": "final", "status": "fallback", "summary": summary["summary"], "attempts": MAX_ATTEMPTS,
           "sections": [{"num": n, "title": man.sections[n].title} for n in nums], "meta": smeta,
           "seconds": round(time.perf_counter() - t_start, 1)}


ASK_SYSTEM = """You are the maintenance assistant of a pump condition-monitoring system. The duty engineer asks about an alert.
Answer from the MANUAL and the ALERT data only. Cite each manual statement with its clause number in square brackets, for example [5.3].
Cite only clause numbers that appear in the manual. If the manual does not answer the question, say so and tell the engineer whom to ask.
Call the pump only by its asset ID. Answer in at most five short sentences or a short numbered list, in plain English. Do not use Markdown headings or bold text."""


def ask(alert: dict, question: str, history: list[dict], guide_text: str | None, use_cache: bool = True) -> Iterator[str]:
    man = manuals.load(alert["asset_id"])
    ctx = f"{alert_text(alert)}\n\n"
    if guide_text:
        ctx += f"VERIFIED GUIDE FOR THIS ALERT\n{guide_text}\n\n"
    ctx += f"MANUAL\n{man.render()}"
    messages = [{"role": "system", "content": ASK_SYSTEM}, {"role": "user", "content": ctx},
                {"role": "assistant", "content": "I have the alert and the manual. Ask your question."}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})
    yield from llm.chat_stream(messages, use_cache=use_cache)
