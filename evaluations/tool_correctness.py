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
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.evaluate.configs import AsyncConfig
from deepeval.test_case import LLMTestCase, ToolCall


def extract_tools_called(messages):
    tools_called = []
    for message in messages:
        tool_name = getattr(message, "name", None)
        if message.type == "tool" and isinstance(tool_name, str):
            tools_called.append(ToolCall(name=tool_name))
    return tools_called


def main():
    metrics = [
        ToolCorrectnessMetric(
            threshold=0.8,
            model=eval_model,
            include_reason=True,
        )
    ]
    test_cases = []

    for golden in dataset.goldens:
        if golden.expected_tools is None:
            raise ValueError(
                f"Golden case {golden.name or golden.input!r} is missing expected_tools"
            )

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
                tools_called=tools_called,
                expected_tools=golden.expected_tools,
                metadata=golden.additional_metadata,
                comments=golden.comments,
                name=golden.name,
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
