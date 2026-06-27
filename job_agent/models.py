"""Pydantic models for all agent inputs, outputs, and shared pipeline state.

Each model corresponds to one agent's structured output.  The ``ScoringRubric``
produced by ``AnalystAgent`` is intentionally threaded all the way through to
``RescorerAgent`` so both agents score against identical criteria.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Agent 1a: Deep Analyst ────────────────────────────────────────────────────

class SectionScore(BaseModel):
    """Score and rationale for a single CV section.

    Attributes:
        section: Name of the section, e.g. ``"summary"``, ``"experience"``.
        score: Numeric score between 0 and 100.
        rationale: One or two sentences justifying the score.
    """

    section: str
    score: int = Field(ge=0, le=100)
    rationale: str


class MissingKeyword(BaseModel):
    """A keyword present in the JD but absent or mis-phrased in the CV.

    Attributes:
        keyword: The missing term or phrase.
        gap_type: Either ``"hard"`` (genuinely lacking), ``"soft"``
            (candidate has the skill but used different wording), or
            ``"recency"`` (fast-moving field where limited exposure still
            constitutes genuine seniority — do not classify as hard).
        rationale: Why this keyword matters for the role.
        addressable_with_existing_skills: For hard gaps only — whether the
            candidate's adjacent skills could bridge the gap.
        upskill_timeframe: For hard gaps only — rough estimate to acquire
            the skill, e.g. ``"3–6 months"``.
    """

    keyword: str
    gap_type: str = Field(description="'hard', 'soft', or 'recency'")
    rationale: str
    addressable_with_existing_skills: Optional[bool] = None
    upskill_timeframe: Optional[str] = None


class ScoringRubric(BaseModel):
    """Scoring criteria extracted by the analyst and reused by the rescorer.

    Passing this object explicitly prevents the rescorer from silently
    inventing different criteria, ensuring deltas are meaningful.

    Attributes:
        keywords_identified: All JD keywords the analyst used for scoring.
        section_weights: Fractional weight per section, must sum to 1.0.
            Example: ``{"summary": 0.2, "experience": 0.5, "skills": 0.3}``.
        recency_flagged_keywords: Subset of ``keywords_identified`` where
            field recency applies (e.g. LLMs, agentic AI). The rescorer
            should not penalise limited tenure for these.
    """

    keywords_identified: list[str]
    section_weights: dict[str, float]
    recency_flagged_keywords: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Full output from Agent 1a (Deep Analyst).

    Attributes:
        aggregate_score: Weighted overall match score 0–100.
        section_scores: Per-section breakdown.
        hard_missing: Keywords the candidate genuinely lacks.
        soft_missing: Keywords the candidate has but phrased differently.
        recency_gaps: Skills in fast-moving fields (e.g. LLMs, agentic AI)
            where limited exposure still constitutes genuine seniority.
            Not classified as hard missing.
        transferable_strengths: Domain expertise and adjacent skills that
            aren't direct JD matches but represent genuine value for the role.
        proceed_with_application: Whether the pipeline should continue.
        proceed_rationale: Plain-English justification of the decision.
        rubric: Criteria object forwarded to Writer and Rescorer.
    """

    aggregate_score: int = Field(ge=0, le=100)
    section_scores: list[SectionScore]
    hard_missing: list[MissingKeyword]
    soft_missing: list[MissingKeyword]
    recency_gaps: list[MissingKeyword] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    proceed_with_application: bool
    proceed_rationale: str
    rubric: ScoringRubric


# ── Agent 1b: Cover Letter Writer ────────────────────────────────────────────

class CoverLetterResult(BaseModel):
    """Output from Agent 1b (Cover Letter Writer).

    Attributes:
        jd_signals: Verbatim phrases, product names, challenges, and mission
            signals extracted from the JD before writing. These are the only
            permitted sources for placeholder content — any claim in the
            cover letter must trace back to an entry here.
        cover_letter: Full tailored cover letter text, ready to send.
        tailoring_notes: What was customised and why, one entry per change,
            each citing the jd_signals entry it drew from.
    """

    jd_signals: list[str]
    cover_letter: str
    tailoring_notes: list[str]


# ── Agent 2: Writer ───────────────────────────────────────────────────────────

class CVVariant(BaseModel):
    """One rewritten summary variant produced by the Writer agent.

    Attributes:
        label: Human-readable identifier, either ``"technical"`` or
            ``"leadership"``.
        summary_section: The full rewritten summary text.
        changes_made: What soft gaps were addressed and how.
        skills_rows_cited: Rows from the skills table that were drawn on,
            ensuring no fabricated experience slips through.
    """

    label: str
    summary_section: str
    changes_made: list[str]
    skills_rows_cited: list[str]


class WriterResult(BaseModel):
    """Output from Agent 2 (Writer).

    Attributes:
        variant: The rewritten leadership-focused CV summary variant.
    """

    variant: CVVariant


# ── Agent 2b: Diff ────────────────────────────────────────────────────────────

class DiffResult(BaseModel):
    """Structured change log comparing original and rewritten summaries.

    Attributes:
        variant_label: Which variant this diff describes.
        original_summary: The unmodified summary text.
        new_summary: The rewritten summary text.
        changes: Human-readable list of what changed and why.
    """

    variant_label: str
    original_summary: str
    new_summary: str
    changes: list[str]


# ── Agent 3b: Rescorer ────────────────────────────────────────────────────────

class RescorerResult(BaseModel):
    """Output from Agent 3b (Rescorer).

    Attributes:
        variant_label: Which CV variant was rescored.
        new_aggregate_score: Updated overall score 0–100.
        new_section_scores: Per-section scores after editing.
        score_deltas: Change per section vs original, e.g.
            ``{"summary": +12, "experience": 0}``.
        aggregate_delta: Overall score change vs original.
        soft_gaps_resolved: Soft keywords now present in the edited CV.
        soft_gaps_remaining: Soft keywords still not addressed.
        regressions: Sections whose score dropped after editing.
        gate_passed: True if ``new_aggregate_score >= threshold``.
    """

    variant_label: str
    new_aggregate_score: int = Field(ge=0, le=100)
    new_section_scores: list[SectionScore]
    score_deltas: dict[str, int]
    aggregate_delta: int
    soft_gaps_resolved: list[str]
    soft_gaps_remaining: list[str]
    regressions: list[str]
    gate_passed: bool


# ── Pipeline State ────────────────────────────────────────────────────────────

class PipelineState(BaseModel):
    """Shared state object threaded through the entire pipeline.

    Created once at pipeline start and progressively enriched by each
    agent.  Agents should treat all fields except their own output as
    read-only.

    Attributes:
        run_id: Short random ID for correlating logs.
        company: Target company name.
        role: Job title being applied for.
        created_at: Pipeline start time (UTC).
        job_description: Raw JD text.
        cv_text: Master CV text loaded from disk.
        skills_table: Skills Excel serialised as a markdown table string.
        analysis: Output from Agent 1a.
        writer_result: Output from Agent 2.
        selected_variant: Which CV variant (``"technical"`` / ``"leadership"``)
            was chosen for downstream agents.
        diff_result: Output from Agent 2b.
        rescore_result: Output from Agent 3b.
        vault_path: Absolute path to the Obsidian output folder.
    """

    run_id: str
    company: str
    role: str
    created_at: datetime = Field(default_factory=datetime.now)

    job_description: str
    cv_text: str
    skills_table: str

    analysis: Optional[AnalysisResult] = None
    cover_letter_result: Optional[CoverLetterResult] = None
    writer_result: Optional[WriterResult] = None
    selected_variant: Optional[str] = None
    diff_result: Optional[DiffResult] = None
    rescore_result: Optional[RescorerResult] = None

    vault_path: Optional[str] = None


# ── JD File Metadata ──────────────────────────────────────────────────────────

class JDFileMetadata(BaseModel):
    """Metadata extracted from a JD file in the batch queue.

    Attributes:
        path: Absolute path to the source ``.md`` file.
        company: Target company name (from frontmatter or filename).
        role: Job title (from frontmatter or filename).
        jd_text: Raw job description text with frontmatter stripped.
        threshold: Per-job score threshold override, or ``None`` to use
            the global ``MATCH_SCORE_THRESHOLD``.
        force: If ``True``, bypass Gate 1 for this job regardless of the
            global ``--force`` flag.
    """

    path: Path
    company: str
    role: str
    jd_text: str
    threshold: Optional[int] = None
    force: bool = False


# ── Batch Run Models ──────────────────────────────────────────────────────────

class BatchJobResult(BaseModel):
    """Outcome of a single job in a batch run.

    Attributes:
        company: Target company name.
        role: Job title.
        jd_file: Filename of the source JD file.
        status: One of ``"applied"``, ``"gated_out"``, ``"skipped"``,
            or ``"error"``.
        initial_score: Aggregate score from Agent 1a, or ``None`` if the
            pipeline errored before Agent 1a completed.
        final_score: Rescored aggregate from Agent 3b, or ``None`` if
            the pipeline exited before Agent 3b completed.
        vault_path: Absolute path to the vault output folder, or ``None``
            on error.
        error_message: Exception message if ``status == "error"``.
    """

    company: str
    role: str
    jd_file: str
    status: Literal["applied", "gated_out", "skipped", "error"]
    initial_score: Optional[int] = None
    final_score: Optional[int] = None
    vault_path: Optional[str] = None
    error_message: Optional[str] = None


class BatchRunResult(BaseModel):
    """Aggregate result of a completed (or interrupted) batch run.

    Attributes:
        run_id: Short random ID for correlating vault files.
        started_at: Batch start time.
        completed_at: Batch end time (set even on interrupt).
        total: Total number of JD files discovered.
        applied: Jobs that passed both gates.
        gated_out: Jobs that passed Gate 1 but failed Gate 2.
        skipped: Jobs that failed Gate 1 (analyst said don't apply).
        errors: Jobs where the pipeline raised an exception.
        results: Per-job outcome list.
    """

    run_id: str
    started_at: datetime
    completed_at: datetime
    total: int
    applied: int
    gated_out: int
    skipped: int
    errors: int
    results: list[BatchJobResult]


class CompanyResearchResults(BaseModel):

    """
    
    """

    company :str