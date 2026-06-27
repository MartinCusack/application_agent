"""Batch pipeline orchestrator — runs the job application pipeline for multiple JDs.

Discovers all ``.md`` files in a queue directory, runs :func:`run_pipeline`
for each one sequentially, moves processed files to outcome subdirectories,
and writes a summary report to the Obsidian vault.

Outcome directories are created as siblings of the TODO directory:

.. code-block::

    job_descriptions/
    ├── TODO/       ← input queue
    ├── applied/    ← both gates passed
    ├── gated_out/  ← passed Gate 1, failed Gate 2 (low rescore)
    ├── skipped/    ← failed Gate 1 (analyst said don't apply)
    └── failed/     ← pipeline raised an exception (.error.txt sidecar written)

Typical usage::

    from job_agent.batch import run_batch
    result = run_batch(todo_dir=Path("job_descriptions/TODO"))
"""

import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from job_agent.config import config
from job_agent.jd_parser import parse_jd_file
from job_agent.models import BatchJobResult, BatchRunResult, PipelineState
from job_agent.pipeline import run_pipeline

console = Console()

_STATUS_COLOURS = {
    "applied": "green",
    "gated_out": "yellow",
    "skipped": "dim",
    "error": "red",
}


def discover_jd_files(todo_dir: Path) -> list[Path]:
    """Return all ``.md`` files in *todo_dir*, sorted alphabetically.

    Args:
        todo_dir: Directory to scan.

    Returns:
        Sorted list of ``.md`` file paths.
    """
    return sorted(todo_dir.glob("*.md"))


def _vault_folder_exists(vault_base: Path, company: str, role: str) -> bool:
    """Return ``True`` if a vault folder for this company/role already exists today."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_company = re.sub(r"[^\w\-]", "_", company)
    safe_role = re.sub(r"[^\w\-]", "_", role)
    folder = vault_base / f"{safe_company}_{safe_role}_{date_str}"
    return folder.exists()


def _classify_state(state: PipelineState) -> str:
    """Return the batch outcome string for a completed pipeline state.

    Args:
        state: Pipeline state after :func:`run_pipeline` returns.

    Returns:
        ``"applied"``, ``"gated_out"``, or ``"skipped"``.
    """
    if state.rescore_result is not None:
        return "applied" if state.rescore_result.gate_passed else "gated_out"
    return "skipped"


def _move_file(src: Path, dest_dir: Path) -> None:
    """Move *src* into *dest_dir*, avoiding silent overwrites.

    If a file with the same name already exists in *dest_dir*, a timestamp
    suffix is appended to the destination filename.

    Args:
        src: Source file path.
        dest_dir: Destination directory (created if it does not exist).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = dest_dir / f"{src.stem}_{ts}{src.suffix}"
    src.rename(dest)


def run_batch(
    todo_dir: Path,
    threshold: Optional[int] = None,
    force: bool = False,
    delay_seconds: float = config.BATCH_DELAY_SECONDS,
    dry_run: bool = False,
) -> BatchRunResult:
    """Run the pipeline for every ``.md`` file in *todo_dir*.

    Files are processed sequentially.  A per-job ``try/except`` ensures
    that one pipeline failure never aborts the rest of the batch.
    ``KeyboardInterrupt`` is caught at the batch level and results in a
    clean partial summary being written before exit.

    Args:
        todo_dir: Directory containing pending ``.md`` JD files.
        threshold: Override score threshold for all jobs.  ``None`` uses
            ``config.MATCH_SCORE_THRESHOLD``.  Per-job frontmatter values
            take precedence over this argument.
        force: Bypass Gate 1 for all jobs.  Per-job frontmatter ``force``
            takes precedence.
        delay_seconds: Pause between jobs (seconds) to respect API rate limits.
        dry_run: If ``True``, list discovered files and exit without processing.

    Returns:
        :class:`~job_agent.models.BatchRunResult` with per-job outcomes and
        aggregate counts.
    """
    todo_dir = todo_dir.expanduser()
    vault_base = config.OBSIDIAN_VAULT_PATH.expanduser()
    effective_threshold = threshold if threshold is not None else config.MATCH_SCORE_THRESHOLD

    jd_files = discover_jd_files(todo_dir)
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now()

    if not jd_files:
        console.print(f"[yellow]No .md files found in {todo_dir}[/yellow]")
        return BatchRunResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(),
            total=0, applied=0, gated_out=0, skipped=0, errors=0,
            results=[],
        )

    if dry_run:
        console.print(f"[bold]Dry run — {len(jd_files)} file(s) in {todo_dir}:[/bold]")
        for f in jd_files:
            try:
                meta = parse_jd_file(f)
                console.print(f"  • {f.name}  →  {meta.company} | {meta.role}")
            except Exception as exc:
                console.print(f"  • {f.name}  →  [red]parse error: {exc}[/red]")
        return BatchRunResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(),
            total=len(jd_files), applied=0, gated_out=0, skipped=0, errors=0,
            results=[],
        )

    parent_dir = todo_dir.parent
    dest_dirs = {
        "applied":   parent_dir / "applied",
        "gated_out": parent_dir / "gated_out",
        "skipped":   parent_dir / "skipped",
        "error":     parent_dir / "failed",
    }

    results: list[BatchJobResult] = []
    interrupted = False

    console.print(
        f"\n[bold]Batch apply[/bold] — {len(jd_files)} job(s) · "
        f"threshold {effective_threshold} · delay {delay_seconds}s\n"
    )

    try:
        for idx, jd_path in enumerate(jd_files, start=1):
            console.rule(f"[bold][{idx}/{len(jd_files)}] {jd_path.name}[/bold]")

            # ── Parse metadata ────────────────────────────────────────────────
            try:
                meta = parse_jd_file(jd_path)
            except Exception as exc:
                console.print(f"[red]Failed to parse {jd_path.name}: {exc}[/red]")
                results.append(BatchJobResult(
                    company=jd_path.stem,
                    role="unknown",
                    jd_file=jd_path.name,
                    status="error",
                    error_message=f"Parse error: {exc}",
                ))
                failed_dir = dest_dirs["error"]
                failed_dir.mkdir(parents=True, exist_ok=True)
                (failed_dir / f"{jd_path.stem}.error.txt").write_text(
                    str(exc), encoding="utf-8"
                )
                _move_file(jd_path, failed_dir)
                continue

            # ── Duplicate detection ───────────────────────────────────────────
            if vault_base.exists() and _vault_folder_exists(vault_base, meta.company, meta.role):
                console.print(
                    f"[yellow]Skipping {meta.company} / {meta.role} — "
                    f"vault folder already exists for today.[/yellow]"
                )
                results.append(BatchJobResult(
                    company=meta.company,
                    role=meta.role,
                    jd_file=jd_path.name,
                    status="skipped",
                    error_message="Vault folder already exists for today",
                ))
                continue

            # ── Run pipeline ──────────────────────────────────────────────────
            job_threshold = meta.threshold if meta.threshold is not None else effective_threshold
            job_force = meta.force or force

            try:
                state = run_pipeline(
                    company=meta.company,
                    role=meta.role,
                    job_description=meta.jd_text,
                    threshold=job_threshold,
                    force=job_force,
                )
            except Exception as exc:
                console.print(
                    f"[red]Pipeline error for {meta.company} / {meta.role}: {exc}[/red]"
                )
                results.append(BatchJobResult(
                    company=meta.company,
                    role=meta.role,
                    jd_file=jd_path.name,
                    status="error",
                    error_message=str(exc),
                ))
                failed_dir = dest_dirs["error"]
                failed_dir.mkdir(parents=True, exist_ok=True)
                (failed_dir / f"{jd_path.stem}.error.txt").write_text(
                    str(exc), encoding="utf-8"
                )
                _move_file(jd_path, failed_dir)
                continue

            outcome = _classify_state(state)
            initial = state.analysis.aggregate_score if state.analysis else None
            final = state.rescore_result.new_aggregate_score if state.rescore_result else None

            results.append(BatchJobResult(
                company=meta.company,
                role=meta.role,
                jd_file=jd_path.name,
                status=outcome,
                initial_score=initial,
                final_score=final,
                vault_path=state.vault_path,
            ))
            _move_file(jd_path, dest_dirs[outcome])

            if idx < len(jd_files):
                time.sleep(delay_seconds)

    except KeyboardInterrupt:
        interrupted = True
        console.print("\n[yellow]Batch interrupted — writing partial summary.[/yellow]")

    completed_at = datetime.now()
    applied_count  = sum(1 for r in results if r.status == "applied")
    gated_out_count = sum(1 for r in results if r.status == "gated_out")
    skipped_count  = sum(1 for r in results if r.status == "skipped")
    errors_count   = sum(1 for r in results if r.status == "error")

    batch_result = BatchRunResult(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        total=len(jd_files),
        applied=applied_count,
        gated_out=gated_out_count,
        skipped=skipped_count,
        errors=errors_count,
        results=results,
    )

    # ── Write vault summary ───────────────────────────────────────────────────
    if vault_base.exists() and results:
        # Import here to avoid circular import at module level
        from job_agent.vault import format_batch_summary, write_to_vault

        write_to_vault(vault_base, f"batch_run_{run_id}.md", format_batch_summary(batch_result))
        (vault_base / f"batch_run_{run_id}.json").write_text(
            batch_result.model_dump_json(indent=2), encoding="utf-8"
        )

    # ── Print results table ───────────────────────────────────────────────────
    if results:
        table = Table(title=f"Batch Run {run_id}", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Company")
        table.add_column("Role")
        table.add_column("Initial", justify="right")
        table.add_column("Final", justify="right")
        table.add_column("Outcome")

        for i, r in enumerate(results, start=1):
            colour = _STATUS_COLOURS.get(r.status, "white")
            table.add_row(
                str(i),
                r.company,
                r.role,
                str(r.initial_score) if r.initial_score is not None else "—",
                str(r.final_score) if r.final_score is not None else "—",
                f"[{colour}]{r.status}[/{colour}]",
            )
        console.print(table)

    label = "interrupted" if interrupted else "complete"
    console.print(
        f"\n[bold]Batch {label}[/bold] — "
        f"[green]{applied_count} applied[/green] · "
        f"[yellow]{gated_out_count} gated out[/yellow] · "
        f"[dim]{skipped_count} skipped[/dim] · "
        f"[red]{errors_count} errors[/red]"
    )

    return batch_result
