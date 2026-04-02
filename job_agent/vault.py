"""Obsidian vault I/O and markdown formatting for pipeline outputs.

All vault operations go through this module so the pipeline stays decoupled
from the filesystem layout.  Formatters convert Pydantic models into
human-readable markdown suitable for Obsidian rendering.

Typical usage::

    from job_agent.vault import create_vault_folder, write_to_vault
    folder = create_vault_folder(vault_base, "Acme", "Data Scientist")
    write_to_vault(folder, "match_report.md", format_analysis_report(analysis))
"""

import re
from pathlib import Path
from datetime import datetime

from job_agent.models import (
    AnalysisResult,
    CoverLetterResult,
    DiffResult,
    PipelineState,
    RescorerResult,
)


def create_vault_folder(vault_base: Path, company: str, role: str) -> Path:
    """Create a dated application subfolder inside the Obsidian vault.

    The folder name is sanitised so it is safe on all operating systems.

    Args:
        vault_base: Root ``Applications`` folder inside the Obsidian vault.
        company: Target company name, e.g. ``"Acme Corp"``.
        role: Job title, e.g. ``"Senior Data Scientist"``.

    Returns:
        ``Path`` to the newly created (or pre-existing) folder.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_company = re.sub(r"[^\w\-]", "_", company)
    safe_role = re.sub(r"[^\w\-]", "_", role)
    folder = vault_base.expanduser() / f"{safe_company}_{safe_role}_{date_str}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_to_vault(folder: Path, filename: str, content: str) -> Path:
    """Write a markdown file to the vault folder.

    Args:
        folder: Destination folder returned by ``create_vault_folder``.
        filename: File name including ``.md`` extension.
        content: Markdown text to write.

    Returns:
        ``Path`` to the written file.
    """
    path = folder / filename
    path.write_text(content, encoding="utf-8")
    return path


# ── Markdown Formatters ───────────────────────────────────────────────────────

def format_analysis_report(analysis: AnalysisResult) -> str:
    """Render an ``AnalysisResult`` as an Obsidian-compatible markdown report.

    Args:
        analysis: Output from ``AnalystAgent.run()``.

    Returns:
        Multi-section markdown string ready to write to ``match_report.md``.
    """
    proceed = "✅ Proceed" if analysis.proceed_with_application else "❌ Do Not Apply"
    lines = [
        "# Match Analysis Report",
        "",
        f"**Aggregate Score: {analysis.aggregate_score}/100**",
        f"**Recommendation: {proceed}**",
        f"> {analysis.proceed_rationale}",
        "",
        "## Section Scores",
        "",
    ]
    for section in analysis.section_scores:
        lines += [f"### {section.section.title()} — {section.score}/100", section.rationale, ""]

    lines += ["## Soft Missing Keywords *(rephrase only)*", ""]
    for kw in analysis.soft_missing:
        lines.append(f"- **{kw.keyword}** — {kw.rationale}")

    lines += ["", "## Hard Missing Keywords *(genuinely lacking)*", ""]
    for kw in analysis.hard_missing:
        addressable = "Addressable" if kw.addressable_with_existing_skills else "Not addressable"
        timeframe = f" | Timeframe: {kw.upskill_timeframe}" if kw.upskill_timeframe else ""
        lines.append(f"- **{kw.keyword}** — {kw.rationale} | {addressable}{timeframe}")

    if analysis.recency_gaps:
        lines += ["", "## Recency Gaps *(fast-moving field — not a hard gap)*", ""]
        for kw in analysis.recency_gaps:
            lines.append(f"- **{kw.keyword}** — {kw.rationale}")

    if analysis.transferable_strengths:
        lines += ["", "## Transferable Strengths", ""]
        for strength in analysis.transferable_strengths:
            lines.append(f"- {strength}")

    return "\n".join(lines)


def format_cover_letter(result: CoverLetterResult) -> str:
    """Render a ``CoverLetterResult`` as a markdown file for the vault.

    Args:
        result: Output from ``CoverLetterAgent.run()``.

    Returns:
        Markdown string ready to write to ``cover_letter.md``.
    """
    lines = [
        "# Cover Letter",
        "",
        result.cover_letter,
        "",
        "---",
        "",
        "## JD Signals Used",
        "",
    ]
    for signal in result.jd_signals:
        lines.append(f"- {signal}")
    lines += [
        "",
        "## Tailoring Notes",
        "",
    ]
    for note in result.tailoring_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


def format_diff_report(diff: DiffResult) -> str:
    """Render a ``DiffResult`` as a before/after markdown comparison.

    Args:
        diff: Output from ``DiffAgent.run()``.

    Returns:
        Markdown string ready to write to ``cv_diff.md``.
    """
    lines = [
        f"# CV Diff — {diff.variant_label.title()} Variant",
        "",
        "## Original",
        diff.original_summary,
        "",
        "## New",
        diff.new_summary,
        "",
        "## Changes",
        "",
    ]
    for change in diff.changes:
        lines.append(f"- {change}")
    return "\n".join(lines)


def format_rescore_report(rescore: RescorerResult) -> str:
    """Render a ``RescorerResult`` as a delta-focused markdown report.

    Args:
        rescore: Output from ``RescorerAgent.run()``.

    Returns:
        Markdown string ready to write to ``rescore_report.md``.
    """
    gate = "✅ PASSED" if rescore.gate_passed else "❌ FAILED"
    lines = [
        f"# Rescore Report — {rescore.variant_label.title()} Variant",
        "",
        f"**New Score: {rescore.new_aggregate_score}/100** (Δ {rescore.aggregate_delta:+d})",
        f"**Gate: {gate}**",
        "",
        "## Section Deltas",
        "",
    ]
    for section, delta in rescore.score_deltas.items():
        lines.append(f"- **{section}**: {delta:+d}")

    if rescore.regressions:
        lines += ["", "## ⚠️ Regressions", ""]
        for regression in rescore.regressions:
            lines.append(f"- {regression}")

    if rescore.soft_gaps_remaining:
        lines += ["", "## Soft Gaps Still Unresolved", ""]
        for gap in rescore.soft_gaps_remaining:
            lines.append(f"- {gap}")

    return "\n".join(lines)


def parse_status_file(path: Path) -> dict:
    """Parse a ``status.md`` file into a plain dict of fields.

    Args:
        path: Path to a ``status.md`` file written by ``format_status``.

    Returns:
        Dict with keys: company, role, date, initial_score, final_score,
        variant, status.  Score values are ints or ``None``.
    """
    text = path.read_text(encoding="utf-8")

    def extract(label: str) -> str:
        m = re.search(rf"\*\*{label}\*\*: (.+)", text)
        return m.group(1).strip() if m else ""

    def parse_score(raw: str) -> int | None:
        m = re.match(r"(\d+)", raw)
        return int(m.group(1)) if m else None

    initial_raw = extract("Initial Score").removesuffix("/100")
    final_raw = extract("Final Score").removesuffix("/100")
    return {
        "company": extract("Company"),
        "role": extract("Role"),
        "date": extract("Date"),
        "initial_score": parse_score(initial_raw),
        "final_score": parse_score(final_raw),
        "variant": extract("Variant"),
        "status": extract("Status"),
    }


def format_status(state: PipelineState) -> str:
    """Render a one-page status summary for the application folder.

    Args:
        state: The completed (or partially completed) ``PipelineState``.

    Returns:
        Markdown string ready to write to ``status.md``.
    """
    initial = state.analysis.aggregate_score if state.analysis else "N/A"
    final = (
        state.rescore_result.new_aggregate_score if state.rescore_result else "N/A"
    )
    return (
        "# Status\n\n"
        f"- **Company**: {state.company}\n"
        f"- **Role**: {state.role}\n"
        f"- **Date**: {state.created_at.strftime('%Y-%m-%d')}\n"
        f"- **Initial Score**: {initial}/100\n"
        f"- **Final Score**: {final}/100\n"
        f"- **Variant**: {state.selected_variant or 'N/A'}\n"
        "- **Status**: Ready to Apply\n\n"
        "<!-- Update status: Ready to Apply | Applied | Interview | Offer | Rejected | Closed - Did Not Apply | Dead Link -->\n"
    )
