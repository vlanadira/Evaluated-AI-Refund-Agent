import logging
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from deepeval.metrics import ArgumentCorrectnessMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall
from langchain_core.messages import messages_from_dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from agent import refers_to_all_items
from data import users_data
from evaluations.all_evaluation import SUCCESSFUL_TASK_DESCRIPTION, build_metrics
from evaluations.model import eval_model

logger = logging.getLogger("refund_web.evaluation")

ANSWER_CORRECTNESS_CRITERIA = """
Evaluate the assistant's complete customer-support conversation using the full
conversation and tool results provided in the input. Check that the assistant:
- follows the refund and purchase-information policy;
- reports ticket status and amount only when supported by the refund tool result;
- does not promise a refund arrival time that the tool did not confirm;
- refunds only the requested, purchased items and explains ineligible items;
- asks a relevant question when required information or confirmation is missing;
- redirects unrelated requests without using tools or continuing that topic.
Judge the conversation as a whole, not only its final response.
"""

_REFUND_PATTERN = re.compile(r"\brefund(?:s|ed|ing)?\b|\bmoney\s+back\b|\breturn\b", re.I)
_PURCHASE_PATTERN = re.compile(
    r"\bpurchases?\b|\bpurchased\b|\borders?\b|\bbought\b|\bwhat\s+i\s+"
    r"(?:bought|purchased)\b|\bwhat\s+(?:did|have)\s+i\s+"
    r"(?:buy|bought|purchase)\b",
    re.I,
)
_NEGATED_REFUND_PATTERN = re.compile(
    r"\b(?:no|not|never)\s+(?:a\s+)?refund\b"
    r"|\bwithout\s+(?:a\s+)?refund\b"
    r"|\b(?:do\s+not|don't|dont)\s+want\s+(?:a\s+)?refund\b",
    re.I,
)
_AFFIRMATIVE_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|sure|okay|ok|please do|go ahead|that's right|that is right)"
    r"(?:\b|[,!.])",
    re.I,
)


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _message_role(message):
    message_type = getattr(message, "type", None)
    if message_type in {"human", "user"}:
        return "user"
    if message_type in {"ai", "assistant"}:
        return "assistant"
    return None


def _username_from_text(text):
    normalized = text.casefold()
    for username in users_data:
        if re.search(rf"(?<![\w]){re.escape(username.casefold())}(?![\w])", normalized):
            return username
    match = re.search(r"\bcustomer_\d+\b", normalized)
    return match.group(0) if match else None


def _requested_items(user_texts, username):
    purchases = users_data.get(username)
    if not isinstance(purchases, dict):
        return []

    selected = []
    for item_name in purchases:
        normalized_name = re.sub(r"[^a-z0-9]+", " ", item_name.casefold()).strip()
        for text in user_texts:
            normalized_text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
            if re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_name)}(?![a-z0-9])",
                normalized_text,
            ):
                selected.append(item_name)
                break
    return selected


def _expected_tool_names(display_messages, username):
    user_texts = [
        message.get("text", "")
        for message in display_messages
        if message.get("role") == "user"
    ]
    refund_requested = False
    for text in user_texts:
        if _NEGATED_REFUND_PATTERN.search(text):
            refund_requested = False
        elif _REFUND_PATTERN.search(text):
            refund_requested = True

    purchase_question = any(_PURCHASE_PATTERN.search(text) for text in user_texts)
    supported_request = refund_requested or purchase_question
    if not supported_request or username is None:
        return []

    expected = ["get_user_purchase_history"]
    if not refund_requested or username not in users_data:
        return expected

    selected_items = _requested_items(user_texts, username)
    if not selected_items and any(refers_to_all_items(text) for text in user_texts):
        selected_items = list(users_data[username])

    if not selected_items:
        assistant_confirmed_single_purchase = any(
            message.get("role") == "assistant"
            and "would you like to request a refund for" in message.get("text", "").casefold()
            for message in display_messages
        )
        latest_user_text = next(
            (
                message.get("text", "").strip()
                for message in reversed(display_messages)
                if message.get("role") == "user"
            ),
            "",
        )
        if (
            assistant_confirmed_single_purchase
            and _AFFIRMATIVE_PATTERN.search(latest_user_text)
            and len(users_data[username]) == 1
        ):
            selected_items = list(users_data[username])

    if selected_items:
        expected.append("issue_refund_ticket")
    return expected


def _conversation_input(display_messages, agent_messages):
    lines = ["Conversation (chronological):"]
    for message in display_messages:
        role = "Customer" if message.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {message.get('text', '')}")

    tool_results = [
        message
        for message in agent_messages
        if getattr(message, "type", None) == "tool"
    ]
    if tool_results:
        lines.append("\nRecorded tool results:")
        for message in tool_results:
            lines.append(
                f"{getattr(message, 'name', 'tool')}: "
                f"{_content_text(getattr(message, 'content', None))}"
            )
    return "\n".join(lines)


def _actual_output(display_messages):
    return "\n".join(
        f"Assistant: {message.get('text', '')}"
        for message in display_messages
        if message.get("role") == "assistant"
    )


def _build_trace(agent_messages):
    children = []
    pending_tools = {}
    user_inputs = []
    assistant_outputs = []
    current_user_text = ""

    for message in agent_messages:
        role = _message_role(message)
        content = _content_text(getattr(message, "content", None))
        if role == "user":
            current_user_text = content
            user_inputs.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            tool_calls = getattr(message, "tool_calls", []) or []
            if tool_calls:
                for call in tool_calls:
                    tool_name = call.get("name")
                    if not isinstance(tool_name, str):
                        continue
                    span = {
                        "name": tool_name,
                        "type": "tool",
                        "input": call.get("args") or {},
                        "output": None,
                        "children": [],
                    }
                    children.append(span)
                    call_id = call.get("id")
                    if isinstance(call_id, str):
                        pending_tools[call_id] = span
            elif content:
                assistant_outputs.append({"role": "assistant", "content": content})
                children.append(
                    {
                        "name": "Refund assistant response",
                        "type": "llm",
                        "input": current_user_text,
                        "output": content,
                        "children": [],
                    }
                )
            continue

        if getattr(message, "type", None) == "tool":
            call_id = getattr(message, "tool_call_id", None)
            span = pending_tools.get(call_id)
            if span is not None:
                span["output"] = content
            else:
                children.append(
                    {
                        "name": getattr(message, "name", "tool"),
                        "type": "tool",
                        "input": {},
                        "output": content,
                        "children": [],
                    }
                )

    return {
        "name": "Refund support conversation",
        "type": "agent",
        "input": {"messages": user_inputs},
        "output": {"messages": assistant_outputs},
        "availableTools": [
            "get_user_purchase_history",
            "issue_refund_ticket",
        ],
        "children": children,
    }


def build_conversation_test_case(chat):
    agent_messages = messages_from_dict(chat["agentMessages"])
    display_messages = chat["messages"]
    user_texts = [
        message.get("text", "")
        for message in display_messages
        if message.get("role") == "user"
    ]
    username = chat.get("username")
    if not username:
        for text in user_texts:
            username = _username_from_text(text)
            if username:
                break

    calls = []
    for message in agent_messages:
        for call in getattr(message, "tool_calls", []) or []:
            name = call.get("name")
            arguments = call.get("args")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ValueError(f"Invalid tool call in saved conversation: {call!r}")
            calls.append(ToolCall(name=name, input_parameters=arguments))

    test_case = LLMTestCase(
        name=chat["id"],
        input=_conversation_input(display_messages, agent_messages),
        actual_output=_actual_output(display_messages),
        tools_called=calls,
        expected_tools=[
            ToolCall(name=name)
            for name in _expected_tool_names(display_messages, username)
        ],
    )
    test_case._trace_dict = _build_trace(agent_messages)
    return test_case


def _metric_pass(metric, score):
    if score is None:
        return False
    if isinstance(metric.success, bool):
        return metric.success
    threshold = metric.threshold
    return score is not None and threshold is not None and score >= threshold


def evaluate_conversation(chat):
    test_case = build_conversation_test_case(chat)
    trace_metrics, single_turn_metrics = build_metrics()
    metrics = trace_metrics + single_turn_metrics
    for metric in metrics:
        if isinstance(metric, ArgumentCorrectnessMetric):
            metric.threshold = 0.8
    single_turn_metrics[-1] = GEval(
        name="Answer Correctness",
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        criteria=ANSWER_CORRECTNESS_CRITERIA,
        threshold=0.8,
        model=eval_model,
        _include_g_eval_suffix=False,
    )
    metrics = trace_metrics + single_turn_metrics

    results = []
    for metric in metrics:
        name = getattr(metric, "__name__", type(metric).__name__)
        try:
            metric.measure(test_case)
        except Exception as error:
            logger.exception("Chat metric failed: %s", name)
            results.append(
                {
                    "name": name,
                    "score": None,
                    "threshold": metric.threshold,
                    "success": False,
                    "reason": None,
                    "error": str(error),
                }
            )
            continue

        score = metric.score
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
        ):
            score = None
        results.append(
            {
                "name": name,
                "score": score,
                "threshold": metric.threshold,
                "success": _metric_pass(metric, score),
                "reason": str(metric.reason) if metric.reason is not None else None,
                "error": str(metric.error) if metric.error is not None else None,
            }
        )

    scores = [metric["score"] for metric in results if metric["score"] is not None]
    passed = sum(metric["success"] is True for metric in results)
    failed = sum(metric["success"] is False for metric in results)
    return {
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "totalMetrics": len(results),
        "passed": passed,
        "failed": failed,
        "passRate": passed / (passed + failed) if passed + failed else None,
        "averageScore": sum(scores) / len(scores) if scores else None,
        "metrics": results,
        "transcript": chat["messages"],
        "toolsCalled": [
            {
                "name": call.name,
                "arguments": call.input_parameters,
            }
            for call in test_case.tools_called
        ],
    }
