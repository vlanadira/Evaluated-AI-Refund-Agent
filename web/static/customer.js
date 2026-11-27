const CHAT_KEY = "refund-agent-chat-id";
const messagesElement = document.querySelector("#chat-messages");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const sendButton = document.querySelector("#send-button");
const newChatButton = document.querySelector("#new-chat");

let chatId = sessionStorage.getItem(CHAT_KEY);
let messages = [];
let waiting = false;
let chatReady = false;
const welcomeMessage = {
  role: "assistant",
  text: "Hi! I’m your refund assistant. I can help review your purchases and refund requests.",
};

function formatPrice(value) {
  return `Rp ${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)}`;
}

function formatDate(value) {
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(value || "");
  if (!match) return value || "Purchase date unavailable";
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function appendPurchaseCards(container, purchases) {
  if (!Array.isArray(purchases) || purchases.length === 0) return;
  const cards = document.createElement("div");
  cards.className = "purchase-cards";

  for (const purchase of purchases) {
    const card = document.createElement("article");
    card.className = "purchase-card";

    const info = document.createElement("div");
    info.className = "purchase-info";
    const name = document.createElement("strong");
    name.className = "purchase-name";
    name.textContent = purchase.name;
    const date = document.createElement("span");
    date.className = "purchase-date";
    date.textContent = formatDate(purchase.date);
    info.append(name, date);

    const price = document.createElement("span");
    price.className = "purchase-price";
    price.textContent = formatPrice(purchase.price);

    const request = document.createElement("button");
    request.type = "button";
    request.className = "outline-button";
    request.textContent = "Request refund";
    request.addEventListener("click", () => {
      sendMessage(`I would like a refund for the ${purchase.name}`);
    });

    card.append(info, price, request);
    cards.append(card);
  }
  container.append(cards);
}

function renderMessage(entry) {
  const row = document.createElement("div");
  row.className = `message-row ${entry.role}`;

  if (entry.role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "assistant-avatar";
    avatar.textContent = "S";
    row.append(avatar);
  }

  const stack = document.createElement("div");
  stack.className = "message-stack";

  if (Array.isArray(entry.events) && entry.events.length > 0) {
    const events = document.createElement("div");
    events.className = "message-events";
    for (const event of entry.events) {
      const pill = document.createElement("span");
      pill.className = "event-pill";
      pill.textContent = event.label;
      events.append(pill);
    }
    stack.append(events);
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = entry.text || "";
  stack.append(bubble);
  appendPurchaseCards(stack, entry.purchases);
  row.append(stack);
  messagesElement.append(row);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function renderAllMessages() {
  messagesElement.replaceChildren();
  for (const message of messages.length > 0 ? messages : [welcomeMessage]) {
    renderMessage(message);
  }
}

function setWaiting(value) {
  waiting = value;
  sendButton.disabled = value || !chatReady;
  chatInput.disabled = value || !chatReady;

  const existing = document.querySelector("#assistant-typing");
  if (existing) existing.remove();
  if (!value) return;

  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = "assistant-typing";
  const avatar = document.createElement("span");
  avatar.className = "assistant-avatar";
  avatar.textContent = "S";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble typing-bubble";
  bubble.setAttribute("aria-label", "Assistant is responding");
  for (let index = 0; index < 3; index += 1) {
    bubble.append(document.createElement("i"));
  }
  row.append(avatar, bubble);
  messagesElement.append(row);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

async function sendMessage(text) {
  const cleanText = text.trim();
  if (!cleanText || waiting || !chatReady) return;

  messages.push({ role: "user", text: cleanText });
  renderAllMessages();
  setWaiting(true);
  chatInput.value = "";
  chatInput.style.height = "auto";

  try {
    if (!chatId) {
      const createResponse = await fetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const created = await createResponse.json();
      if (!createResponse.ok) throw new Error(created.error || "Could not create a chat.");
      chatId = created.chat.id;
      sessionStorage.setItem(CHAT_KEY, chatId);
    }

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: cleanText, chatId }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The assistant request failed.");

    chatId = result.chatId;
    sessionStorage.setItem(CHAT_KEY, chatId);
    messages = result.chat.messages;
  } catch (error) {
    messages.push({
      role: "assistant",
      text: error.message || "The refund assistant is temporarily unavailable.",
    });
  } finally {
    setWaiting(false);
    renderAllMessages();
    chatInput.focus();
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(chatInput.value);
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 130)}px`;
});

document.querySelectorAll("[data-message]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.message));
});

newChatButton.addEventListener("click", async () => {
  if (waiting || !chatReady) return;
  setWaiting(true);
  try {
    const response = await fetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not create a new chat.");
    chatId = result.chat.id;
    sessionStorage.setItem(CHAT_KEY, chatId);
    messages = [];
    renderAllMessages();
    chatInput.focus();
  } catch (error) {
    messages = [{ role: "assistant", text: error.message || "Could not create a new chat." }];
    renderAllMessages();
  } finally {
    setWaiting(false);
  }
});

async function initializeChat() {
  if (chatId) {
    try {
      const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
        cache: "no-store",
      });
      const result = await response.json();
      if (response.ok) {
        messages = result.chat.messages;
      } else {
        chatId = null;
        sessionStorage.removeItem(CHAT_KEY);
      }
    } catch {
      messages = [
        {
          role: "assistant",
          text: "Could not load this chat. Please check that the web app is running and try again.",
        },
      ];
    }
  }

  chatReady = true;
  setWaiting(false);
  renderAllMessages();
}

chatInput.disabled = true;
sendButton.disabled = true;
renderAllMessages();
initializeChat();
