"""Configuration loaded from environment variables and CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_FILE = PROJECT_ROOT / "data" / "students.xlsx"
DEFAULT_COMPLETION_FILE = PROJECT_ROOT / "data" / "results.completed.json"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_INPUT_SHEET = "اطلاعات نوآموزان"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSER_CONNECT_TIMEOUT_MS = 15_000
# Zero means wait indefinitely for the user's manual CAPTCHA/Search action.
DEFAULT_PAGE_TRANSITION_TIMEOUT_MS = 0
DEFAULT_ACTION_TIMEOUT_MS = 15_000


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(slots=True)
class AppConfig:
    """Runtime settings with conservative defaults."""

    input_file: Path = DEFAULT_INPUT_FILE
    completion_file: Path = DEFAULT_COMPLETION_FILE
    log_dir: Path = DEFAULT_LOG_DIR
    input_sheet: str = DEFAULT_INPUT_SHEET
    cdp_url: str = DEFAULT_CDP_URL
    sida_start_url: str | None = None
    browser_connect_timeout_ms: int = DEFAULT_BROWSER_CONNECT_TIMEOUT_MS
    page_transition_timeout_ms: int = DEFAULT_PAGE_TRANSITION_TIMEOUT_MS
    action_timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS
    inquiry_retry_delay_ms: int = 3_000
    inquiry_max_attempts: int = 5
    grade_response_timeout_ms: int = 10_000
    grade_retry_delay_ms: int = 6_000
    captcha_retry_delay_ms: int = 5_000
    student_registry_error_delay_ms: int = 4_000
    grade_preferences: tuple[str, ...] = field(
        default=("پیش دبستانی یک", "پیش دبستانی دو", "نوباوه")
    )

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            input_file=Path(os.getenv("SIDA_INPUT_FILE", str(DEFAULT_INPUT_FILE))),
            completion_file=Path(
                os.getenv("SIDA_COMPLETION_FILE", str(DEFAULT_COMPLETION_FILE))
            ),
            log_dir=Path(os.getenv("SIDA_LOG_DIR", str(DEFAULT_LOG_DIR))),
            input_sheet=os.getenv("SIDA_INPUT_SHEET", DEFAULT_INPUT_SHEET),
            cdp_url=os.getenv("SIDA_CDP_URL", DEFAULT_CDP_URL),
            sida_start_url=os.getenv("SIDA_START_URL") or None,
            browser_connect_timeout_ms=_env_int(
                "SIDA_BROWSER_CONNECT_TIMEOUT_MS", DEFAULT_BROWSER_CONNECT_TIMEOUT_MS
            ),
            page_transition_timeout_ms=_env_int(
                "SIDA_PAGE_TRANSITION_TIMEOUT_MS", DEFAULT_PAGE_TRANSITION_TIMEOUT_MS
            ),
            action_timeout_ms=_env_int(
                "SIDA_ACTION_TIMEOUT_MS", DEFAULT_ACTION_TIMEOUT_MS
            ),
        )

    def ensure_runtime_directories(self) -> None:
        self.input_file.parent.mkdir(parents=True, exist_ok=True)
        self.completion_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
