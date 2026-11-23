
import re
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.messages import HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from uuid import uuid4

from data import users_data
from tools import calculate_right_refund, get_todays_date
from tools import issue_refund_ticket, get_user_purchase_history
from objects import Answer
from prompts import agent_system_prompt

ALL_ITEMS_PATTERN = re.compile(
    r"\b(?:all(?:\s+(?:of\s+)?(?:them|these|those|the(?:\s+listed)?\s+(?:items|purchases)))?"
    r"|both(?:\s+of\s+(?:them|these|those))?"
    r"|everything|every(?:\s+one|thing| item(?:s)?)"
    r"|the whole (?:list|lot))\b"
)


def refers_to_all_items(text: str) -> bool:
    normalized = text.casefold().replace("’", "'")
    normalized = re.sub(r"\b'em\b", "them", normalized)
    normalized = re.sub(r"[^a-z0-9\s']", " ", normalized)
    normalized = " ".join(normalized.split())

    if re.search(r"\b(?:not all|all but|everything but|except|excluding|without|but not)\b", normalized):
        return False
    if re.search(r"\b(?:don't|do not|never|not)\b.*\b(?:all|both|everything|every|whole)\b", normalized):
        return False
    return ALL_ITEMS_PATTERN.search(normalized) is not None


def clarify_all_items_selection(text: str, username: str | None) -> str:
    if username is None or username not in users_data or not refers_to_all_items(text):
        return text

    item_names = ", ".join(users_data[username])
    return (
        f"{text}\n"
        f"Interpret this as selecting every listed purchase for {username}: "
        f"{item_names}."
    )


load_dotenv()

model = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)

agent = create_agent(
    model=model,
    system_prompt=agent_system_prompt,
    tools=[
        calculate_right_refund,
        get_user_purchase_history,
        get_todays_date,
        issue_refund_ticket
    ],
    checkpointer=InMemorySaver()
)

def run_conversation():
    config = {"configurable": {"thread_id": str(uuid4())}}
    current_customer = None
    
    text = "I would like to request a refund"
    print(text)
    question = HumanMessage(content=text)

    conversation = True

    while conversation:
        response = agent.invoke(
            {"messages": [question]},
            config=config
        )

        messages = response["messages"]

        for message in messages:
            for tool_call in getattr(message, "tool_calls", []):
                if tool_call.get("name") == "get_user_purchase_history":
                    username = tool_call.get("args", {}).get("user")
                    current_customer = username if username in users_data else None

        final_message = next(
            (
                msg.content for msg in reversed(messages)
                if msg.type == "ai" and not msg.tool_calls
            ),
            ""
        )

        ticket_issued = any(
            getattr(msg, "name", None) == "issue_refund_ticket"
            and "successfully" in str(msg.content).lower()
            for msg in messages
        )

        structured_response = Answer(
            answer=str(final_message),
            conversation=not ticket_issued
        )

        print(structured_response.answer)

        conversation = structured_response.conversation

        if conversation:
            user_input = input("reply: \n")
            user_input = clarify_all_items_selection(user_input, current_customer)
            question = HumanMessage(content=user_input)

    print("the task is done!")


if __name__ == "__main__":
    run_conversation()
