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

from deepeval.metrics import TaskCompletionMetric
from deepeval.integrations.langchain import CallbackHandler
from deepeval.evaluate.configs import AsyncConfig
from deepeval.metrics.utils import print_tools_called
from deepeval.test_case import LLMTestCase


SUCCESSFUL_TASK_DESCRIPTION = """
The agent is considered successful if it follows all applicable rules below.

1. USER IDENTIFICATION
- Before processing any refund request, the agent must identify the user.
- If a refund request does not include a username, the agent must warmly ask for it before looking up purchases.
- The agent must not claim that an account could not be found or imply that a lookup was attempted before receiving a username.
- The agent must not retrieve purchase history, calculate refund amounts, or issue refund tickets until the user has been identified.
- If the user only asks general questions or requests information unrelated to refunds, user identification is not required.

2. PURCHASE HISTORY VERIFICATION
- Once the username is provided, the agent must retrieve the user's purchase history.
- The agent must verify that the requested purchase was made within the last 30 days, relative to today's date.
- Purchases older than 30 days are not eligible for a refund.
- The agent must use the actual purchase date and today's date to determine eligibility. It must not assume or fabricate dates.
- If purchase information is unavailable or insufficient, the agent must request clarification or explain that eligibility cannot be verified. It must not issue a refund ticket based on assumptions.

3. REFUND SCOPE
- The agent must refund only the specific items explicitly requested by the user.
- It must not automatically include all items from an order unless the user explicitly requests a full-order refund.
- If the requested items are ambiguous, the agent must ask the user to clarify which items they want refunded.
- The refund amount must correspond only to the eligible requested items.
- The agent must not invent item prices, quantities, or refund amounts.

4. REFUND ELIGIBILITY AND TICKET ISSUANCE
- A refund ticket may only be issued if:
  a. The user has been successfully identified.
  b. The requested purchase is within the 30-day refund eligibility period.
  c. The requested items are clearly identified.
  d. The refund amount has been correctly calculated.
- If any eligibility condition is not met, the agent must not issue a refund ticket.
- If the purchase is outside the 30-day period, the agent must explain why the refund cannot be processed.
- The agent must not claim that a refund has been issued unless the refund ticket tool confirms successful execution.
- The agent must not issue duplicate refund tickets for the same request.

5. USER COMMUNICATION
- The agent does not need to disclose internal verification steps unless the result affects refund eligibility or the user asks for an explanation.
- Once all required information and checks are complete, the agent must communicate the outcome clearly.
- For identified users, the final refund outcome must be one of the following:
  a. "A refund was issued." This may only be stated after successful confirmation from the refund ticket tool.
  b. "The refund was not issued." The agent must provide the specific reason.
- If additional information is required, the agent must ask a clear and relevant follow-up question instead of prematurely approving or rejecting the refund.
- The agent must not misrepresent the status of a refund request.

6. NON-REFUND REQUESTS
- If the user asks about an unrelated topic or casual conversation, the agent should briefly and politely explain that it only handles refunds and purchase questions, then redirect the user to those topics. It must not continue the unrelated conversation or call tools.
- If the user explicitly says they do not want a refund and only asks what they purchased, the agent should list the purchases without mentioning refund status or eligibility.
- The agent must not issue, calculate, or initiate refund tickets for requests that do not explicitly concern a refund.
- Unrelated requests must not trigger any tools.

7. GENERAL SAFETY AND CONSISTENCY
- The agent must never fabricate user information, purchase history, dates, item details, eligibility decisions, or refund amounts.
- The agent must follow the available tool outputs as the source of truth.
- The agent must not bypass any eligibility requirement, even if the user insists.
- If a tool fails or returns incomplete information, the agent must communicate the limitation and avoid claiming that an action was completed.
- The agent must prioritize correctness and policy compliance over completing a refund request at all costs.
"""

class CompactTaskCompletionMetric(TaskCompletionMetric):
	def _get_prompt(self, method, *, template_class=None, **kwargs):
		return super()._get_prompt(
			method,
			template_class=template_class or "TaskCompletionMetric",
			**kwargs,
		)

	async def _a_extract_task_and_outcome(self, test_case: LLMTestCase):
		return self._extract_task_and_outcome(test_case)

	def _extract_task_and_outcome(self, test_case: LLMTestCase):
		task = self.task or test_case.input or "Complete the user's request."
		tools_called = print_tools_called(test_case.tools_called)
		outcome = (
			f"Final response: {test_case.actual_output or 'No final response recorded.'}\n"
			f"Tools called: {tools_called or 'None'}"
		)
		return task, outcome


def main():
	metrics = [
		CompactTaskCompletionMetric(
			threshold=0.8,
			model=eval_model,
			task=SUCCESSFUL_TASK_DESCRIPTION,
			include_reason=True,
		)
	]

	for golden in dataset.evals_iterator(
		metrics=metrics,
		async_config=AsyncConfig(max_concurrent=1, throttle_value=15),
	):
		agent.invoke(
			{"messages":[{"role": "user", "content": golden.input}]},
			config={"configurable": {"thread_id": str(uuid4())},
			"callbacks": [CallbackHandler()]}
		)


if __name__ == "__main__":
	main()