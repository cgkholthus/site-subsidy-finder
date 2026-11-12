// Shared "Ask about programs" chatbot, used on the results page (index.html) and the capital stack page (stack.html).
// It adds its own button and panel to the page. Each page tells it about the current site by defining
// window.siteChatContext() => { address, project, matchedAddress, stackHref, page }.
// Everything is inside this function so its helpers don't clash with the page's own scripts.
(() => {
  const PAGE_TEXT = {
    results: {
      placeholder: "e.g. Which programs could cover a funding gap here?",
      intro: "I can answer questions about the programs in this site's database",
    },
    stack: {
      placeholder: "e.g. How is the LIHTC equity estimated?",
      intro: "I can explain how this capital stack estimate works, its recommended numbers, and the programs in this site's database",
    },
  };

  const q = (sel) => document.querySelector(sel);
  const context = () => (window.siteChatContext ? window.siteChatContext() : {}) || {};

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function safeUrl(url) {
    try {
      // Site-relative links (like the "/stack.html" source) resolve against this site.
      const u = new URL(url, window.location.origin);
      return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
    } catch {
      return null;
    }
  }

  // A source pointing at the capital stack page opens it for the current site when one is looked up.
  function sourceUrl(url) {
    const ctx = context();
    if (url === "/stack.html" && ctx.address && ctx.stackHref) return safeUrl(ctx.stackHref);
    return safeUrl(url);
  }

  function formatDate(iso) {
    const d = new Date(iso + "T12:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  }

  function contactHtml(c) {
    if (!c) return "";
    const url = safeUrl(c.url);
    const bits = [
      c.phone && `<a href="tel:${esc(c.phone.replace(/[^\d+]/g, ""))}">${esc(c.phone)}</a>`,
      c.email && `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`,
      url && `<a href="${esc(url)}" target="_blank" rel="noopener">website</a>`,
    ].filter(Boolean).join(" · ");
    return `${esc(c.name)}${bits ? ` · ${bits}` : ""}`;
  }

  // ---------- panel ----------

  const page = context().page === "stack" ? "stack" : "results";
  const toggle = document.createElement("button");
  toggle.id = "chat-toggle";
  toggle.className = "chat-toggle";
  toggle.type = "button";
  toggle.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", "chat");
  toggle.textContent = "Ask a question";

  const panel = document.createElement("aside");
  panel.id = "chat";
  panel.className = "chat";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Question assistant");
  panel.innerHTML = `
    <header class="chat-head">
      <strong>Ask about programs</strong>
      <button id="chat-close" type="button" class="chat-close" aria-label="Close chat">×</button>
    </header>
    <p class="chat-disclosure"><strong>Student prototype.</strong> This assistant is a student project, not an official or professional service. It answers only from this site's program database, which may be incomplete or out of date, and it does not give legal or tax advice. Questions are sent to Google's Gemini AI.</p>
    <div id="chat-log" class="chat-log" aria-live="polite"></div>
    <form id="chat-form" class="chat-form" autocomplete="off">
      <input id="chat-input" type="text" maxlength="1000" placeholder="${esc(PAGE_TEXT[page].placeholder)}" required>
      <button type="submit">Send</button>
    </form>`;
  document.body.append(toggle, panel);

  // ---------- conversation ----------

  const chat = { messages: [], busy: false, greeted: false };

  function openChat(open) {
    panel.hidden = !open;
    toggle.hidden = open;
    toggle.setAttribute("aria-expanded", String(open));
    if (!open) return;
    if (!chat.greeted) {
      chat.greeted = true;
      const site = context().matchedAddress;
      addBotMessage({
        answer: `Hi! I'm a student prototype assistant. ${PAGE_TEXT[page].intro}` +
          (site ? `, plus the site at ${site}.` : ". Look up an address first if you want answers about a specific site.") +
          " I'll cite a source for every fact, and I'll say when I don't know.",
        sources: [],
      });
    }
    q("#chat-input").focus();
  }

  function addUserMessage(text) {
    const el = document.createElement("div");
    el.className = "msg user";
    el.textContent = text;
    q("#chat-log").appendChild(el);
    el.scrollIntoView({ block: "end" });
  }

  // Escape the answer, then turn [S#] markers into numbered links to the cited sources.
  function renderAnswer(text, sources) {
    const number = Object.fromEntries(sources.map((s, i) => [s.id, i + 1]));
    const byId = Object.fromEntries(sources.map((s) => [s.id, s]));
    return esc(text)
      .replace(/\s*\[(S\d+)\]/g, (m, id) => {
        const s = byId[id];
        const url = s && sourceUrl(s.url);
        return s ? `<sup>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener" title="${esc(s.title)}">[${number[id]}]</a>` : `[${number[id]}]`}</sup>` : "";
      })
      .split(/\n{2,}/).map((para) => `<p>${para.replace(/\n/g, "<br>")}</p>`).join("");
  }

  function addBotMessage(reply, isError = false) {
    const el = document.createElement("div");
    el.className = "msg bot" + (isError ? " error" : "");
    const tag = { dont_know: "Not sure", declined_advice: "No legal or tax advice" }[reply.type];
    const sources = reply.sources || [];
    const sourceList = sources.length
      ? `<ol class="sources">${sources.map((s) => {
          const url = sourceUrl(s.url);
          return `<li>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`;
        }).join("")}</ol>`
      : "";
    // Key requirements come straight from the program database, so they appear even when the answer is brief.
    const number = Object.fromEntries(sources.map((s, i) => [s.id, i + 1]));
    const requirements = (reply.requirements || []).length
      ? `<div class="chat-reqs"><strong>Key requirements</strong> <span class="muted-note">(from the program database)</span>${reply.requirements.map((r) => `
          <p><em>${esc(r.program)}</em>${number[r.source_id] ? ` <sup>[${number[r.source_id]}]</sup>` : ""}</p>
          <ul>${r.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`).join("")}</div>`
      : "";
    const contacts = (reply.contacts || []).length
      ? `<div class="chat-contacts"><strong>Agency contacts:</strong><ul>${reply.contacts.map((c) => `<li>${contactHtml(c)}</li>`).join("")}</ul></div>`
      : "";
    const verified = reply.last_verified ? `<div class="chat-verified">Information last verified ${esc(formatDate(reply.last_verified))}</div>` : "";
    el.innerHTML =
      (tag ? `<span class="tag">${esc(tag)}</span>` : "") +
      (isError ? `<p>${esc(reply.answer)}</p>` : renderAnswer(reply.answer, sources)) +
      requirements + sourceList + contacts + verified;
    q("#chat-log").appendChild(el);
    el.scrollIntoView({ block: "end" });
    return el;
  }

  q("#chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = q("#chat-input");
    const text = input.value.trim();
    if (!text || chat.busy) return;
    chat.busy = true;
    input.value = "";
    addUserMessage(text);
    chat.messages.push({ role: "user", content: text });
    const thinking = addBotMessage({ answer: "Thinking…", sources: [] });
    try {
      const ctx = context();
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: ctx.address || "", project: ctx.project || {}, messages: chat.messages }),
      });
      const data = await res.json();
      thinking.remove();
      if (!res.ok) throw new Error(data.error || "The chatbot couldn't answer.");
      addBotMessage(data);
      chat.messages.push({ role: "assistant", content: data.answer });
    } catch (err) {
      thinking.remove();
      addBotMessage({ answer: err.message }, true);
      chat.messages.pop(); // let the user retry the same question
    } finally {
      chat.busy = false;
      input.focus();
    }
  });

  toggle.addEventListener("click", () => openChat(true));
  q("#chat-close").addEventListener("click", () => openChat(false));

  fetch("/api/status").then((r) => r.json()).then((s) => { toggle.hidden = !s.chat_enabled; }).catch(() => {});
})();
