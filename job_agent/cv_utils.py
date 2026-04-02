"""Utility functions for manipulating CV text.

These are pure string operations with no LLM calls, kept separate so they
can be unit-tested cheaply.

Typical usage::

    from job_agent.cv_utils import extract_summary, substitute_summary
    original = extract_summary(cv_text)
    full_cv  = substitute_summary(cv_text, new_summary)
"""

_SUMMARY_HEADINGS = ("## summary", "## profile", "## about")


def extract_summary(cv_text: str) -> str:
    """Extract the summary/profile section from a markdown CV.

    Searches for the first heading whose lower-cased text matches one of
    ``## summary``, ``## profile``, or ``## about`` and returns the text
    between that heading and the next ``##`` heading.

    Args:
        cv_text: Full CV text in markdown format.

    Returns:
        The summary section text, stripped of leading/trailing whitespace.
        Returns an empty string if no matching heading is found.
    """
    lines = cv_text.split("\n")
    in_summary = False
    collected: list[str] = []

    for line in lines:
        if line.lower().startswith(tuple(_SUMMARY_HEADINGS)):
            in_summary = True
            continue
        if in_summary:
            if line.startswith("## "):
                break
            collected.append(line)

    return "\n".join(collected).strip()


def substitute_summary(cv_text: str, new_summary: str) -> str:
    """Replace the summary section in a CV with a rewritten version.

    If no matching summary heading is found the new summary is prepended
    to the document so downstream agents always receive a summary.

    Args:
        cv_text: Full CV text in markdown format.
        new_summary: Replacement summary text (heading not included).

    Returns:
        Full CV text with the summary section swapped out.
    """
    lines = cv_text.split("\n")
    result: list[str] = []
    skipping = False
    inserted = False

    for line in lines:
        if line.lower().startswith(tuple(_SUMMARY_HEADINGS)):
            result.append(line)
            result.append(new_summary)
            skipping = True
            inserted = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            result.append(line)

    if not inserted:
        result = [new_summary, ""] + result

    return "\n".join(result)
