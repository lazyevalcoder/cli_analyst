from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load(name: str) -> str:
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def format(template: str, **kwargs: str) -> str:
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template


def render(name: str, **kwargs: str) -> str:
    """Load a prompt file and fill its `{placeholders}` in one call."""
    return format(load(name), **kwargs)


def load_reasoning_framework() -> str:
    path = PROMPTS_DIR / "reasoning_framework.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def extract_strategy_section(strategy_name: str) -> str:
    framework = load_reasoning_framework()
    if not framework or not strategy_name:
        return ""

    lines = framework.split("\n")
    out = []
    capturing = False
    found_header = False

    for line in lines:
        if line.startswith("### Strategy") and strategy_name.lower() in line.lower():
            capturing = True
            found_header = True
        elif capturing and line.startswith("### Strategy") and found_header:
            break
        if capturing:
            out.append(line)

    return "\n".join(out)
