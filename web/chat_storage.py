import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".webapp-data"
DATABASE_FILE = DATA_DIR / "refund-chats.sqlite3"


@contextmanager
def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _title(username, updated_at):
    date = datetime.fromisoformat(updated_at).date().isoformat()
    return f"{username or 'Unknown user'} · {date}"


def initialize_database():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                username TEXT,
                agent_messages TEXT NOT NULL DEFAULT '[]',
                display_messages TEXT NOT NULL DEFAULT '[]',
                evaluation_json TEXT,
                evaluation_status TEXT,
                evaluation_error TEXT
            )
            """
        )
        connection.execute(
            """
            UPDATE chats
            SET evaluation_status = 'failed',
                evaluation_error = 'Evaluation was interrupted when the server stopped.'
            WHERE evaluation_status IN ('queued', 'running')
            """
        )


def create_chat():
    chat_id = str(uuid4())
    now = _now()
    with _connect() as connection:
        connection.execute(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (?, ?, ?)",
            (chat_id, now, now),
        )
    return get_chat(chat_id)


def _chat_from_row(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "username": row["username"],
        "title": _title(row["username"], row["updated_at"]),
        "agentMessages": json.loads(row["agent_messages"]),
        "messages": json.loads(row["display_messages"]),
        "evaluation": (
            json.loads(row["evaluation_json"])
            if row["evaluation_json"] is not None
            else None
        ),
        "evaluationStatus": row["evaluation_status"],
        "evaluationError": row["evaluation_error"],
    }


def get_chat(chat_id):
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
    return _chat_from_row(row)


def list_chats():
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, updated_at, username, evaluation_status
            FROM chats
            WHERE display_messages != '[]'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "updatedAt": row["updated_at"],
            "username": row["username"],
            "title": _title(row["username"], row["updated_at"]),
            "evaluationStatus": row["evaluation_status"],
        }
        for row in rows
    ]


def append_turn(chat_id, agent_messages, display_messages, username, refunded_items=()):
    now = _now()
    with _connect() as connection:
        row = connection.execute(
            "SELECT display_messages, username FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Chat not found.")

        messages = json.loads(row["display_messages"])
        refunded_items = set(refunded_items)
        if refunded_items:
            for message in messages:
                for purchase in message.get("purchases", []):
                    if purchase.get("name") in refunded_items:
                        purchase["refundIssued"] = True
        messages.extend(display_messages)
        connection.execute(
            """
            UPDATE chats
            SET updated_at = ?,
                username = ?,
                agent_messages = ?,
                display_messages = ?,
                evaluation_json = NULL,
                evaluation_status = NULL,
                evaluation_error = NULL
            WHERE id = ?
            """,
            (
                now,
                username or row["username"],
                _json_dump(agent_messages),
                _json_dump(messages),
                chat_id,
            ),
        )
    return get_chat(chat_id)


def set_evaluation_status(chat_id, status, error=None):
    with _connect() as connection:
        result = connection.execute(
            """
            UPDATE chats
            SET evaluation_status = ?,
                evaluation_error = ?,
                evaluation_json = NULL
            WHERE id = ?
            """,
            (status, error, chat_id),
        )
        if result.rowcount == 0:
            raise LookupError("Chat not found.")


def save_evaluation(chat_id, evaluation):
    with _connect() as connection:
        result = connection.execute(
            """
            UPDATE chats
            SET evaluation_json = ?,
                evaluation_status = 'completed',
                evaluation_error = NULL
            WHERE id = ?
            """,
            (_json_dump(evaluation), chat_id),
        )
        if result.rowcount == 0:
            raise LookupError("Chat not found.")


def public_chat(chat):
    if chat is None:
        return None
    return {
        "id": chat["id"],
        "createdAt": chat["createdAt"],
        "updatedAt": chat["updatedAt"],
        "username": chat["username"],
        "title": chat["title"],
        "messages": chat["messages"],
        "evaluation": chat["evaluation"],
        "evaluationStatus": chat["evaluationStatus"],
        "evaluationError": chat["evaluationError"],
    }
