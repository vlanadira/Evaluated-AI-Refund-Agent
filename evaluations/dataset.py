
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.test_case import ToolCall

dataset = EvaluationDataset(
    goldens=[
        Golden(
            input="I am customer_001, I would like a refund for the esp32_devkit and dht22_temperature_sensor",
            expected_output="A refund ticket for 190.000 has been issued successfully.",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="calculate_right_refund"),
                ToolCall(name="issue_refund_ticket"),
                ToolCall(name="get_todays_date")
            ]
        ),
        Golden(
            input="I am customer_001, I would like a refund for the esp32_devkit",
            expected_output="A refund ticket for 125.000 has been issued successfully.",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="calculate_right_refund"),
                ToolCall(name="issue_refund_ticket"),
                ToolCall(name="get_todays_date")
            ]
        ),
        Golden(
            input="I am customer_001, I would like no refund, I just want to know what I purchased",
            expected_output="No refund tickets were issued, only a list of item(s) they bought",
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
                ToolCall(name="get_todays_date")
            ]
        ),
        Golden(
            input="I am customer_004, I would like a refund for the raspberry_pi_4 and oled_display_0_96",
            expected_output="A refund ticket for 1.150.000 has been issued successfully only for the raspberry_pi_4. The oled_display_0_96 is not eligible for a refund because it is outside 30 days refund policy",
            expected_tools=[
                ToolCall(name="get_user_purchase_history"),
                ToolCall(name="calculate_right_refund"),
                ToolCall(name="issue_refund_ticket"),
                ToolCall(name="get_todays_date")
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
