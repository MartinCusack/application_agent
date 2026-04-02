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
    COVER_LETTER_TEMPLATE_PATH: Path = Path(os.getenv("COVER_LETTER_TEMPLATE_PATH", "data/cover_letter.md"))
    COVER_LETTER_RUBRIC_PATH: Path = Path(os.getenv("COVER_LETTER_RUBRIC_PATH", "data/cover_letter_rubric.md"))


config = Config()
