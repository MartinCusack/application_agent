"""Shared pytest fixtures for the job agent test suite.

Fixtures are organised by scope:
- ``session`` — expensive objects built once per test run (sample data)
- ``function`` — fresh objects per test (mutable state, tmp paths)
"""

import pytest

from job_agent.models import (
    AnalysisResult,
    CoverLetterResult,
    CVVariant,
    DiffResult,
    MissingKeyword,
    PipelineState,
    RescorerResult,
    ScoringRubric,
    SectionScore,
    WriterResult,
)


# ── Sample text ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_cv_text() -> str:
    """Minimal two-section CV in markdown format."""
    return (
        "## Summary\n"
        "Experienced data scientist with 5 years in pharma.\n\n"
        "## Experience\n"
        "Senior Data Scientist, Acme Corp, 2020–present\n"
        "- Built ML models for clinical trial outcome prediction.\n"
    )


@pytest.fixture(scope="session")
def sample_skills_table() -> str:
    """Minimal markdown skills table string."""
    return (
        "| Skill  | Category    | Proficiency | Projects          | Roles               | Years |\n"
        "|--------|-------------|-------------|-------------------|---------------------|-------|\n"
        "| Python | Programming | Expert      | Clinical pipeline | Senior Data Scientist | 5   |\n"
    )


@pytest.fixture(scope="session")
def sample_job_description() -> str:
    """Short synthetic job description for testing."""
    return (
        "We are looking for a Senior Data Scientist with Python, machine learning, "
        "and FDA regulatory experience to join our medtech team."
    )


# ── Model instances ───────────────────────────────────────────────────────────

@pytest.fixture
def scoring_rubric() -> ScoringRubric:
    """Minimal ``ScoringRubric`` with two keywords and equal weights."""
    return ScoringRubric(
        keywords_identified=["Python", "FDA"],
        section_weights={"summary": 0.3, "experience": 0.5, "skills": 0.2},
        recency_flagged_keywords=[],
    )


@pytest.fixture
def soft_keyword() -> MissingKeyword:
    """A single soft-missing keyword fixture."""
    return MissingKeyword(
        keyword="machine learning",
        gap_type="soft",
        rationale="Candidate has ML experience but uses 'predictive modelling'.",
    )


@pytest.fixture
def hard_keyword() -> MissingKeyword:
    """A single hard-missing keyword fixture."""
    return MissingKeyword(
        keyword="FDA 510k",
        gap_type="hard",
        rationale="Candidate has no regulatory submission experience.",
        addressable_with_existing_skills=False,
        upskill_timeframe="12+ months",
    )


@pytest.fixture
def recency_keyword() -> MissingKeyword:
    """A single recency-gap keyword fixture."""
    return MissingKeyword(
        keyword="LangChain",
        gap_type="recency",
        rationale="Candidate has 1 year hands-on; field is <2 years old.",
    )


@pytest.fixture
def analysis_result(scoring_rubric, soft_keyword, hard_keyword, recency_keyword) -> AnalysisResult:
    """Passing ``AnalysisResult`` (score 75, proceed=True)."""
    return AnalysisResult(
        aggregate_score=75,
        section_scores=[
            SectionScore(section="summary", score=70, rationale="Good but missing ML phrasing."),
            SectionScore(section="experience", score=80, rationale="Strong clinical background."),
            SectionScore(section="skills", score=65, rationale="Missing regulatory keywords."),
        ],
        hard_missing=[hard_keyword],
        soft_missing=[soft_keyword],
        recency_gaps=[recency_keyword],
        transferable_strengths=["Regulatory experience (FDA, ISO 13485) rare in ML candidates."],
        proceed_with_application=True,
        proceed_rationale="Score above threshold; soft gaps are addressable.",
        rubric=scoring_rubric,
    )


@pytest.fixture
def failing_analysis_result(scoring_rubric, hard_keyword) -> AnalysisResult:
    """``AnalysisResult`` that recommends not applying (score 40)."""
    return AnalysisResult(
        aggregate_score=40,
        section_scores=[
            SectionScore(section="summary", score=35, rationale="Large keyword gaps."),
            SectionScore(section="experience", score=45, rationale="Unrelated industry."),
            SectionScore(section="skills", score=40, rationale="Core skills missing."),
        ],
        hard_missing=[hard_keyword],
        soft_missing=[],
        recency_gaps=[],
        transferable_strengths=[],
        proceed_with_application=False,
        proceed_rationale="Score below threshold and blocking hard gaps present.",
        rubric=scoring_rubric,
    )


@pytest.fixture
def cover_letter_result() -> CoverLetterResult:
    """``CoverLetterResult`` with jd_signals, cover letter, and tailoring notes."""
    return CoverLetterResult(
        jd_signals=[
            "AI-powered diagnostics platform",
            "ISO 13485 compliance",
            "Series B growth stage",
        ],
        cover_letter="Dear Hiring Team, ...",
        tailoring_notes=[
            "Filled [COMPANY_MISSION] with 'AI-powered diagnostics platform' from JD para 1",
        ],
    )


@pytest.fixture
def writer_result() -> WriterResult:
    """``WriterResult`` with a single leadership variant."""
    return WriterResult(
        variant=CVVariant(
            label="leadership",
            summary_section="Led cross-functional data science team to deliver ML solutions improving clinical outcomes.",
            changes_made=["Emphasised team leadership and stakeholder outcomes"],
            skills_rows_cited=["Python | Programming | Expert"],
        )
    )


@pytest.fixture
def diff_result() -> DiffResult:
    """Minimal ``DiffResult`` for the technical variant."""
    return DiffResult(
        variant_label="technical",
        original_summary="Experienced data scientist with 5 years in pharma.",
        new_summary="Accomplished ML pipeline delivery as measured by 20% accuracy improvement.",
        changes=["Replaced 'predictive modelling' with 'machine learning' (soft gap)"],
    )


@pytest.fixture
def passing_rescore_result() -> RescorerResult:
    """``RescorerResult`` that passes the gate (score 85)."""
    return RescorerResult(
        variant_label="technical",
        new_aggregate_score=85,
        new_section_scores=[
            SectionScore(section="summary", score=82, rationale="Soft gap resolved."),
            SectionScore(section="experience", score=88, rationale="Unchanged."),
            SectionScore(section="skills", score=80, rationale="Keywords now present."),
        ],
        score_deltas={"summary": 12, "experience": 8, "skills": 15},
        aggregate_delta=10,
        soft_gaps_resolved=["machine learning"],
        soft_gaps_remaining=[],
        regressions=[],
        gate_passed=True,
    )


@pytest.fixture
def failing_rescore_result() -> RescorerResult:
    """``RescorerResult`` that fails the gate (score 55)."""
    return RescorerResult(
        variant_label="technical",
        new_aggregate_score=55,
        new_section_scores=[
            SectionScore(section="summary", score=60, rationale="Marginal improvement."),
            SectionScore(section="experience", score=55, rationale="Still missing keywords."),
            SectionScore(section="skills", score=50, rationale="Core skills absent."),
        ],
        score_deltas={"summary": 5, "experience": 0, "skills": -5},
        aggregate_delta=-5,
        soft_gaps_resolved=[],
        soft_gaps_remaining=["machine learning"],
        regressions=["skills"],
        gate_passed=False,
    )


@pytest.fixture
def pipeline_state(
    sample_cv_text,
    sample_skills_table,
    sample_job_description,
) -> PipelineState:
    """Minimal ``PipelineState`` with no agent outputs populated."""
    return PipelineState(
        run_id="abc12345",
        company="Acme Corp",
        role="Senior Data Scientist",
        job_description=sample_job_description,
        cv_text=sample_cv_text,
        skills_table=sample_skills_table,
    )
