import json
import re
import threading
import time
from typing import Any, cast

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolParam,
)

from src.analyst.config import CONFIG

HEARTBEAT_INTERVAL = 10.0


def _call_with_heartbeat(fn, label: str = "Waiting for model"):
    """Run a blocking call while printing elapsed-time progress every few seconds.

    Streaming adds complexity and resource overhead; a heartbeat gives the user a
    regular "still working" signal during long LLM calls without changing the API.
    """
    stop = threading.Event()

    def tick():
        start = time.monotonic()
        while not stop.wait(HEARTBEAT_INTERVAL):
            print(f"    ...{label} ({time.monotonic() - start:.0f}s elapsed)", flush=True)

    thread = threading.Thread(target=tick, daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop.set()
        thread.join(timeout=0.5)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Execute Python code on the DataFrame. The DataFrame is available as 'df'. Use pandas for data manipulation. Print results to see output.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Python code to execute"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Provide the final answer to the user's question. Use this after you have gathered enough information from executing code.",
            "parameters": {
                "type": "object",
                "properties": {"answer": {"type": "string", "description": "The final answer to the user's question"}},
                "required": ["answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_metric",
            "description": "Look up a metric definition from the project's metric catalog. Returns the precise business formula and description for any KPI or operational metric. Use this to get exact formulas instead of guessing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the metric to look up (e.g., 'Revenue Growth Trajectory')",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "traverse_graph",
            "description": "Explore relationships in the knowledge graph. Given a node name, returns connected nodes and their relationship types. Use this to understand what influences a metric, what a metric depends on, or what business goals it supports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "string",
                        "description": "The name or ID of the node to explore (e.g., 'Revenue', 'Discount %')",
                    },
                    "relation": {
                        "type": "string",
                        "description": "Optional: filter by relationship type (e.g., 'INFLUENCES', 'DERIVED_FROM', 'SUPPORTS'). Leave empty to show all.",
                    },
                },
                "required": ["node"],
            },
        },
    },
]


def get_client() -> OpenAI:
    return OpenAI(base_url=CONFIG.base_url, api_key="not-needed", timeout=CONFIG.llm_timeout_seconds)


def _retry(fn, *args, **kwargs):
    last_error: Exception | None = None
    for attempt in range(CONFIG.max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < CONFIG.max_retries - 1:
                delay = CONFIG.retry_base_delay * (2**attempt)
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry loop exhausted without error")  # unreachable: max_retries >= 1


def check_availability() -> bool:
    try:
        client = get_client()
        _retry(client.models.list)
        return True
    except Exception:
        return False


def ask(user_question: str, system_context: str = "", temperature: float = 0.3, label: str = "Waiting for model") -> str:
    client = get_client()
    messages = []
    if system_context:
        messages.append({"role": "system", "content": system_context})
    messages.append({"role": "user", "content": user_question})

    def call():
        response = client.chat.completions.create(
            model=CONFIG.model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            temperature=temperature,
            max_tokens=CONFIG.max_tokens,
            extra_body={"thinking_budget_tokens": CONFIG.thinking_budget_tokens},
        )
        message = response.choices[0].message
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            print(f"    ...reasoning content: {len(reasoning)} chars", flush=True)
        return message.content

    return _call_with_heartbeat(lambda: _retry(call), label)


def ask_json(
    user_question: str, system_context: str = "", temperature: float = 0.1, retries: int = 2, label: str = "Waiting for model"
) -> dict:
    for attempt in range(retries + 1):
        response = ask(user_question, system_context, temperature=temperature, label=label)
        result = extract_json(response)
        if result:
            return result
        if attempt < retries:
            user_question = (
                "Your previous response was not valid JSON. Respond with ONLY a valid JSON object, no other text.\n\n"
                + user_question
            )
    return {}


def extract_json(response: str) -> dict:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{[\s\S]*?\})\s*$", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\[[\s\S]*?\])\s*$", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return {}


def chat_with_tools(
    messages: list,
    tools: list[Any] | None = None,
    temperature: float = 0.2,
    tool_choice: str = "auto",
    label: str = "Waiting for model",
):
    client = get_client()
    if tools is None:
        tools = TOOLS

    def call():
        response = client.chat.completions.create(
            model=CONFIG.model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            tools=cast("list[ChatCompletionToolParam]", tools),
            tool_choice=cast("ChatCompletionToolChoiceOptionParam", tool_choice),
            temperature=temperature,
            extra_body={"thinking_budget_tokens": CONFIG.thinking_budget_tokens},
        )
        return response.choices[0].message

    return _call_with_heartbeat(lambda: _retry(call), label)
