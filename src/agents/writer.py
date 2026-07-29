"""ReportWriter: turns verified conclusions into a debrief.

Deliberately thin. The rules already decided what is true; this layer only
decides how it reads. Two consequences:

- `--no-llm` emits template text from the same conclusions, so the demo runs with
  no API key and no network. The claims are identical; only the prose differs.
- When the LLM is on, the model may rephrase but never add a number. That is not
  a request in the prompt, it is a post-check: every numeral in the output must
  already exist in the decision trace, or the output is rejected and the template
  version is used instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.agents.base import SEVERITIES, Conclusion
from src.agents.trace import allowed_numerals

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

_NUMERAL = re.compile(r"\d+(?:\.\d+)?")

SYSTEM = """You are a VALORANT coaching analyst writing a post-match debrief.

You will be given a list of verified findings about one match. Every finding was
produced by a deterministic rule and checked against the underlying data.

Your job is to phrase them, not to extend them.

Hard constraints:
- You may rephrase, reorder, merge, and connect the findings into prose.
- You MUST NOT introduce any number that does not already appear in the findings.
  Do not compute new figures, do not convert units, do not round to a different
  precision, do not total anything up.
- You MUST NOT introduce any claim the findings do not support. No player names,
  no agent names, no map reads, no tactical speculation.
- Anything the findings label `sim-approx` must stay labelled as an approximation.

Write 2-4 short paragraphs, lead with what decided the match. Address the team
directly. No headings, no bullet lists, no preamble, no sign-off."""


@dataclass
class Report:
    text: str
    used_llm: bool
    # Populated when an LLM draft was rejected; the text falls back to template.
    rejected_numerals: list[str] | None = None
    error: str | None = None


def _group(conclusions: list[Conclusion]) -> dict[str, list[Conclusion]]:
    grouped: dict[str, list[Conclusion]] = {}
    for c in conclusions:
        grouped.setdefault(c.agent, []).append(c)
    return grouped


def template_report(conclusions: list[Conclusion]) -> str:
    """The dry debrief. Complete, just not written by anyone."""
    if not conclusions:
        return "No verified findings for this match."

    lines = []
    for agent in sorted(_group(conclusions)):
        lines.append(f"{agent}")
        lines.append("-" * len(agent))
        for c in sorted(_group(conclusions)[agent],
                        key=lambda c: (SEVERITIES.index(c.severity), c.rule_id)):
            lines.append(f"  [{c.severity}] {c.text}")
            lines.append(f"           rule: {c.rule_id}, "
                         f"{len(c.citations)} feature row(s) cited")
        lines.append("")
    return "\n".join(lines).rstrip()


def check_numerals(text: str, conclusions: list[Conclusion]) -> list[str]:
    """Numerals present in `text` that no verified conclusion entitles it to."""
    allowed = allowed_numerals(conclusions)
    return sorted({n for n in _NUMERAL.findall(text) if n not in allowed})


def _findings_block(conclusions: list[Conclusion]) -> str:
    return "\n".join(
        f"- [{c.severity}] {c.text}" for c in conclusions
    )


def llm_report(conclusions: list[Conclusion]) -> Report:
    """Ask the model to phrase the findings; reject the draft if it invents a number."""
    fallback = template_report(conclusions)
    if not conclusions:
        return Report(text=fallback, used_llm=False, error="no verified findings to phrase")

    try:
        import anthropic
    except ImportError:
        return Report(text=fallback, used_llm=False,
                      error="anthropic SDK not installed -- run with --no-llm")

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            output_config={"effort": "low"},  # phrasing, not reasoning
            messages=[{"role": "user", "content": _findings_block(conclusions)}],
        )
    except Exception as e:  # noqa: BLE001 -- any API failure falls back to template
        return Report(text=fallback, used_llm=False, error=f"{type(e).__name__}: {e}")

    if response.stop_reason == "refusal":
        return Report(text=fallback, used_llm=False, error="model declined the request")

    draft = "\n".join(b.text for b in response.content if b.type == "text").strip()
    if not draft:
        return Report(text=fallback, used_llm=False, error="model returned no text")

    invented = check_numerals(draft, conclusions)
    if invented:
        return Report(text=fallback, used_llm=False, rejected_numerals=invented,
                      error="draft contained numbers absent from the trace")

    return Report(text=draft, used_llm=True)


def write_report(conclusions: list[Conclusion], use_llm: bool) -> Report:
    if not use_llm:
        return Report(text=template_report(conclusions), used_llm=False)
    return llm_report(conclusions)
