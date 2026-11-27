import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict

from web.chat_evaluation import _expected_tool_names, build_conversation_test_case


class ExpectedToolInferenceTests(unittest.TestCase):
    def test_purchase_question_expects_history_lookup_only(self):
        messages = [{"role": "user", "text": "What have I purchased?"}]

        self.assertEqual(
            _expected_tool_names(messages, "customer_001"),
            ["get_user_purchase_history"],
        )

    def test_requested_purchase_expects_refund_ticket(self):
        messages = [
            {
                "role": "user",
                "text": "Please refund my esp32_devkit, customer_001.",
            }
        ]

        self.assertEqual(
            _expected_tool_names(messages, "customer_001"),
            ["get_user_purchase_history", "issue_refund_ticket"],
        )

    def test_unknown_item_does_not_expect_refund_ticket(self):
        messages = [
            {
                "role": "user",
                "text": "Please refund an item that I do not own.",
            }
        ]

        self.assertEqual(
            _expected_tool_names(messages, "customer_001"),
            ["get_user_purchase_history"],
        )

    def test_missing_username_does_not_expect_tools(self):
        messages = [{"role": "user", "text": "I want a refund."}]

        self.assertEqual(_expected_tool_names(messages, None), [])


class ConversationTestCaseTests(unittest.TestCase):
    def test_case_contains_complete_transcript_and_observed_tool_result(self):
        messages = [
            HumanMessage(content="Please refund my esp32_devkit, customer_001."),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_user_purchase_history",
                        "args": {"user": "customer_001"},
                        "id": "lookup",
                    },
                    {
                        "name": "issue_refund_ticket",
                        "args": {
                            "user": "customer_001",
                            "items": [{"name": "esp32_devkit"}],
                        },
                        "id": "refund",
                    },
                ],
            ),
            ToolMessage(
                content="A refund ticket was issued.",
                tool_call_id="refund",
                name="issue_refund_ticket",
            ),
            AIMessage(content="Your refund ticket has been issued."),
        ]
        chat = {
            "id": "chat-test",
            "username": "customer_001",
            "agentMessages": messages_to_dict(messages),
            "messages": [
                {
                    "role": "user",
                    "text": "Please refund my esp32_devkit, customer_001.",
                },
                {
                    "role": "assistant",
                    "text": "Your refund ticket has been issued.",
                },
            ],
        }

        test_case = build_conversation_test_case(chat)

        self.assertEqual(
            [tool.name for tool in test_case.expected_tools],
            ["get_user_purchase_history", "issue_refund_ticket"],
        )
        self.assertIn("A refund ticket was issued.", test_case.input)
        self.assertIn("Your refund ticket has been issued.", test_case.actual_output)
        self.assertEqual(
            test_case._trace_dict["children"][1]["output"],
            "A refund ticket was issued.",
        )


if __name__ == "__main__":
    unittest.main()
