
from langchain.tools import tool
from data import users_data
from dotenv import load_dotenv
import logging
from objects import PurchaseItem
from datetime import date, datetime

load_dotenv()

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s | %(levelname)s | %(message)s "
)


def _assess_refund(user: str, items: list[PurchaseItem]) -> tuple[str, int]:
    if user not in users_data:
        return "There was no username found.", 0

    today = date.today()
    seen_items = set()
    details = []
    total_refund = 0

    for item in items:
        item_name = item.name.strip()
        if item_name in seen_items:
            continue
        seen_items.add(item_name)

        purchase = users_data[user].get(item_name)
        if purchase is None:
            details.append(f"{item_name}: not purchased by this customer.")
            continue

        purchase_date = datetime.strptime(purchase["date"], "%Y-%m-%d").date()
        if purchase_date > today:
            details.append(f"{item_name}: ineligible because the purchase date is in the future.")
        elif (today - purchase_date).days > 30:
            details.append(
                f"{item_name}: ineligible because it was purchased on {purchase_date}, "
                "more than 30 days ago."
            )
        else:
            price = purchase["price"]
            total_refund += price
            details.append(f"{item_name}: eligible (Rp {price:,}).")

    if not details:
        details.append("No items were selected.")
    details.append(f"Eligible refund total: Rp {total_refund:,}.")
    return "\n".join(details), total_refund


@tool
def get_user_purchase_history(user: str) -> dict:
    """This tool takes the user username and returns a dict of the user's purchase history,
    if the user exists"""
    logging.info(f"Using get_user_purchase_history tool on user: {user}")
    if users_data.get(user):
        return users_data[user]
    return {"status": "there was no username found"}


@tool
def calculate_right_refund(user: str, items: list[PurchaseItem]) -> str:
    """Checks each selected purchase for refund eligibility and returns the eligible total."""
    logging.info(f"Using calculate_right_refund tool to get the user's: {user} refund")
    assessment, _ = _assess_refund(user, items)
    return assessment


@tool
def issue_refund_ticket(user: str, items: list[PurchaseItem]) -> str:
    """Issues a refund ticket for the eligible selected items and calculates its amount."""
    logging.info(f"Using issue_refund_ticket for user: {user}")
    assessment, refund_amount = _assess_refund(user, items)
    if refund_amount == 0:
        return f"No refund ticket was issued.\n{assessment}"

    today = date.today()
    return (
        f"A refund ticket has been issued successfully with the amount of Rp {refund_amount:,}\n"
        f"{today}\n{assessment}"
    )


@tool
def get_todays_date() -> str:
    """This tool will return today's date"""
    logging.info("Using the date tool")
    return str(date.today())


# print(get_user_purchase_history.invoke({"user": "customer_001"}))

# print(calculate_right_refund.invoke({
#     "user": "customer_001",
#     "items": [
#         {"name": "esp32_devkit"},
#         {"name": "dht22_temperature_sensor"}
#     ]
# }))

# print(get_todays_date.invoke("customer_001"))

# print(issue_refund_ticket.invoke({
#     "user": "customer_001",
#     "items": [
#         {"name": "esp32_devkit"},
#         {"name": "dht22_temperature_sensor"}
#     ]
# }))
