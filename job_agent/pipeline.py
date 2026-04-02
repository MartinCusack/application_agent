"""Pipeline orchestrator — runs all agents in sequence and writes outputs.

The pipeline loads the CV and skills table once, creates an Obsidian vault
folder, then calls agents 1a → 2 → 2b → 3b in order.  State is accumulated
in a ``PipelineState`` object so any stage can be inspected after the run.
Early-exit gates write a ``status.md`` and return so the caller can inspect
``state.analysis`` to understand why the run stopped.

Typical usage::

    from job_agent.pipeline import run_pipeline
    state = run_pipeline(
        company="Acme Corp",
        role="Senior Data Scientist",
        job_description=jd_text,
    )
"""

import uuid

from rich.console import Console
from rich.panel import Panel

from job_agent.agents import (
    AnalystAgent,
    CoverLetterAgent,
    DiffAgent,
    RescorerAgent,
    WriterAgent,
)
from job_agent.config import config
from job_agent.cv_utils import extract_summary, substitute_summary
from job_agent.loaders import load_cv, load_skills_table, load_text
from job_agent.models import PipelineState
from job_agent.vault import (
    create_vault_folder,
    format_analysis_report,
    format_cover_letter,
    format_diff_report,
    format_rescore_report,
    format_status,
    write_to_vault,
)

console = Console()


def run_pipeline(
    company: str,
    role: str,
    job_description: str,
    threshold: int = config.MATCH_SCORE_THRESHOLD,
    force: bool = False,
) -> PipelineState:
    """Execute the full job application pipeline for a single role.

    Stages run in this order:
    1a. ``AnalystAgent`` — score and gap analysis
    2.  ``WriterAgent``  — rewrite summary (leadership variant)
    2b. ``DiffAgent``    — change log
    3b. ``RescorerAgent``— rescore edited CV with original rubric

    The pipeline exits early (and writes ``status.md``) if:

    - Agent 1a recommends not applying.
    - Agent 3b rescores below ``config.MATCH_SCORE_THRESHOLD``.

    All outputs are written to an Obsidian vault subfolder at each stage so
    partial results are always available even on early exit.

    Args:
        company: Target company name used for the vault folder name.
        role: Job title used for the vault folder name.
        job_description: Raw text of the job description to match against.
        threshold: Minimum rescored aggregate to pass Gate 2.  Defaults to
            ``config.MATCH_SCORE_THRESHOLD``.

    Returns:
        ``PipelineState`` with all agent outputs populated up to the
        point the pipeline ran or exited.
    """
    # ── Load inputs ───────────────────────────────────────────────────────────
    console.print(Panel("📂 Loading CV and Skills Table", style="bold blue"))
    cv_text = load_cv(config.CV_PATH)
    skills_table = load_skills_table(config.SKILLS_TABLE_PATH)
    cover_letter_template = load_text(config.COVER_LETTER_TEMPLATE_PATH)
    cover_letter_rubric = load_text(config.COVER_LETTER_RUBRIC_PATH)

    state = PipelineState(
        run_id=str(uuid.uuid4())[:8],
        company=company,
        role=role,
        job_description=job_description,
        cv_text=cv_text,
        skills_table=skills_table,
    )

    vault_folder = create_vault_folder(config.OBSIDIAN_VAULT_PATH, company, role)
    state.vault_path = str(vault_folder)
    write_to_vault(vault_folder, "job_description.md", f"# Job Description\n\n{job_description}")
    console.print(f"📁 Vault folder: {vault_folder}")

    # ── Agent 1a ──────────────────────────────────────────────────────────────
    console.print(Panel("🔍 Agent 1a: Deep Analysis", style="bold yellow"))
    analysis = AnalystAgent().run(cv_text, skills_table, job_description)
    state.analysis = analysis
    write_to_vault(vault_folder, "match_report.md", format_analysis_report(analysis))
    console.print(
        f"  Score: [bold]{analysis.aggregate_score}/100[/bold] | "
        f"Threshold: {config.MATCH_SCORE_THRESHOLD} | "
        f"Proceed: {'✅' if analysis.proceed_with_application else '❌'}"
    )

    if not analysis.proceed_with_application:
        if force:
            console.print("[yellow]Gate 1 skipped (--force): continuing despite analyst recommendation.[/yellow]")
        else:
            write_to_vault(vault_folder, "status.md", format_status(state))
            console.print("[red]Pipeline stopped: analyst recommended not applying.[/red]")
            return state

    # ── Agent 1b ──────────────────────────────────────────────────────────────
    console.print(Panel("✉️  Agent 1b: Cover Letter", style="bold magenta"))
    cover_letter_result = CoverLetterAgent().run(
        cover_letter_template=cover_letter_template,
        cover_letter_rubric=cover_letter_rubric,
        job_description=job_description,
        company=company,
        role=role,
        analysis=analysis,
    )
    state.cover_letter_result = cover_letter_result
    write_to_vault(vault_folder, "cover_letter.md", format_cover_letter(cover_letter_result))
    console.print(f"  Tailoring notes: {len(cover_letter_result.tailoring_notes)}")

    # ── Agent 2 ───────────────────────────────────────────────────────────────
    console.print(Panel("✍️  Agent 2: Rewriting Summary", style="bold green"))
    writer_result = WriterAgent().run(cv_text, skills_table, analysis)
    state.writer_result = writer_result

    variant = writer_result.variant
    state.selected_variant = variant.label
    full_cv = substitute_summary(cv_text, variant.summary_section)
    write_to_vault(
        vault_folder,
        "cv_tailored.md",
        f"# Tailored CV ({variant.label})\n\n{full_cv}",
    )

    # ── Agent 2b ──────────────────────────────────────────────────────────────
    console.print(Panel("📊 Agent 2b: Change Log", style="bold cyan"))
    original_summary = extract_summary(cv_text)
    diff_result = DiffAgent().run(original_summary, variant.summary_section, variant.label)
    state.diff_result = diff_result
    write_to_vault(vault_folder, "cv_diff.md", format_diff_report(diff_result))

    # ── Agent 3b ──────────────────────────────────────────────────────────────
    console.print(Panel("📈 Agent 3b: Rescoring", style="bold yellow"))
    rescore = RescorerAgent().run(full_cv, job_description, analysis, variant.label, threshold=threshold)
    state.rescore_result = rescore
    write_to_vault(vault_folder, "rescore_report.md", format_rescore_report(rescore))
    console.print(
        f"  New Score: [bold]{rescore.new_aggregate_score}/100[/bold] "
        f"(Δ {rescore.aggregate_delta:+d}) | "
        f"Gate: {'✅' if rescore.gate_passed else '❌'}"
    )

    if not rescore.gate_passed:
        write_to_vault(vault_folder, "status.md", format_status(state))
        console.print("[red]Pipeline stopped: rescored CV still below threshold.[/red]")
        return state

    write_to_vault(vault_folder, "status.md", format_status(state))
    console.print(Panel(f"✅ Pipeline complete\n{vault_folder}", style="bold green"))
    return state
