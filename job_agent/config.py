"""Application configuration loaded from environment variables."""

from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for the job application pipeline.

    All values are read from environment variables, with sensible defaults
    for local development. Copy ``.env.example`` to ``.env`` and fill in
    your own values before running.

    Attributes:
        MODEL_PROVIDER: Which LLM provider to use: ``"anthropic"`` or ``"openai"``.
        MODEL_NAME: Model identifier for the chosen provider.
        ANTHROPIC_API_KEY: Secret key for the Anthropic Claude API.
        OPENAI_API_KEY: Secret key for the OpenAI API.
        CV_PATH: Path to the master CV file (markdown or plain text).
        SKILLS_TABLE_PATH: Path to the Excel skills table.
        OBSIDIAN_VAULT_PATH: Root folder inside your Obsidian vault where
            per-application subfolders will be created.
        MATCH_SCORE_THRESHOLD: Minimum aggregate score (0–100) required to
            proceed past the analysis stage.
        OBSIDIAN_LIST_PATH: Root folder scanned by ``list-applications``.
            Defaults to ``OBSIDIAN_VAULT_PATH`` when unset.  Set this to a
            parent directory (e.g. ``application_status/``) if your vault
            organises applications across multiple subdirectories.
        BATCH_TODO_DIR: Directory scanned by ``batch-apply`` for pending JD
            files.  Subdirectories ``applied/``, ``gated_out/``, ``skipped/``,
            and ``failed/`` are created as siblings of this directory.
        BATCH_DELAY_SECONDS: Pause between pipeline runs in batch mode to
            avoid hitting API rate limits.
    """

    MODEL_PROVIDER: str = os.getenv("MODEL_PROVIDER", "anthropic")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-sonnet-4-6")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    CV_PATH: Path = Path(os.getenv("CV_PATH", "data/cv.md"))
    SKILLS_TABLE_PATH: Path = Path(os.getenv("SKILLS_TABLE_PATH", "data/skills.xlsx"))
    OBSIDIAN_VAULT_PATH: Path = Path(
        os.getenv("OBSIDIAN_VAULT_PATH", "~/Documents/vault/thoughts-and-dreams/Job_hunt/Job_applications/companies/")
    )
    MATCH_SCORE_THRESHOLD: int = int(os.getenv("MATCH_SCORE_THRESHOLD", "60"))
    OBSIDIAN_LIST_PATH: Path = Path(
        os.getenv("OBSIDIAN_LIST_PATH", os.getenv("OBSIDIAN_VAULT_PATH", "~/Documents/vault/thoughts-and-dreams/Job_hunt/Job_applications/companies/"))
    )
    COVER_LETTER_TEMPLATE_PATH: Path = Path(os.getenv("COVER_LETTER_TEMPLATE_PATH", "data/cover_letter.md"))
    COVER_LETTER_RUBRIC_PATH: Path = Path(os.getenv("COVER_LETTER_RUBRIC_PATH", "data/cover_letter_rubric.md"))
    BATCH_TODO_DIR: Path = Path(os.getenv("BATCH_TODO_DIR", "job_descriptions/TODO"))
    BATCH_DELAY_SECONDS: float = float(os.getenv("BATCH_DELAY_SECONDS", "2.0"))


config = Config()
