"""Command-line interface for the job application pipeline.

Provides two commands:

- ``apply``        — run the full pipeline for a role
- ``check-config`` — verify paths and API key before a real run

Typical usage::

    uv run job-agent apply --company "Acme Corp" --role "Senior Data Scientist"
    uv run job-agent apply --company "Acme" --role "DS" --jd-file jd.txt
    uv run job-agent check-config
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="AI-powered job application pipeline")
console = Console()


@app.command()
def apply(
    company: str = typer.Option(..., "--company", "-c", help="Company name"),
    role: str = typer.Option(..., "--role", "-r", help="Job role/title"),
    jd_file: Path = typer.Option(None, "--jd-file", "-f", help="Path to JD text file"),
    threshold: Optional[int] = typer.Option(None, "--threshold", "-t", help="Override score threshold"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip Gate 1 and produce CV + cover letter regardless of analyst recommendation"),
) -> None:
    """Run the full job application pipeline for a given role.

    Args:
        company: Target company name.
        role: Job title being applied for.
        jd_file: Optional path to a plain-text job description file.  If not
            provided the JD is read interactively from stdin.
        threshold: Override ``MATCH_SCORE_THRESHOLD`` for this single run.
    """
    if jd_file and jd_file.exists():
        job_description = jd_file.read_text(encoding="utf-8")
        console.print(f"[green]Loaded JD from {jd_file}[/green]")
    else:
        console.print(
            "[yellow]Paste the job description below. "
            "Press Enter twice when done:[/yellow]"
        )
        lines: list[str] = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        job_description = "\n".join(lines).strip()

    if not job_description:
        console.print("[red]No job description provided. Exiting.[/red]")
        raise typer.Exit(1)

    from job_agent.config import config
    from job_agent.pipeline import run_pipeline
    run_pipeline(
        company=company,
        role=role,
        job_description=job_description,
        threshold=threshold if threshold is not None else config.MATCH_SCORE_THRESHOLD,
        force=force,
    )


@app.command()
def list_applications(
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (e.g. Applied, Interview, Offer, Rejected, Closed - Did Not Apply, Dead Link)"),
) -> None:
    """List all job applications in the Obsidian vault with their scores and status."""
    from rich.table import Table
    from job_agent.config import config
    from job_agent.vault import parse_status_file

    vault_base = config.OBSIDIAN_VAULT_PATH.expanduser()
    if not vault_base.exists():
        console.print(f"[red]Vault path not found: {vault_base}[/red]")
        raise typer.Exit(1)

    status_files = sorted(vault_base.rglob("status.md"), reverse=True)
    if not status_files:
        console.print("[yellow]No applications found in vault.[/yellow]")
        return

    STATUS_COLOURS = {
        "ready to apply": "blue",
        "applied": "cyan",
        "interview": "yellow",
        "offer": "green",
        "rejected": "red",
        "closed - did not apply": "dim",
        "dead link": "magenta",
    }

    table = Table(title="Job Applications", show_lines=True)
    table.add_column("Date", style="dim", no_wrap=True)
    table.add_column("Company", style="bold")
    table.add_column("Role")
    table.add_column("Initial", justify="right")
    table.add_column("Final", justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("Variant", style="dim")
    table.add_column("Status")

    count = 0
    for sf in status_files:
        data = parse_status_file(sf)
        if status_filter and data["status"].lower() != status_filter.lower():
            continue

        initial = data["initial_score"]
        final = data["final_score"]
        if initial is not None and final is not None:
            delta = final - initial
            delta_str = f"[green]+{delta}[/green]" if delta >= 0 else f"[red]{delta}[/red]"
            final_str = str(final)
        else:
            delta_str = "—"
            final_str = str(final) if final is not None else "—"

        status_colour = STATUS_COLOURS.get(data["status"].lower(), "white")
        table.add_row(
            data["date"],
            data["company"],
            data["role"],
            str(initial) if initial is not None else "—",
            final_str,
            delta_str,
            data["variant"] or "—",
            f"[{status_colour}]{data['status']}[/{status_colour}]",
        )
        count += 1

    console.print(table)
    console.print(f"[dim]{count} application(s) found[/dim]")


@app.command()
def check_config() -> None:
    """Verify that all required config paths and the API key are set.

    Prints a quick checklist so problems are caught before a real API run.
    """
    from job_agent.config import config

    console.print("\n[bold]Config Check[/bold]")
    console.print(
        f"  CV path:         {config.CV_PATH} "
        f"{'✅' if config.CV_PATH.exists() else '❌ NOT FOUND'}"
    )
    console.print(
        f"  Skills table:    {config.SKILLS_TABLE_PATH} "
        f"{'✅' if config.SKILLS_TABLE_PATH.exists() else '❌ NOT FOUND'}"
    )
    console.print(f"  Obsidian vault:  {config.OBSIDIAN_VAULT_PATH}")
    console.print(f"  Score threshold: {config.MATCH_SCORE_THRESHOLD}")
    console.print(f"  Provider:        {config.MODEL_PROVIDER}")
    console.print(f"  Model:           {config.MODEL_NAME}")
    api_key = config.ANTHROPIC_API_KEY if config.MODEL_PROVIDER == "anthropic" else config.OPENAI_API_KEY
    console.print(f"  API key set:     {'✅' if api_key else '❌'}\n")


if __name__ == "__main__":
    app()
