"""Agent classes that call Claude and parse structured JSON responses.

Each public agent class corresponds to one pipeline stage.  All agents
inherit from ``BaseAgent``, which owns the LLM client and JSON extraction
logic so individual agents stay focused on prompt wiring only.

Typical usage::

    from job_agent.agents import AnalystAgent
    result = AnalystAgent().run(cv_text, skills_table, job_description)
"""

import json
import re
import time
from typing import Type, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

import job_agent.prompts as prompts
from job_agent.config import config
from job_agent.models import (
    AnalysisResult,
    CoverLetterResult,
    DiffResult,
    RescorerResult,
    WriterResult,
)

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubled on each subsequent attempt


def _build_llm(model: str):
    """Instantiate the correct LangChain chat model based on ``config.MODEL_PROVIDER``."""
    if config.MODEL_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=config.OPENAI_API_KEY, max_tokens=4096)
    return ChatAnthropic(model=model, api_key=config.ANTHROPIC_API_KEY, max_tokens=4096)


class BaseAgent:
    """Shared LLM client and response-parsing logic for all agents.

    Args:
        model: Model identifier for the configured provider.  Defaults to ``config.MODEL_NAME``.
    """

    def __init__(self, model: str = config.MODEL_NAME) -> None:
        self.llm = _build_llm(model)

    def _call(self, system: str, human: str, output_model: Type[T]) -> T:
        """Send a prompt pair to Claude and parse the JSON response.

        Retries up to ``_MAX_RETRIES`` times with exponential backoff.  On each
        failure the bad response is appended to the message history and a strict
        correction prompt is added so the model knows exactly what went wrong.

        Args:
            system: System prompt setting the agent's persona and rules.
            human: Human prompt containing the filled-in template.
            output_model: Pydantic model class to validate the response against.

        Returns:
            A validated instance of ``output_model``.

        Raises:
            ValueError: If Claude returns text that cannot be parsed as JSON
                after all retry attempts.
            ValidationError: If the parsed JSON does not conform to
                ``output_model``'s schema after all retry attempts.
        """
        messages: list[BaseMessage] = [
            SystemMessage(content=system),
            HumanMessage(content=human),
        ]

        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                time.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))

            response = self.llm.invoke(messages)
            raw: str = response.content  # type: ignore[assignment]

            # Strip optional markdown code fences Claude sometimes wraps JSON in
            match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
            json_str = match.group(1) if match else raw

            data: dict[str, object] = {}
            parse_error: Exception | None = None
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as exc:
                parse_error = exc

            if parse_error is None:
                try:
                    return output_model.model_validate(data)
                except ValidationError as exc:
                    parse_error = exc

            is_last = attempt == _MAX_RETRIES - 1
            if is_last:
                if isinstance(parse_error, json.JSONDecodeError):
                    raise ValueError(
                        f"{self.__class__.__name__} returned invalid JSON after"
                        f" {_MAX_RETRIES} attempts: {parse_error}\n\n"
                        f"Raw response:\n{raw}"
                    ) from parse_error
                raise parse_error  # type: ignore[misc]

            if isinstance(parse_error, json.JSONDecodeError):
                correction = (
                    "Your previous response was not valid JSON. "
                    "Respond ONLY with a valid JSON object matching the required schema. "
                    "Do not include any explanation, markdown fences, or other text."
                )
            else:
                schema_str = json.dumps(output_model.model_json_schema(), indent=2)
                correction = (
                    f"Your previous response did not match the required schema. "
                    f"Error: {parse_error}\n\n"
                    f"Respond ONLY with a valid JSON object matching this exact schema:\n"
                    f"{schema_str}\n"
                    "Do not include any explanation, markdown fences, or other text."
                )

            messages = [
                *messages,
                AIMessage(content=raw),
                HumanMessage(content=correction),
            ]

        raise RuntimeError("unreachable")  # pragma: no cover


class AnalystAgent(BaseAgent):
    """Agent 1a — analyses CV fit against a job description.

    Produces section-level scores, a hard/soft keyword gap split, and a
    scoring rubric that is forwarded to downstream agents unchanged.
    """

    def run(
        self,
        cv_text: str,
        skills_table: str,
        job_description: str,
    ) -> AnalysisResult:
        """Run the deep analyst against a single job description.

        Args:
            cv_text: Full text of the candidate's master CV.
            skills_table: Skills Excel serialised as a markdown table string.
            job_description: Raw text of the target job description.

        Returns:
            ``AnalysisResult`` with aggregate score, section scores, gap
            classification, and the rubric object for downstream reuse.
        """
        human = prompts.ANALYST_HUMAN.format(
            cv_text=cv_text,
            skills_table=skills_table,
            job_description=job_description,
        )
        return self._call(prompts.ANALYST_SYSTEM, human, AnalysisResult)


class CoverLetterAgent(BaseAgent):
    """Agent 1b — tailors the cover letter template for a specific role.

    Fills bracketed placeholders using the job description and analysis,
    reproduces the body paragraph verbatim, and applies the quality rubric.
    """

    def run(
        self,
        cover_letter_template: str,
        cover_letter_rubric: str,
        job_description: str,
        company: str,
        role: str,
        analysis: AnalysisResult,
    ) -> CoverLetterResult:
        """Tailor the cover letter template for a single application.

        Args:
            cover_letter_template: Raw template text with bracketed placeholders.
            cover_letter_rubric: Rubric markdown used to enforce quality rules.
            job_description: Raw text of the target job description.
            company: Target company name.
            role: Job title being applied for.
            analysis: Output from ``AnalystAgent.run()`` — transferable
                strengths and soft gaps are woven into the letter.

        Returns:
            ``CoverLetterResult`` with the complete tailored letter and a
            list of tailoring notes describing each change made.
        """
        human = prompts.COVER_LETTER_HUMAN.format(
            cover_letter_template=cover_letter_template,
            cover_letter_rubric=cover_letter_rubric,
            job_description=job_description,
            company=company,
            role=role,
            transferable_strengths=json.dumps(analysis.transferable_strengths, indent=2),
            soft_missing=json.dumps(
                [m.model_dump() for m in analysis.soft_missing], indent=2
            ),
        )
        return self._call(prompts.COVER_LETTER_SYSTEM, human, CoverLetterResult)


class WriterAgent(BaseAgent):
    """Agent 2 — rewrites the CV summary to target the role.

    Produces a single leadership-focused variant.  Hard gaps are
    explicitly passed so the agent cannot accidentally address them.
    """

    def run(
        self,
        cv_text: str,
        skills_table: str,
        analysis: AnalysisResult,
    ) -> WriterResult:
        """Rewrite the summary section based on the analyst's gap report.

        Args:
            cv_text: Full text of the candidate's master CV.
            skills_table: Skills Excel serialised as a markdown table string.
            analysis: Output from ``AnalystAgent.run()``.  The hard/soft split
                and keyword list are extracted and injected into the prompt.

        Returns:
            ``WriterResult`` containing a single leadership ``CVVariant``.
        """
        human = prompts.WRITER_HUMAN.format(
            cv_text=cv_text,
            skills_table=skills_table,
            soft_missing=json.dumps(
                [m.model_dump() for m in analysis.soft_missing], indent=2
            ),
            hard_missing=json.dumps(
                [m.model_dump() for m in analysis.hard_missing], indent=2
            ),
            keywords=json.dumps(analysis.rubric.keywords_identified, indent=2),
        )
        return self._call(prompts.WRITER_SYSTEM, human, WriterResult)


class DiffAgent(BaseAgent):
    """Agent 2b — produces a structured change log between CV versions."""

    def run(
        self,
        original_summary: str,
        new_summary: str,
        variant_label: str,
    ) -> DiffResult:
        """Compare original and rewritten summary sections.

        Args:
            original_summary: The unmodified summary text extracted from the CV.
            new_summary: The rewritten summary text from ``WriterAgent``.
            variant_label: Which variant is being diffed, e.g. ``"technical"``.

        Returns:
            ``DiffResult`` with a human-readable list of changes and their
            rationale.
        """
        human = prompts.DIFF_HUMAN.format(
            original_summary=original_summary,
            new_summary=new_summary,
            variant_label=variant_label,
        )
        return self._call(prompts.DIFF_SYSTEM, human, DiffResult)


class RescorerAgent(BaseAgent):
    """Agent 3b — rescores the edited CV using the original rubric.

    Using the same ``ScoringRubric`` object from ``AnalystAgent`` ensures
    score deltas are meaningful and not contaminated by criterion drift.
    """

    def run(
        self,
        full_cv: str,
        job_description: str,
        analysis: AnalysisResult,
        variant_label: str,
        threshold: int = config.MATCH_SCORE_THRESHOLD,
    ) -> RescorerResult:
        """Rescore an edited CV and compute deltas vs the original.

        Args:
            full_cv: The full CV text with the rewritten summary substituted in.
            job_description: Raw text of the target job description.
            analysis: Original ``AnalysisResult`` whose rubric and scores are
                used as the baseline.
            variant_label: Which variant is being rescored.
            threshold: Pass/fail gate; defaults to ``config.MATCH_SCORE_THRESHOLD``.

        Returns:
            ``RescorerResult`` with new scores, deltas, regression flags, and
            a boolean ``gate_passed`` field.
        """
        original_section_scores = {
            s.section: s.score for s in analysis.section_scores
        }
        human = prompts.RESCORER_HUMAN.format(
            full_cv=full_cv,
            job_description=job_description,
            keywords=json.dumps(analysis.rubric.keywords_identified, indent=2),
            section_weights=json.dumps(analysis.rubric.section_weights, indent=2),
            original_aggregate=analysis.aggregate_score,
            original_section_scores=json.dumps(original_section_scores, indent=2),
            soft_missing=json.dumps(
                [m.keyword for m in analysis.soft_missing], indent=2
            ),
            threshold=threshold,
            variant_label=variant_label,
        )
        return self._call(prompts.RESCORER_SYSTEM, human, RescorerResult)


