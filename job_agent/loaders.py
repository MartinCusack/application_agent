"""File loaders for CV and skills table inputs.

These functions are deliberately thin — they load from disk and return
strings so the rest of the pipeline stays testable without touching the
filesystem.

Typical usage::

    from job_agent.loaders import load_cv, load_skills_table
    cv_text = load_cv(Path("data/cv.md"))
    skills_md = load_skills_table(Path("data/skills.xlsx"))
"""

from pathlib import Path

import pandas as pd


def load_cv(cv_path: Path) -> str:
    """Load the master CV from a markdown or plain-text file.

    Args:
        cv_path: Absolute or relative path to the CV file.

    Returns:
        Full CV text as a single UTF-8 string.

    Raises:
        FileNotFoundError: If ``cv_path`` does not exist.
    """
    if not cv_path.exists():
        raise FileNotFoundError(f"CV not found at {cv_path}")
    return cv_path.read_text(encoding="utf-8")


def load_text(path: Path) -> str:
    """Load any plain-text or markdown file.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        File contents as a single UTF-8 string.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def load_skills_table(skills_path: Path) -> str:
    """Load the skills Excel table and serialise it as a markdown table.

    The returned string is injected directly into agent prompts so the
    model can cite specific rows.  Expected columns: Skill, Category,
    Proficiency, Projects, Roles, Years.  Extra columns are included
    automatically.

    Args:
        skills_path: Absolute or relative path to the ``.xlsx`` file.

    Returns:
        Markdown-formatted table string (pipe-delimited, with header row).

    Raises:
        FileNotFoundError: If ``skills_path`` does not exist.
    """
    if not skills_path.exists():
        raise FileNotFoundError(f"Skills table not found at {skills_path}")
    df = pd.read_excel(skills_path)
    return df.to_markdown(index=False)
