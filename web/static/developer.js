const runSelect = document.querySelector("#run-select");
const runButton = document.querySelector("#run-evaluation");
const runSubtitle = document.querySelector("#run-subtitle");
const jobBanner = document.querySelector("#job-banner");
const metricsTableBody = document.querySelector("#metrics-table-body");
const caseList = document.querySelector("#case-list");
const caseDetail = document.querySelector("#case-detail");

let runs = [];
let selectedRunId = null;
let currentJob = null;
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
  if (!value) return "Saved run";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
}

function selectedRun() {
  return runs.find((run) => run.id === selectedRunId) || runs[0] || null;
}

function renderRunOptions() {
  runSelect.replaceChildren();
  if (runs.length === 0) {
    runSelect.add(new Option("No saved runs", ""));
    runSelect.disabled = true;
    return;
  }

  runSelect.disabled = false;
  for (const run of runs) {
    runSelect.add(new Option(formatDate(run.createdAt), run.id));
  }
  if (!runs.some((run) => run.id === selectedRunId)) {
    selectedRunId = runs[0].id;
  }
  runSelect.value = selectedRunId;
}

function renderSummary(run) {
  if (!run) {
    setText("#stat-pass-rate", "--");
    setText("#stat-pass-detail", "No run selected");
    setText("#stat-average-label", "Task Completion (avg)");
    setText("#stat-average", "--");
    document.querySelector("#stat-average-bar").style.width = "0";
    setText("#stat-cases", "--");
    setText("#stat-metrics-detail", "-- metrics");
    setText("#stat-failures", "--");
    setText("#stat-failure-detail", "Nothing to review");
    return;
  }

  setText("#stat-pass-rate", formatPercent(run.passRate));
  setText("#stat-pass-detail", `${run.passed} passed · ${run.failed} failed`);

  const taskAverage = run.taskCompletionAverage;
  const average = taskAverage ?? run.averageScore;
  setText(
    "#stat-average-label",
    taskAverage === null || taskAverage === undefined
      ? "Average score"
      : "Task Completion (avg)",
  );
  setText("#stat-average", formatScore(average));
  document.querySelector("#stat-average-bar").style.width =
    typeof average === "number" ? `${Math.max(0, Math.min(1, average)) * 100}%` : "0";
  setText("#stat-cases", String(run.totalCases));
  setText("#stat-metrics-detail", `${run.metrics.length} metric${run.metrics.length === 1 ? "" : "s"}`);
  setText("#stat-failures", String(run.failed));
  setText(
    "#stat-failure-detail",
    run.failed === 0 ? "Nothing to review" : `${run.failed} case${run.failed === 1 ? "" : "s"} need review`,
  );
  runSubtitle.textContent = `${formatDate(run.createdAt)} · ${run.totalCases} test cases · ${run.metrics.length} metrics`;
}

function renderMetricTable(run) {
  metricsTableBody.replaceChildren();
  if (!run || run.metrics.length === 0) {
    const row = document.createElement("tr");
    row.append(createElement("td", "empty-cell", "No metric results in this run."));
    row.firstChild.colSpan = 5;
    metricsTableBody.append(row);
    return;
  }

  for (const metric of run.metrics) {
    const row = document.createElement("tr");
    row.append(createElement("td", "metric-name-cell", metric.name));
    row.append(createElement("td", "", formatScore(metric.averageScore)));
    const passCell = document.createElement("td");
    const badge = createElement(
      "span",
      `metric-badge${metric.failed > 0 ? " fail" : ""}`,
      formatPercent(metric.passRate),
    );
    passCell.append(badge);
    row.append(passCell);
    row.append(createElement("td", "", `${metric.passed} / ${metric.failed}`));
    row.append(createElement("td", "", String(metric.total)));
    metricsTableBody.append(row);
  }
}

function renderCaseList(run) {
  caseList.replaceChildren();
  if (!run || run.cases.length === 0) {
    caseList.append(createElement("p", "empty-state", "No test cases in this run."));
    setText("#case-list-summary", "No cases");
    return;
  }

  const failures = run.cases.filter((testCase) => !testCase.success).length;
  setText(
    "#case-list-summary",
    failures === 0 ? "All passed" : `${failures} failed`,
  );
  for (const testCase of run.cases) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `case-list-button${testCase.name === selectedCaseName ? " selected" : ""}`;
    button.addEventListener("click", () => {
      selectedCaseName = testCase.name;
      renderCaseList(run);
      renderCaseDetail(testCase);
    });

    button.append(createElement("span", "case-list-name", testCase.name));
    button.append(
      createElement(
        "span",
        `case-list-status${testCase.success ? "" : " fail"}`,
        testCase.success ? "Passed" : "Review",
      ),
    );
    caseList.append(button);
  }
}

let selectedCaseName = null;

function renderCaseDetail(testCase) {
  if (!testCase) {
    caseDetail.replaceChildren(
      createElement(
        "div",
        "empty-state detail-empty",
        "Select a test case to inspect its input, tool calls, output, and metric reasons.",
      ),
    );
    return;
  }

  caseDetail.replaceChildren();
  const heading = createElement("div", "case-detail-title");
  heading.append(createElement("h2", "", testCase.name));
  heading.append(
    createElement(
      "span",
      `status-pill${testCase.success ? "" : " fail"}`,
      testCase.success ? "Passed" : "Review",
    ),
  );
  caseDetail.append(heading);

  addDetailSection(caseDetail, "Customer input", testCase.input || "No input recorded");

  const toolsSection = createElement("section", "detail-section");
  toolsSection.append(createElement("span", "detail-label", "Tools called"));
  const toolsList = createElement("div", "tool-chip-list");
  if (testCase.toolsCalled.length === 0) {
    toolsList.append(createElement("span", "detail-content", "No tool calls"));
  } else {
    for (const tool of testCase.toolsCalled) {
      let label = tool.name;
      if (tool.arguments && Object.keys(tool.arguments).length > 0) {
        label += `  ${JSON.stringify(tool.arguments)}`;
      }
      toolsList.append(createElement("span", "tool-chip", label));
    }
  }
  toolsSection.append(toolsList);
  caseDetail.append(toolsSection);

  addDetailSection(
    caseDetail,
    "Agent output",
    testCase.actualOutput || "No assistant output recorded.",
  );

  const metricsSection = createElement("section", "detail-section");
  metricsSection.append(createElement("span", "detail-label", "Metric results"));
  const metricList = createElement("div", "metric-detail-list");
  if (testCase.metrics.length === 0) {
    metricList.append(createElement("div", "detail-content", "No metric details recorded."));
  } else {
    for (const metric of testCase.metrics) {
      const card = createElement("article", "metric-detail");
      const metricHeading = createElement("div", "metric-detail-heading");
      metricHeading.append(createElement("span", "", metric.name));
      const scoreText = metric.score === null ? "Error" : formatScore(metric.score);
      metricHeading.append(
        createElement(
          "span",
          `metric-score${metric.success === false ? " fail" : ""}`,
          scoreText,
        ),
      );
      card.append(metricHeading);
      if (metric.error) card.append(createElement("p", "metric-reason", metric.error));
      else if (metric.reason) card.append(createElement("p", "metric-reason", metric.reason));
      else card.append(createElement("p", "metric-reason", "No reason recorded."));
      metricList.append(card);
    }
  }
  metricsSection.append(metricList);
  caseDetail.append(metricsSection);
}

function addDetailSection(container, label, content) {
  const section = createElement("section", "detail-section");
  section.append(createElement("span", "detail-label", label));
  section.append(createElement("div", "detail-content", content));
  container.append(section);
}

function renderSelectedRun() {
  const run = selectedRun();
  renderSummary(run);
  renderMetricTable(run);
  renderCaseList(run);
  if (!run) {
    selectedCaseName = null;
    renderCaseDetail(null);
    return;
  }
  const testCase = run.cases.find((item) => item.name === selectedCaseName) || run.cases[0];
  selectedCaseName = testCase ? testCase.name : null;
  renderCaseList(run);
  renderCaseDetail(testCase);
}

function renderJob(job) {
  currentJob = job;
  if (!job) {
    jobBanner.hidden = true;
    runButton.disabled = false;
    return;
  }

  if (job.status === "running" || job.status === "queued") {
    jobBanner.hidden = false;
    jobBanner.classList.remove("error");
    jobBanner.textContent = "Evaluation is running. It may take several minutes while the agent and judge process each case.";
    runButton.disabled = true;
  } else if (job.status === "failed") {
    jobBanner.hidden = false;
    jobBanner.classList.add("error");
    jobBanner.textContent = job.error || "Evaluation failed. Check the server terminal for details.";
    runButton.disabled = false;
  } else {
    jobBanner.hidden = false;
    jobBanner.classList.remove("error");
    jobBanner.textContent = "Evaluation completed. Results have been saved.";
    runButton.disabled = false;
  }
}

async function loadEvaluations() {
  const response = await fetch("/api/evaluations", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not load evaluation results.");
  runs = Array.isArray(result.runs) ? result.runs : [];
  renderRunOptions();
  renderSelectedRun();
  renderJob(result.job);
}

async function pollEvaluation() {
  try {
    await loadEvaluations();
    if (currentJob && ["queued", "running"].includes(currentJob.status)) {
      pollTimer = window.setTimeout(pollEvaluation, 1800);
    } else if (currentJob && currentJob.status === "completed" && currentJob.runId) {
      selectedRunId = currentJob.runId;
      renderRunOptions();
      renderSelectedRun();
    }
  } catch (error) {
    jobBanner.hidden = false;
    jobBanner.classList.add("error");
    jobBanner.textContent = error.message || "Could not refresh evaluation status.";
  }
}

runSelect.addEventListener("change", () => {
  selectedRunId = runSelect.value;
  selectedCaseName = null;
  renderSelectedRun();
});

runButton.addEventListener("click", async () => {
  const confirmed = window.confirm(
    "Run all evaluation cases? This calls the configured agent and judge models and may use paid API credits.",
  );
  if (!confirmed) return;

  runButton.disabled = true;
  jobBanner.hidden = false;
  jobBanner.classList.remove("error");
  jobBanner.textContent = "Starting evaluation...";
  try {
    const response = await fetch("/api/evaluations/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start evaluation.");
    renderJob(result.job);
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(pollEvaluation, 1000);
  } catch (error) {
    jobBanner.classList.add("error");
    jobBanner.textContent = error.message || "Could not start evaluation.";
    runButton.disabled = false;
  }
});

loadEvaluations().catch((error) => {
  runSubtitle.textContent = error.message || "Could not load evaluation results.";
  jobBanner.hidden = false;
  jobBanner.classList.add("error");
  jobBanner.textContent = error.message || "Could not load evaluation results.";
});
