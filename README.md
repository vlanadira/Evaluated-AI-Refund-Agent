# Evaluated-AI-Refund-Agent
A customer support AI agent that processes refund requests using tools, follows refund policies, and is evaluated using DeepEval to measure task completion, tool correctness, argument accuracy, and answer quality.

## Local web app

The web app provides a customer refund chat and a developer conversation-evaluation view. Create separate customer conversations with **New chat**; conversations and tool activity are stored locally in `.webapp-data/refund-chats.sqlite3`. In the developer view, select a conversation and evaluate it without replaying the agent.

Each selected chat is evaluated with seven metrics: Task Completion, Step Efficiency, Plan Quality, Plan Adherence, Argument Correctness, Tool Correctness, and Answer Correctness. Chats are titled with the identified username and last-activity date, or `Unknown user` until a username is identified.

The app uses Python's standard-library HTTP server, so no additional web framework is required.

Run it from the project root using the Python environment that has the agent and DeepEval dependencies installed:

```bash
python web/server.py
```

Then open `http://127.0.0.1:8000`. The customer chat is at `/`, and the developer view is at `/developer`. Evaluations call the configured judge model and may use paid API credits. Chat and evaluation data stay in the ignored `.webapp-data/` directory.

The server binds to localhost and has no authentication. Do not expose it to a network or deploy it publicly without adding authentication and protecting the evaluation endpoint.
