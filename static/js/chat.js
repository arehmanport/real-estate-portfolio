const chatWidget = document.getElementById("chat-widget");
const chatToggle = document.getElementById("chat-toggle");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const chatLoading = document.getElementById("chat-loading");

function toggleChat() {
  const isHidden = chatWidget.classList.toggle("hidden");
  chatToggle.querySelector(".chat-icon").classList.toggle("hidden", !isHidden);
  chatToggle.querySelector(".close-icon").classList.toggle("hidden", isHidden);
  if (!isHidden) {
    chatInput.focus();
  }
}

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  chatInput.value = "";
  chatLoading.classList.remove("hidden");
  scrollToBottom();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    chatLoading.classList.add("hidden");

    appendMessage("bot", data.reply);
    if (data.properties && data.properties.length > 0) {
      appendPropertyCards(data.properties);
    }
  } catch (err) {
    chatLoading.classList.add("hidden");
    appendMessage("bot", "Sorry, something went wrong. Please try again.");
  }

  scrollToBottom();
}

function appendMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role === "user" ? "user-message" : "bot-message"}`;

  if (role === "bot") {
    wrapper.innerHTML = `
      <div class="message-avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <div class="message-content">${formatText(text)}</div>
    `;
  } else {
    wrapper.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
  }

  chatMessages.appendChild(wrapper);
  scrollToBottom();
}

function appendPropertyCards(properties) {
  const container = document.createElement("div");
  container.className = "property-cards";

  properties.forEach((p) => {
    const price = p.price ? `$${Number(p.price).toLocaleString()}` : "Price N/A";
    const beds = p.bedrooms || "?";
    const baths = p.bathrooms || "?";
    const sqft = p.sqft ? `${Number(p.sqft).toLocaleString()} sqft` : "";
    const addr = p.address || "Address unavailable";
    const city = [p.city, p.state, p.zip].filter(Boolean).join(", ");
    const imgUrl = p.image_url || "";
    const listingUrl = p.id ? `/property/${Math.floor(p.id)}` : (p.listing_url || "#");

    const card = document.createElement("div");
    card.className = "property-card";
    card.innerHTML = `
      ${imgUrl ? `<div class="property-image" style="background-image: url('${imgUrl}')"></div>` : '<div class="property-image property-image-placeholder"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></div>'}
      <div class="property-info">
        <div class="property-price">${price}</div>
        <div class="property-address">${escapeHtml(addr)}</div>
        <div class="property-city">${escapeHtml(city)}</div>
        <div class="property-details">
          <span>${beds} bd</span>
          <span>${baths} ba</span>
          ${sqft ? `<span>${sqft}</span>` : ""}
        </div>
        <a href="${listingUrl}" target="_blank" rel="noopener" class="property-link">View Listing</a>
      </div>
    `;
    container.appendChild(card);
  });

  chatMessages.appendChild(container);
  scrollToBottom();
}

function formatText(text) {
  // Convert markdown-like formatting to HTML
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  });
}

async function resetChat() {
  try {
    await fetch("/reset", { method: "POST" });
  } catch (_) {}
  chatMessages.innerHTML = `
    <div class="message bot-message">
      <div class="message-avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <div class="message-content">
        Hi! I'm your AI real estate assistant. Tell me what kind of home you're looking for — budget, location, number of bedrooms — and I'll find the best matches for you!
      </div>
    </div>
  `;
}
