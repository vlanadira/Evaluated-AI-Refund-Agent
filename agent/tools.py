
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

_ITEM_DISPLAY_NAMES = {
    "esp32_devkit": "ESP32 Dev Kit",
    "dht22_temperature_sensor": "DHT22 temperature sensor",
    "arduino_uno_r3": "Arduino Uno R3",
    "ultrasonic_sensor_hc_sr04": "HC-SR04 ultrasonic sensor",
    "relay_module_4_channel": "4-channel relay module",
    "raspberry_pi_4": "Raspberry Pi 4",
    "soil_moisture_sensor": "Soil moisture sensor",
    "oled_display_0_96": "0.96-inch OLED display",
    "ir_obstacle_sensor": "IR obstacle sensor",
    "rfid_reader_rc522": "RC522 RFID reader",
    "rfid_card_tag": "RFID card tag",
    "nodemcu_esp8266": "NodeMCU ESP8266",
    "sim800l_gsm_module": "SIM800L GSM module",
    "micro_sd_card_32gb": "32 GB microSD card",
    "pir_motion_sensor": "PIR motion sensor",
    "smart_energy_meter_pzem004t": "PZEM-004T smart energy meter",
    "current_transformer_sensor": "Current transformer sensor",
    "bme280_environmental_sensor": "BME280 environmental sensor",
    "rain_sensor_module": "Rain sensor module",
    "water_flow_sensor": "Water flow sensor",
}


def display_item_name(item_name: str) -> str:
    if item_name in _ITEM_DISPLAY_NAMES:
        return _ITEM_DISPLAY_NAMES[item_name]
    return " ".join(part.capitalize() for part in item_name.split("_"))


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
        display_name = display_item_name(item_name)
        if purchase is None:
            details.append(f"{display_name}: not purchased by this customer.")
            continue

        purchase_date = datetime.strptime(purchase["date"], "%Y-%m-%d").date()
        if purchase_date > today:
            details.append(
                f"{display_name}: ineligible because the purchase date is in the future."
            )
        elif (today - purchase_date).days > 30:
            details.append(
                f"{display_name}: ineligible because it was purchased on {purchase_date}, "
                "more than 30 days ago."
            )
        else:
            price = purchase["price"]
            total_refund += price
            details.append(f"{display_name}: eligible (Rp {price:,}).")

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
    """Checks selected items' eligibility and issues a ticket only for eligible items."""
    logging.info(f"Checking eligibility and issuing refund ticket for user: {user}")
    assessment, refund_amount = _assess_refund(user, items)
    if refund_amount == 0:
        return f"No refund ticket was issued.\n{assessment}"

    today = date.today()
    return (
        f"A refund ticket has been issued successfully with the amount of Rp {refund_amount:,}\n"
        f"{today}\n{assessment}"
    )


# print(get_user_purchase_history.invoke({"user": "customer_001"}))

# print(calculate_right_refund.invoke({
#     "user": "customer_001",
#     "items": [
#         {"name": "esp32_devkit"},
#         {"name": "dht22_temperature_sensor"}
#     ]
# }))

# print(issue_refund_ticket.invoke({
#     "user": "customer_001",
#     "items": [
#         {"name": "esp32_devkit"},
#         {"name": "dht22_temperature_sensor"}
#     ]
# }))
