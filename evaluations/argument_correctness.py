import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "agent")
)

from agent import agent
from dataset import dataset
from model import eval_model

from deepeval import evaluate
from deepeval.metrics import ArgumentCorrectnessMetric
from deepeval.evaluate.configs import AsyncConfig
from deepeval.test_case import LLMTestCase, ToolCall


def extract_tools_called(messages):
    tools_called = []
    for message in messages:
        for tool_call in getattr(message, "tool_calls", []):
            tool_name = tool_call.get("name")
            input_parameters = tool_call.get("args")
            if not isinstance(tool_name, str) or not isinstance(input_parameters, dict):
                raise ValueError(f"Invalid arguments in tool call: {tool_call!r}")
            tools_called.append(
                ToolCall(
                    name=tool_name,
                    input_parameters=input_parameters,
                )
            )
    return tools_called


def main():
    metrics = [
        ArgumentCorrectnessMetric(
            threshold=0.8,
            model=eval_model,
            include_reason=True,
        )
    ]
    test_cases = []

    for golden in dataset.goldens:
        response = agent.invoke(
            {"messages": [{"role": "user", "content": golden.input}]},
            config={
                "configurable": {
                    "thread_id": str(uuid4())
                }
            }
        )
        messages = response["messages"]
        tools_called = extract_tools_called(messages)
        final_output = next(
            (
                str(message.content)
                for message in reversed(messages)
                if message.type == "ai" and not message.tool_calls
            ),
            None,
        )

        test_cases.append(
            LLMTestCase(
                input=golden.input,
                actual_output=final_output,
                expected_output=golden.expected_output,
                metadata=golden.additional_metadata,
                comments=golden.comments,
                name=golden.name,
                tools_called=tools_called,
            )
        )

    evaluate(
        test_cases=test_cases,
        metrics=metrics,
        async_config=AsyncConfig(
            max_concurrent=1,
            throttle_value=15,
        ),
    )


if __name__ == "__main__":
    main()
