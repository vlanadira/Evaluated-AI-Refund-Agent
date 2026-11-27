
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.test_case import ToolCall

dataset = EvaluationDataset(
    goldens=[
        Golden(
            input="I would like to request a refund",
            expected_output="Warmly acknowledge the refund request and ask for the account username before looking up purchases. Do not say the account was not found or imply that a lookup was attempted.",
            expected_tools=[]
        ),
        Golden(
            input="Can we talk casually outside of this refund request?",
            expected_output="Politely explain that the assistant only handles refunds and purchase questions, then invite the user to ask about one of those topics. Do not continue casual conversation or call tools.",
            expected_tools=[]
        ),
        Golden(
            input="I am customer_001, I would like a refund for the esp32_devkit and dht22_temperature_sensor",
            expected_output="A refund ticket for 190.000 has been issued successfully.",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="issue_refund_ticket")
            ]
        ),
        Golden(
            input="I am customer_001, I would like a refund for the esp32_devkit",
            expected_output="A refund ticket for 125.000 has been issued successfully.",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="issue_refund_ticket")
            ]
        ),
        Golden(
            input="I am customer_001, I would like no refund, I just want to know what I purchased",
            expected_output="List the customer's purchased items only, without mentioning refund status or eligibility",
            expected_tools=[
                ToolCall(name="get_user_purchase_history")
            ]
        ),
        Golden(
            input="I am customer_999, I would like a refund for the esp32_devkit",
            expected_output="Tell the user that the username is not valid and ask for username again before giving the information of the refund",
            expected_tools=[
                ToolCall(name="get_user_purchase_history")
            ]
        ),
        Golden(
            input="I am customer_004, I would like a refund for the oled_display_0_96",
            expected_output="No refund given because it is outside of the 30 days guideline",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="issue_refund_ticket")
            ]
        ),
        Golden(
            input="I am customer_004, I would like a refund for the raspberry_pi_4 and oled_display_0_96",
            expected_output="A refund ticket for 1.150.000 has been issued successfully only for the raspberry_pi_4. The oled_display_0_96 is not eligible for a refund because it is outside 30 days refund policy",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="issue_refund_ticket")
            ]
        ),
        Golden(
            input="I am customer_004, I would like a refund for the esp32 c3",
            expected_output="No refund was given because you didn't purchase this item",
            expected_tools=[
                ToolCall(name="get_user_purchase_history")
            ]
        )
    ]
)
