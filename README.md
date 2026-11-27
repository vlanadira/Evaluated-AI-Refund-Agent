# Evaluated-AI-Refund-Agent
A customer support AI agent that processes refund requests using tools, follows refund policies, and is evaluated using DeepEval to measure task completion, tool correctness, argument accuracy, and answer quality.

## Local web app

The web app provides two views: a customer refund chat and a developer evaluation dashboard. It uses Python's standard-library HTTP server, so no additional web framework is required.

Run it from the project root using the Python environment that has the agent and DeepEval dependencies installed:

```bash
python web/server.py
```

Then open `http://127.0.0.1:8000`. The customer chat is at `/`, and the developer dashboard is at `/developer`. The dashboard can run `evaluations/all_evaluation.py`; evaluation runs call the configured agent and judge models and may use paid API credits. Dashboard history is stored locally in the ignored `.webapp-data/` directory.

The server binds to localhost and has no authentication. Do not expose it to a network or deploy it publicly without adding authentication and protecting the evaluation endpoint.
