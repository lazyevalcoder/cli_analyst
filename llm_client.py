import json
import re
import time

from openai import OpenAI

from config import CONFIG

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Execute Python code on the DataFrame. The DataFrame is available as 'df'. Use pandas for data manipulation. Print results to see output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Provide the final answer to the user's question. Use this after you have gathered enough information from executing code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "The final answer to the user's question"
                    }
                },
                "required": ["answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_metric",
            "description": "Look up a metric definition from the project's metric catalog. Returns the precise business formula and description for any KPI or supporting metric. Use this to get exact formulas instead of guessing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the metric to look up (e.g., 'Revenue Growth Trajectory')"
                    }
                },
                "required": ["name"]
            }
        }
    }
]


def get_client() -> OpenAI:
    return OpenAI(base_url=CONFIG.base_url, api_key="not-needed")


def _retry(fn, *args, **kwargs):
    last_error = None
    for attempt in range(CONFIG.max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < CONFIG.max_retries - 1:
                delay = CONFIG.retry_base_delay * (2 ** attempt)
                time.sleep(delay)
    raise last_error


def check_availability() -> bool:
    try:
        client = get_client()
        _retry(client.models.list)
        return True
    except Exception:
        return False


def ask(user_question: str, system_context: str = "", temperature: float = 0.3) -> str:
    client = get_client()
    messages = []
    if system_context:
        messages.append({"role": "system", "content": system_context})
    messages.append({"role": "user", "content": user_question})

    def call():
        response = client.chat.completions.create(
            model=CONFIG.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    return _retry(call)


def ask_json(user_question: str, system_context: str = "", temperature: float = 0.1, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        response = ask(user_question, system_context, temperature=temperature)
        result = extract_json(response)
        if result:
            return result
        if attempt < retries:
            user_question = "Your previous response was not valid JSON. Respond with ONLY a valid JSON object, no other text.\n\n" + user_question
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


def chat_with_tools(messages: list, tools: list = None, temperature: float = 0.2, tool_choice: str = "auto"):
    client = get_client()
    if tools is None:
        tools = TOOLS

    def call():
        response = client.chat.completions.create(
            model=CONFIG.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
        )
        return response.choices[0].message

    return _retry(call)
