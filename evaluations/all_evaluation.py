import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from deepeval import evaluate
from deepeval.evaluate import CacheConfig, DisplayConfig
from deepeval.integrations.langchain import CallbackHandler
from deepeval.metrics import (
    ArgumentCorrectnessMetric,
    GEval,
    PlanAdherenceMetric,
    PlanQualityMetric,
    StepEfficiencyMetric,
    TaskCompletionMetric,
    ToolCorrectnessMetric,
)
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall

if __package__:
    from .dataset import dataset
    from .model import eval_model
else:
    from dataset import dataset
    from model import eval_model


SUCCESSFUL_TASK_DESCRIPTION = """
For a refund request without a username, ask the user to provide it before looking up purchases.
For a refund request, identify the customer and the requested purchases, and
check that each purchase is no more than 30 days old and is not in the future.
Refund only the items requested by the user. If the customer or requested item
cannot be found, do not issue a refund ticket and explain why.
Once the necessary information is available, tell the user whether a refund
ticket was issued and its amount, or explain why no refund was issued.
When mentioning purchases, use readable product names instead of internal item
identifiers with underscores. Keep exact identifiers only in tool calls.
For a purchase-information request, list the available purchases without issuing a ticket.
For unrelated requests, briefly state that you only handle refunds and purchase questions, then redirect the user without continuing the unrelated conversation or using tools.
"""


def build_metrics():
    """Keep the thresholds and evaluator model used by the individual scripts."""
    trace_metrics = [
        TaskCompletionMetric(
            threshold=0.8,
            model=eval_model,
            task=SUCCESSFUL_TASK_DESCRIPTION,
            include_reason=True,
        ),
        StepEfficiencyMetric(
            threshold=0.8, model=eval_model, include_reason=True,
        ),
        PlanQualityMetric(
            threshold=0.8, model=eval_model, include_reason=True,
        ),
        PlanAdherenceMetric(
            threshold=0.8, model=eval_model, include_reason=True,
        ),
    ]
    single_turn_metrics = [
        ArgumentCorrectnessMetric(
            threshold=None, 
            model=eval_model,
            include_reason=True,
        ),
        ToolCorrectnessMetric(
            threshold=0.9, 
            model=eval_model,
            include_reason=True,
        ),
        GEval(
            name="Answer Correctness",
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            evaluation_steps=[
                "Check that the actual output and expected output have the same "
                "logical conclusion about the user's request.",
            ],
            threshold=0.8,
            model=eval_model,
            verbose_mode=True,
        ),
    ]
    return trace_metrics, single_turn_metrics


def main():
    load_dotenv()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
    from agent import agent

    trace_metrics, single_turn_metrics = build_metrics()
    cache_config = CacheConfig(use_cache=False, write_cache=False)
    display_config = DisplayConfig(inspect_after_run=False)
    test_cases = []

    for golden in dataset.evals_iterator(
        metrics=trace_metrics,
        cache_config=cache_config,
        display_config=display_config,
    ):
        response = agent.invoke(
            {"messages": [{"role": "user", "content": golden.input}]},
            config={
                "configurable": {"thread_id": str(uuid4())},
                "callbacks": [CallbackHandler()],
            },
        )

        messages = response["messages"]
        tools_called = []
        for message in messages:
            for tool_call in getattr(message, "tool_calls", []) or []:
                tools_called.append(
                    ToolCall(
                        name=tool_call["name"],
                        input_parameters=tool_call["args"],
                    )
                )

        final_output = next(
            (
                str(message.content)
                for message in reversed(messages)
                if message.type == "ai" and not message.tool_calls
            ),
            None,
        )
        if final_output is None:
            raise RuntimeError(
                f"Agent returned no final assistant message for case "
                f"{golden.name or golden.input!r}"
            )

        test_cases.append(
            LLMTestCase(
                input=golden.input,
                actual_output=final_output,
                expected_output=golden.expected_output,
                tools_called=tools_called,
                expected_tools=golden.expected_tools,
            )
        )

    evaluate(
        test_cases=test_cases,
        metrics=single_turn_metrics,
        cache_config=cache_config,
        display_config=display_config,
    )
    print(f"\nCompleted all 7 metrics for {len(test_cases)} test cases.")


if __name__ == "__main__":
    main()