import ast
import json
import logging
import math
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / ".webapp-data"
HISTORY_FILE = DATA_DIR / "evaluation-runs.json"
DEEPEVAL_RUN_FILES = (
    ROOT / ".deepeval" / ".latest_test_run.json",
    ROOT / ".deepeval" / ".latest_run_full.json",
)
MAX_REQUEST_BYTES = 1_000_000
MAX_MESSAGE_LENGTH = 5_000
MAX_RUN_HISTORY = 20
EVALUATION_TIMEOUT_SECONDS = 3_600

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "agent"))

from agent import agent
from data import users_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("refund_web")

_history_lock = threading.Lock()
_job_lock = threading.Lock()
_jobs = {}


def _message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _final_assistant_message(messages):
    for message in reversed(messages):
        if (
            getattr(message, "type", None) == "ai"
            and not getattr(message, "tool_calls", [])
        ):
            content = _message_text(getattr(message, "content", None))
            if content:
                return content
    return None


def _purchase_items_for_turn(messages):
    username = None
    for message in messages:
        for call in getattr(message, "tool_calls", []) or []:
            if call.get("name") == "get_user_purchase_history":
                username = (call.get("args") or {}).get("user")

    purchases = users_data.get(username) if isinstance(username, str) else None
    if not isinstance(purchases, dict):
        return []

    return [
        {
            "name": item_name,
            "price": details["price"],
            "date": details["date"],
        }
        for item_name, details in purchases.items()
        if isinstance(details, dict)
        and isinstance(details.get("price"), (int, float))
        and isinstance(details.get("date"), str)
    ]


def _tool_events(messages):
    labels = {
        "get_user_purchase_history": "Checked purchase history",
        "issue_refund_ticket": "Processed refund request",
    }
    events = []
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        tool_name = getattr(message, "name", None)
        if not isinstance(tool_name, str):
            continue

        result = _message_text(getattr(message, "content", None))
        label = labels.get(tool_name, "Used support tool")
        if (
            tool_name == "issue_refund_ticket"
            and "ticket has been issued successfully" in result.casefold()
        ):
            label = "Refund ticket issued"
        events.append({"name": tool_name, "label": label})
    return events


def _parse_assistant_text(value):
    if not isinstance(value, dict):
        return None
    messages = value.get("messages")
    if not isinstance(messages, list):
        return None

    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") not in {"assistant", "ai"}:
            continue

        content = message.get("content")
        if isinstance(content, str) and content:
            return content
        parts = message.get("parts")
        if isinstance(parts, list):
            text = [
                part.get("content") or part.get("text")
                for part in parts
                if isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("content") or part.get("text"), str)
            ]
            if text:
                return "\n".join(text)
    return None


def _case_output(case):
    output = case.get("actualOutput")
    if isinstance(output, dict):
        extracted = _parse_assistant_text(output)
        if extracted:
            return extracted
    elif isinstance(output, str):
        try:
            parsed = ast.literal_eval(output)
        except (SyntaxError, ValueError):
            return output
        extracted = _parse_assistant_text(parsed)
        if extracted:
            return extracted
        return output

    trace = case.get("trace") or {}
    for span in reversed(trace.get("agentSpans") or []):
        extracted = _parse_assistant_text(span.get("output"))
        if extracted:
            return extracted
    return None


def _case_tools(case):
    tools = case.get("toolsCalled") or []
    trace = case.get("trace") or {}
    trace_tools = sorted(
        trace.get("toolSpans") or [],
        key=lambda tool: tool.get("startTime") or "",
    )
    if trace_tools:
        recorded_by_name = {}
        for tool in tools:
            if isinstance(tool, dict):
                recorded_by_name.setdefault(tool.get("name"), []).append(tool)
        ordered_tools = []
        for trace_tool in trace_tools:
            name = trace_tool.get("name")
            recorded = recorded_by_name.get(name, [])
            ordered_tools.append(recorded.pop(0) if recorded else trace_tool)
        ordered_tools.extend(
            tool for recorded in recorded_by_name.values() for tool in recorded
        )
        tools = ordered_tools

    normalized = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not isinstance(name, str):
            continue
        arguments = tool.get("inputParameters")
        if arguments is None:
            arguments = tool.get("input_parameters")
        if arguments is None:
            arguments = tool.get("input")
        normalized.append({"name": name, "arguments": arguments})
    return normalized


def _metric_result(metric):
    score = metric.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        score = None
    elif not math.isfinite(score):
        score = None

    threshold = metric.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        threshold = None

    success = metric.get("success")
    if success is None and score is not None and threshold is not None:
        success = score >= threshold

    return {
        "name": metric.get("name") or metric.get("metric") or "Metric",
        "score": score,
        "threshold": threshold,
        "success": success,
        "reason": metric.get("reason"),
        "error": metric.get("error"),
    }


def _unwrap_run_file(path):
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected evaluation result format in {path.name}")
    data = payload.get("testRunData", payload)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected evaluation result format in {path.name}")
    return data


def _build_dashboard_run(payloads, run_id, created_at, source_signature=None):
    cases_by_key = {}
    for payload in payloads:
        for position, raw_case in enumerate(payload.get("testCases") or []):
            key = raw_case.get("name") or raw_case.get("input") or f"case-{position}"
            case = cases_by_key.setdefault(
                key,
                {
                    "name": key,
                    "input": raw_case.get("input") or "",
                    "actualOutput": None,
                    "toolsCalled": [],
                    "metrics": {},
                },
            )
            if raw_case.get("input"):
                case["input"] = raw_case["input"]
            output = _case_output(raw_case)
            if output:
                case["actualOutput"] = output
            tools = _case_tools(raw_case)
            if tools:
                case["toolsCalled"] = tools
            for metric in raw_case.get("metricsData") or []:
                result = _metric_result(metric)
                case["metrics"][result["name"]] = result

    cases = []
    all_metric_names = set()
    for case in cases_by_key.values():
        case["metrics"] = list(case["metrics"].values())
        all_metric_names.update(metric["name"] for metric in case["metrics"])
        case["success"] = bool(case["metrics"]) and all(
            metric["success"] is True for metric in case["metrics"]
        )
        cases.append(case)

    metric_summaries = []
    for name in sorted(all_metric_names):
        results = [
            metric
            for case in cases
            for metric in case["metrics"]
            if metric["name"] == name
        ]
        scores = [metric["score"] for metric in results if metric["score"] is not None]
        passed = sum(metric["success"] is True for metric in results)
        failed = sum(metric["success"] is False for metric in results)
        metric_summaries.append(
            {
                "name": name,
                "averageScore": sum(scores) / len(scores) if scores else None,
                "passRate": passed / (passed + failed) if passed + failed else None,
                "passed": passed,
                "failed": failed,
                "errors": sum(metric["error"] is not None for metric in results),
                "total": len(results),
            }
        )

    passed_cases = sum(case["success"] for case in cases)
    scores = [
        metric["score"]
        for case in cases
        for metric in case["metrics"]
        if metric["score"] is not None
    ]
    task_scores = [
        metric["score"]
        for case in cases
        for metric in case["metrics"]
        if "task completion" in metric["name"].casefold()
        and metric["score"] is not None
    ]
    return {
        "id": run_id,
        "createdAt": created_at,
        "sourceSignature": source_signature,
        "totalCases": len(cases),
        "passed": passed_cases,
        "failed": len(cases) - passed_cases,
        "passRate": passed_cases / len(cases) if cases else None,
        "averageScore": sum(scores) / len(scores) if scores else None,
        "taskCompletionAverage": (
            sum(task_scores) / len(task_scores) if task_scores else None
        ),
        "metrics": metric_summaries,
        "cases": cases,
    }


def _latest_deepeval_run(changed_since=None):
    payloads = []
    signatures = []
    timestamps = []
    for path in DEEPEVAL_RUN_FILES:
        if not path.exists():
            continue
        stat = path.stat()
        signature = f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}"
        if changed_since is not None and changed_since.get(path) == (
            stat.st_mtime_ns,
            stat.st_size,
        ):
            continue
        payload = _unwrap_run_file(path)
        if payload is not None:
            payloads.append(payload)
            signatures.append(signature)
            timestamps.append(stat.st_mtime)

    if not payloads:
        return None
    created_at = datetime.fromtimestamp(
        max(timestamps), timezone.utc
    ).astimezone().isoformat(timespec="minutes")
    return _build_dashboard_run(
        payloads,
        run_id=f"run-{uuid4().hex[:10]}",
        created_at=created_at,
        source_signature="|".join(signatures),
    )


def _write_history(history):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = HISTORY_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(history, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(HISTORY_FILE)


def _load_history():
    with _history_lock:
        if HISTORY_FILE.exists():
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                raise ValueError("Evaluation history must be a JSON list.")
            return history

        latest = _latest_deepeval_run()
        history = [latest] if latest else []
        if history:
            _write_history(history)
        return history


def _append_run(run):
    with _history_lock:
        if HISTORY_FILE.exists():
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                raise ValueError("Evaluation history must be a JSON list.")
        else:
            history = []
        history.insert(0, run)
        _write_history(history[:MAX_RUN_HISTORY])


def _active_job():
    with _job_lock:
        active = next(
            (
                job
                for job in reversed(list(_jobs.values()))
                if job["status"] in {"queued", "running"}
            ),
            None,
        )
        if active is None and _jobs:
            active = next(reversed(_jobs.values()))
        return dict(active) if active else None


def _run_evaluation(job_id):
    with _job_lock:
        _jobs[job_id]["status"] = "running"

    before = {}
    for path in DEEPEVAL_RUN_FILES:
        if path.exists():
            stat = path.stat()
            before[path] = (stat.st_mtime_ns, stat.st_size)
        else:
            before[path] = None

    try:
        result = subprocess.run(
            [sys.executable, "-u", str(ROOT / "evaluations" / "all_evaluation.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=EVALUATION_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                logger.error("Evaluation failed: %s", detail[-4_000:])
            raise RuntimeError(
                f"Evaluation exited with status {result.returncode}. "
                "See the web server terminal for details."
            )

        run = _latest_deepeval_run(changed_since=before)
        if run is None:
            raise RuntimeError("Evaluation completed but produced no new result files.")
        run["id"] = f"run-{uuid4().hex[:10]}"
        run["createdAt"] = datetime.now().astimezone().isoformat(timespec="minutes")
        _append_run(run)
        with _job_lock:
            _jobs[job_id].update(
                status="completed",
                finishedAt=datetime.now().astimezone().isoformat(timespec="seconds"),
                runId=run["id"],
            )
    except subprocess.TimeoutExpired:
        with _job_lock:
            _jobs[job_id].update(
                status="failed",
                error="Evaluation timed out. Check the server terminal.",
                finishedAt=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
    except Exception as error:
        logger.exception("Developer evaluation job failed")
        with _job_lock:
            _jobs[job_id].update(
                status="failed",
                error=str(error),
                finishedAt=datetime.now().astimezone().isoformat(timespec="seconds"),
            )


def _start_evaluation():
    with _job_lock:
        if any(job["status"] in {"queued", "running"} for job in _jobs.values()):
            return None
        job_id = f"job-{uuid4().hex[:10]}"
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "startedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "finishedAt": None,
            "runId": None,
            "error": None,
        }
    threading.Thread(
        target=_run_evaluation,
        args=(job_id,),
        daemon=True,
        name=f"evaluation-{job_id}",
    ).start()
    return dict(_jobs[job_id])


class RefundWebHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        content = json.dumps(
            payload, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_file(self, path, content_type):
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length header.") from error
        if length <= 0:
            raise ValueError("Request body must be JSON.")
        if length > MAX_REQUEST_BYTES:
            raise OverflowError("Request body is too large.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request body must contain valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")
        return payload

    def do_GET(self):
        path = urlsplit(self.path).path
        pages = {
            "/": ("customer.html", "text/html; charset=utf-8"),
            "/developer": ("developer.html", "text/html; charset=utf-8"),
            "/developer/": ("developer.html", "text/html; charset=utf-8"),
        }
        assets = {
            "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/assets/customer.js": ("customer.js", "text/javascript; charset=utf-8"),
            "/assets/developer.js": ("developer.js", "text/javascript; charset=utf-8"),
        }
        if path in pages:
            filename, content_type = pages[path]
            self._send_file(WEB_ROOT / "static" / filename, content_type)
            return
        if path in assets:
            filename, content_type = assets[path]
            self._send_file(WEB_ROOT / "static" / filename, content_type)
            return
        if path == "/api/evaluations":
            try:
                self._send_json(200, {"runs": _load_history(), "job": _active_job()})
            except (OSError, ValueError, json.JSONDecodeError) as error:
                logger.exception("Could not load evaluation history")
                self._send_json(500, {"error": str(error)})
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            payload = self._read_json()
        except OverflowError as error:
            self._send_json(413, {"error": str(error)})
            return
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return

        if path == "/api/chat":
            self._handle_chat(payload)
        elif path == "/api/evaluations/run":
            job = _start_evaluation()
            if job is None:
                self._send_json(409, {"error": "An evaluation is already running."})
            else:
                self._send_json(202, {"job": job})
        else:
            self._send_json(404, {"error": "Not found."})

    def _handle_chat(self, payload):
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            self._send_json(400, {"error": "Enter a message to continue."})
            return
        if len(message) > MAX_MESSAGE_LENGTH:
            self._send_json(413, {"error": "Message is too long."})
            return

        raw_thread_id = payload.get("threadId")
        try:
            thread_id = str(UUID(raw_thread_id)) if raw_thread_id else str(uuid4())
        except (ValueError, TypeError, AttributeError):
            self._send_json(400, {"error": "Invalid chat session identifier."})
            return

        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": message.strip()}]},
                config={"configurable": {"thread_id": thread_id}},
            )
            messages = response.get("messages")
            if not isinstance(messages, list):
                raise RuntimeError("The agent response did not contain messages.")
            user_positions = [
                index
                for index, item in enumerate(messages)
                if getattr(item, "type", None) in {"human", "user"}
            ]
            if not user_positions:
                raise RuntimeError("The agent response did not contain the new user turn.")
            turn_messages = messages[user_positions[-1] + 1 :]
            assistant_message = _final_assistant_message(turn_messages)
            if assistant_message is None:
                raise RuntimeError("The agent did not return a final assistant message.")
            self._send_json(
                200,
                {
                    "threadId": thread_id,
                    "message": assistant_message,
                    "events": _tool_events(turn_messages),
                    "purchases": _purchase_items_for_turn(turn_messages),
                },
            )
        except Exception:
            logger.exception("Refund agent request failed")
            self._send_json(
                502,
                {"error": "The refund assistant could not complete that request. Please try again."},
            )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the local refund-agent web app.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), RefundWebHandler)
    server.daemon_threads = True
    logger.info("Refund web app listening on http://127.0.0.1:%s", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping refund web app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
