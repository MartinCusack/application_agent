"""Utilities for parsing job description files from the batch queue.

Supports two metadata sources, in priority order:

1. YAML frontmatter (between ``---`` delimiters at the top of the file)
2. Filename convention: ``Company_Role_Words.md``

Frontmatter keys (all optional):

.. code-block:: yaml

    ---
    company: Deel
    role: Data Scientist
    threshold: 70
    force: false
    ---

    [Job description text follows...]

Typical usage::

    from job_agent.jd_parser import parse_jd_file
    meta = parse_jd_file(Path("job_descriptions/TODO/Deel_Data_Scientist.md"))
    # meta.company → "Deel"
    # meta.role    → "Data Scientist"
"""

import re
from pathlib import Path
from typing import Optional

from job_agent.models import JDFileMetadata


def _parse_simple_yaml(yaml_text: str) -> dict:
    """Parse a minimal YAML block containing only ``key: value`` pairs.

    Handles strings, integers, and booleans.  Does not support nested
    structures or lists — only the flat keys needed for JD frontmatter.

    Args:
        yaml_text: Raw text between the ``---`` delimiters.

    Returns:
        Dict of parsed key/value pairs.
    """
    result: dict = {}
    for line in yaml_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        # Parse typed values
        if value.lower() == "true":
            result[key] = True
        elif value.lower() == "false":
            result[key] = False
        elif value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value
    return result


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from the body of a markdown file.

    Args:
        text: Raw file contents.

    Returns:
        ``(metadata_dict, body_text)`` tuple.  If no frontmatter block is
        found, returns ``({}, text)`` unchanged.
    """
    pattern = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)
    match = pattern.match(text)
    if not match:
        return {}, text
    meta = _parse_simple_yaml(match.group(1))
    body = text[match.end():]
    return meta, body


def _parse_filename(path: Path) -> tuple[str, str]:
    """Derive company and role from a JD filename.

    The convention is ``Company_Role_Words.md``:

    - The first underscore-separated token becomes the company name.
    - All remaining tokens are joined with spaces to form the role.

    Examples::

        Deel_Data_Scientist.md            → ("Deel", "Data Scientist")
        Acme_Corp_Senior_Data_Scientist.md → ("Acme", "Corp Senior Data Scientist")

    Args:
        path: Path to the JD ``.md`` file.

    Returns:
        ``(company, role)`` string tuple.
    """
    parts = path.stem.split("_")
    company = parts[0]
    role = " ".join(parts[1:]) if len(parts) > 1 else path.stem
    return company, role


def parse_jd_file(path: Path) -> JDFileMetadata:
    """Parse a JD file and return structured metadata.

    Frontmatter values take precedence over filename-derived values.
    ``company`` and ``role`` are always populated — either from frontmatter
    or from the filename convention.

    Args:
        path: Path to the ``.md`` JD file.

    Returns:
        :class:`~job_agent.models.JDFileMetadata` with company, role,
        jd_text, and optional threshold/force overrides.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    text = path.read_text(encoding="utf-8")
    meta_dict, body = _extract_frontmatter(text)

    filename_company, filename_role = _parse_filename(path)

    company = str(meta_dict.get("company", filename_company)).strip()
    role = str(meta_dict.get("role", filename_role)).strip()

    threshold: Optional[int] = meta_dict.get("threshold")
    if threshold is not None:
        threshold = int(threshold)

    force: bool = bool(meta_dict.get("force", False))

    return JDFileMetadata(
        path=path,
        company=company,
        role=role,
        jd_text=body.strip(),
        threshold=threshold,
        force=force,
    )
