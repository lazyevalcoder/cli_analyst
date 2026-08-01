from dataclasses import dataclass, field
from os import environ


@dataclass
class Config:
    base_url: str = field(default_factory=lambda: environ.get("LLM_BASE_URL", "http://localhost:8080/v1"))
    model: str = field(default_factory=lambda: environ.get("LLM_MODEL", "local"))
    max_iterations: int = field(default_factory=lambda: int(environ.get("MAX_ITERATIONS", "15")))
    continuation_block: int = field(default_factory=lambda: int(environ.get("CONTINUATION_BLOCK", "5")))
    max_output_chars: int = field(default_factory=lambda: int(environ.get("MAX_OUTPUT_CHARS", "3000")))
    timeout_seconds: int = field(default_factory=lambda: int(environ.get("TIMEOUT_SECONDS", "30")))
    max_retries: int = field(default_factory=lambda: int(environ.get("MAX_RETRIES", "3")))
    retry_base_delay: float = field(default_factory=lambda: float(environ.get("RETRY_BASE_DELAY", "1.0")))
    temperature_json: float = 0.1
    temperature_code: float = 0.2
    temperature_synthesis: float = 0.4


CONFIG = Config()
