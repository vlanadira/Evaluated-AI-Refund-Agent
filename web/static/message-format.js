function appendFormattedMessageText(container, value) {
  const text = typeof value === "string" ? value : String(value || "");
  const boldPattern = /\*\*([\s\S]+?)\*\*/g;
  let cursor = 0;

  for (const match of text.matchAll(boldPattern)) {
    container.append(document.createTextNode(text.slice(cursor, match.index)));
    const bold = document.createElement("strong");
    bold.textContent = match[1];
    container.append(bold);
    cursor = match.index + match[0].length;
  }

  container.append(document.createTextNode(text.slice(cursor)));
}
