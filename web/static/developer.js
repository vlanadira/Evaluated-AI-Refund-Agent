const CHAT_SELECTION_KEY = "refund-agent-developer-chat";
const chatSelect = document.querySelector("#chat-select");
const refreshButton = document.querySelector("#refresh-chats");
const runButton = document.querySelector("#run-evaluation");
const chatSubtitle = document.querySelector("#chat-subtitle");
const jobBanner = document.querySelector("#job-banner");
const metricsTableBody = document.querySelector("#metrics-table-body");
const transcript = document.querySelector("#conversation-transcript");
const caseDetail = document.querySelector("#case-detail");

let chats = [];
let selectedChatId = sessionStorage.getItem(CHAT_SELECTION_KEY);
let selectedChat = null;
let pollTimer = null;

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function formatPercent(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)}%`
    : "--";
}

function formatScore(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(2)
    : "--";
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
}

function selectedChatOption() {
  return chats.find((chat) => chat.id === selectedChatId) || null;
}

function renderChatOptions() {
  chatSelect.replaceChildren();
  if (chats.length === 0) {
    chatSelect.add(new Option("No conversations yet", ""));
    chatSelect.disabled = true;
    selectedChatId = null;
    sessionStorage.removeItem(CHAT_SELECTION_KEY);
    return;
  }

  chatSelect.disabled = false;
  for (const chat of chats) {
    chatSelect.add(new Option(chat.title, chat.id));
  }
  if (!chats.some((chat) => chat.id === selectedChatId)) {
    selectedChatId = chats[0].id;
  }
  chatSelect.value = selectedChatId;
  sessionStorage.setItem(CHAT_SELECTION_KEY, selectedChatId);
}

function renderSummary(chat) {
  if (!chat) {
    setText("#case-list-summary", "Select a chat");
    setText("#stat-pass-rate", "--");
    setText("#stat-pass-detail", "No chat selected");
    setText("#stat-average", "--");
    document.querySelector("#stat-average-bar").style.width = "0";
    setText("#stat-cases", "--");
    setText("#stat-metrics-detail", "No chat selected");
    setText("#stat-failures", "--");
    setText("#stat-failure-detail", "Nothing to review");
    return;
  }

  const evaluation = chat.evaluation;
  setText(
    "#case-list-summary",
    `${chat.messages.length} message${chat.messages.length === 1 ? "" : "s"}`,
  );
  setText("#stat-cases", String(chat.messages.length));
  const userTurns = chat.messages.filter((message) => message.role === "user").length;
  setText(
    "#stat-metrics-detail",
    `${userTurns} customer message${userTurns === 1 ? "" : "s"}`,
  );
  if (!evaluation) {
    setText("#stat-pass-rate", "--");
    setText("#stat-pass-detail", "Not evaluated yet");
    setText("#stat-average", "--");
    document.querySelector("#stat-average-bar").style.width = "0";
    setText("#stat-failures", "--");
    setText("#stat-failure-detail", "Run an evaluation to see results");
    return;
  }

  setText("#stat-pass-rate", formatPercent(evaluation.passRate));
  setText(
    "#stat-pass-detail",
    `${evaluation.passed} passed · ${evaluation.failed} need review`,
  );
  setText("#stat-average", formatScore(evaluation.averageScore));
  document.querySelector("#stat-average-bar").style.width =
    typeof evaluation.averageScore === "number"
      ? `${Math.max(0, Math.min(1, evaluation.averageScore)) * 100}%`
      : "0";
  setText("#stat-failures", String(evaluation.failed));
  setText(
    "#stat-failure-detail",
    evaluation.failed === 0 ? "All scored metrics passed" : "Review metric explanations below",
  );
}

function renderMetrics(chat) {
  metricsTableBody.replaceChildren();
  const metrics = chat?.evaluation?.metrics || [];
  if (metrics.length === 0) {
    const row = document.createElement("tr");
    const cell = createElement(
      "td",
      "empty-cell",
      chat?.evaluationStatus === "failed"
        ? chat.evaluationError || "Evaluation failed."
        : "No evaluation results for this chat yet.",
    );
    cell.colSpan = 5;
    row.append(cell);
    metricsTableBody.append(row);
    return;
  }

  for (const metric of metrics) {
    const row = document.createElement("tr");
    row.append(createElement("td", "metric-name-cell", metric.name));
    row.append(createElement("td", "", formatScore(metric.score)));
    row.append(createElement("td", "", formatScore(metric.threshold)));
    const resultCell = document.createElement("td");
    const resultText = metric.error
      ? "Error"
      : metric.success
        ? "Passed"
        : "Review";
    resultCell.append(
      createElement(
        "span",
        `metric-badge${metric.success ? "" : " fail"}`,
        resultText,
      ),
    );
    row.append(resultCell);
    row.append(createElement("td", "metric-table-reason", metric.error || metric.reason || "No reason recorded."));
    metricsTableBody.append(row);
  }
}

function renderTranscript(chat) {
  transcript.replaceChildren();
  if (!chat || chat.messages.length === 0) {
    transcript.append(
      createElement("p", "empty-state", "This chat has no messages yet."),
    );
    return;
  }

  for (const message of chat.messages) {
    const entry = createElement(
      "article",
      `conversation-turn ${message.role === "user" ? "customer-turn" : "assistant-turn"}`,
    );
    entry.append(
      createElement(
        "span",
        "conversation-role",
        message.role === "user" ? "Customer" : "Refund assistant",
      ),
    );
    if (Array.isArray(message.events) && message.events.length > 0) {
      const events = createElement("div", "message-events");
      for (const event of message.events) {
        events.append(createElement("span", "event-pill", event.label));
      }
      entry.append(events);
    }
    entry.append(createElement("p", "conversation-text", message.text || ""));
    transcript.append(entry);
  }
}

function addDetailSection(container, label, content) {
  const section = createElement("section", "detail-section");
  section.append(createElement("span", "detail-label", label));
  section.append(createElement("div", "detail-content", content));
  container.append(section);
}

function renderDetails(chat) {
  if (!chat) {
    caseDetail.replaceChildren(
      createElement("div", "empty-state detail-empty", "Select a chat to inspect its tool calls and evaluation."),
    );
    return;
  }

  caseDetail.replaceChildren();
  const heading = createElement("div", "case-detail-title");
  heading.append(createElement("h2", "", chat.title));
  const statusText = chat.evaluationStatus || "Not evaluated";
  heading.append(
    createElement(
      "span",
      `status-pill${chat.evaluationStatus === "failed" ? " fail" : ""}`,
      statusText,
    ),
  );
  caseDetail.append(heading);
  addDetailSection(caseDetail, "Last activity", formatDate(chat.updatedAt));

  const toolsSection = createElement("section", "detail-section");
  toolsSection.append(createElement("span", "detail-label", "Tool calls"));
  const toolsList = createElement("div", "tool-chip-list");
  const tools = chat.evaluation?.toolsCalled || [];
  if (tools.length === 0) {
    toolsList.append(createElement("span", "detail-content", "No tool calls in this conversation."));
  } else {
    for (const tool of tools) {
      const label = tool.arguments && Object.keys(tool.arguments).length > 0
        ? `${tool.name}  ${JSON.stringify(tool.arguments)}`
        : tool.name;
      toolsList.append(createElement("span", "tool-chip", label));
    }
  }
  toolsSection.append(toolsList);
  caseDetail.append(toolsSection);

  if (chat.evaluation?.createdAt) {
    addDetailSection(caseDetail, "Evaluated", formatDate(chat.evaluation.createdAt));
  }
  if (!chat.evaluation && chat.evaluationError) {
    addDetailSection(caseDetail, "Evaluation error", chat.evaluationError);
  }
}

function renderChat(chat) {
  selectedChat = chat;
  renderSummary(chat);
  renderMetrics(chat);
  renderTranscript(chat);
  renderDetails(chat);

  if (!chat) {
    chatSubtitle.textContent = "No saved customer chats yet.";
    runButton.disabled = true;
    return;
  }
  chatSubtitle.textContent =
    `${chat.title} · Last activity ${formatDate(chat.updatedAt)} · ${chat.messages.length} messages`;
  const running = ["queued", "running"].includes(chat.evaluationStatus);
  runButton.disabled = running || !chat.messages.some((message) => message.role === "user");

  if (running) {
    jobBanner.hidden = false;
    jobBanner.classList.remove("error");
    jobBanner.textContent = "Evaluating the complete conversation with all seven metrics. This may take a few minutes.";
  } else if (chat.evaluationStatus === "failed") {
    jobBanner.hidden = false;
    jobBanner.classList.add("error");
    jobBanner.textContent = chat.evaluationError || "Evaluation failed.";
  } else if (chat.evaluationStatus === "completed") {
    jobBanner.hidden = false;
    jobBanner.classList.remove("error");
    jobBanner.textContent = "Evaluation completed. Results are saved with this chat.";
  } else {
    jobBanner.hidden = true;
  }
}

async function loadSelectedChat() {
  if (!selectedChatId) {
    renderChat(null);
    return null;
  }
  const response = await fetch(`/api/chats/${encodeURIComponent(selectedChatId)}`, {
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not load this chat.");
  renderChat(result.chat);
  return result.chat;
}

async function loadChats() {
  const response = await fetch("/api/chats", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not load customer chats.");
  chats = Array.isArray(result.chats) ? result.chats : [];
  renderChatOptions();
  return loadSelectedChat();
}

function showLoadError(error) {
  chatSubtitle.textContent = error.message || "Could not load customer chats.";
  jobBanner.hidden = false;
  jobBanner.classList.add("error");
  jobBanner.textContent = error.message || "Could not load customer chats.";
  runButton.disabled = true;
}

async function pollEvaluation() {
  try {
    const chat = await loadSelectedChat();
    if (chat && ["queued", "running"].includes(chat.evaluationStatus)) {
      pollTimer = window.setTimeout(pollEvaluation, 1800);
    } else {
      await loadChats();
    }
  } catch (error) {
    showLoadError(error);
  }
}

chatSelect.addEventListener("change", () => {
  selectedChatId = chatSelect.value;
  sessionStorage.setItem(CHAT_SELECTION_KEY, selectedChatId);
  window.clearTimeout(pollTimer);
  loadSelectedChat().catch(showLoadError);
});

refreshButton.addEventListener("click", () => {
  loadChats().catch(showLoadError);
});

runButton.addEventListener("click", async () => {
  if (!selectedChatId) return;
  const confirmed = window.confirm(
    "Evaluate this entire conversation with all seven metrics? The judge model may use paid API credits.",
  );
  if (!confirmed) return;

  runButton.disabled = true;
  jobBanner.hidden = false;
  jobBanner.classList.remove("error");
  jobBanner.textContent = "Starting chat evaluation...";
  try {
    const response = await fetch(
      `/api/chats/${encodeURIComponent(selectedChatId)}/evaluate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start chat evaluation.");
    await loadSelectedChat();
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(pollEvaluation, 1200);
  } catch (error) {
    jobBanner.hidden = false;
    jobBanner.classList.add("error");
    jobBanner.textContent = error.message || "Could not start chat evaluation.";
    runButton.disabled = false;
  }
});

loadChats().catch(showLoadError);
