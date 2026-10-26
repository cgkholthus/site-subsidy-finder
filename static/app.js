const $ = (sel) => document.querySelector(sel);

const state = {
  lookup: null,
  map: null,
};

const STATUS_LABEL = {
  eligible: "Site qualifies",
  applies: "Applies here",
  check: "Check eligibility",
  ineligible: "Not eligible here",
  not_applicable: "Doesn't apply here",
};
const LEVELS = [["federal", "Federal"], ["state", "State"], ["local", "County & City"], ["neighborhood", "Neighborhood"]];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

function money(n) {
  return n == null ? "—" : "$" + Number(n).toLocaleString();
}

function formatDate(iso) {
  const d = new Date(iso + "T12:00:00");
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

// ---------- search ----------

$("#search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const address = $("#address").value.trim();
  if (!address) return;
  const button = e.submitter || $("#search button");
  button.disabled = true;
  button.textContent = "Looking up…";
  $("#search-error").hidden = true;
  try {
    const res = await fetch("/api/lookup?address=" + encodeURIComponent(address));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Lookup failed");
    state.lookup = data;
    state.address = address;
    history.replaceState(null, "", "?address=" + encodeURIComponent(address));
    renderAll();
  } catch (err) {
    $("#search-error").textContent = err.message;
    $("#search-error").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Look up site";
  }
});

// ---------- tabs ----------

document.querySelectorAll(".tabs button").forEach((tab) => {
  tab.addEventListener("click", () => selectTab(tab.dataset.level));
});

function selectTab(level) {
  document.querySelectorAll(".tabs button").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.level === level)));
  document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "panel-" + level));
}

// ---------- rendering ----------

function programCard(p) {
  const url = safeUrl(p.url);
  const details = [
    p.amount && `<span><strong>Amount:</strong> ${esc(p.amount)}</span>`,
    p.deadline && `<span><strong>Timing:</strong> ${esc(p.deadline)}</span>`,
  ].filter(Boolean).join("");
  return `
    <article class="card ${esc(p.status)}">
      <div class="card-head">
        <div>
          <h4>${esc(p.name)}</h4>
          <div class="meta">${esc(p.type)} · ${esc(p.agency)}</div>
        </div>
        <span class="badge ${esc(p.status)}">${esc(STATUS_LABEL[p.status] || p.status)}</span>
      </div>
      <p>${esc(p.summary)}</p>
      ${p.reason ? `<p class="reason"><strong>This site:</strong> ${esc(p.reason)}</p>` : ""}
      ${p.eligibility ? `<p class="reason"><strong>Eligibility:</strong> ${esc(p.eligibility)}</p>` : ""}
      ${details ? `<div class="details">${details}</div>` : ""}
      ${url ? `<p><a href="${esc(url)}" target="_blank" rel="noopener">Official source ↗</a></p>` : ""}
    </article>`;
}

function renderPrograms() {
  for (const [level] of LEVELS) {
    const list = state.lookup.programs[level] || [];
    const html = list.length ? list.map(programCard).join("") : `<p class="empty">No programs at this level.</p>`;
    const target = level === "neighborhood" ? $("#neighborhood-programs") : $("#panel-" + level);
    target.innerHTML = (level === "neighborhood" ? `<h3>Districts and neighborhood programs</h3>` : "") + html;
    const relevant = list.filter((p) => p.status !== "ineligible" && p.status !== "not_applicable").length;
    document.querySelector(`.tabs button[data-level="${level}"] .count`).textContent = relevant ? `(${relevant})` : "";
  }
}

function renderSite() {
  const { site, flags, tract_stats: stats, district_chips: districtChips, neighborhood, city } = state.lookup;
  $("#site-address").textContent = site.matched_address;
  const facts = [
    ["City", city.name],
    ["Neighborhood", neighborhood],
    ["County", site.county_name],
    ["Census tract", `${site.tract_name || "—"} (${site.tract_geoid || "—"})`],
  ];
  if (stats) {
    facts.push(["Tract poverty rate", stats.poverty_rate != null ? stats.poverty_rate + "%" : "—"]);
    facts.push(["Tract median family income", money(stats.median_family_income)]);
  }
  $("#site-facts").innerHTML = facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v || "—")}</dd>`).join("");

  const chips = [
    ["Qualified Census Tract", flags.qct],
    [flags.dda_name ? `DDA: ${flags.dda_name}` : "Difficult Development Area", flags.dda],
    ["Opportunity Zone", flags.opportunity_zone],
    [flags.promise_zone ? `Promise Zone: ${flags.promise_zone}` : "Promise Zone", !!flags.promise_zone],
  ];
  for (const label of districtChips) chips.push([label, true]);
  $("#flags").innerHTML = chips
    .map(([label, on]) => `<span class="flag ${on ? "on" : ""}">${on ? "✓ " : ""}${esc(label)}</span>`)
    .join("");
}

function renderCity() {
  const { city } = state.lookup;
  $("#city-context").innerHTML = `
    <h3>${esc(city.name)} funding landscape</h3>
    <p>${esc(city.local_context)}</p>`;
  $("#disclaimer").textContent =
    `Site designations come from HUD, Census and ${city.name} city map data, checked live. ` +
    `The ${city.name} program database was last reviewed ${formatDate(city.last_reviewed)}; ` +
    `programs, amounts and deadlines change, so confirm with the administering agency before relying on them.`;
}

function renderMarket() {
  const fmr = state.lookup.fair_market_rents;
  $("#fmr").innerHTML = fmr
    ? `<div class="table-scroll"><table>
        <thead><tr><th>HUD Fair Market Rent — ${esc(fmr.area)}</th><th class="num">Studio</th><th class="num">1 BR</th><th class="num">2 BR</th><th class="num">3 BR</th><th class="num">4 BR</th></tr></thead>
        <tbody><tr><td>Monthly rent</td>${[fmr.studio, fmr.one_br, fmr.two_br, fmr.three_br, fmr.four_br].map((v) => `<td class="num">${money(v)}</td>`).join("")}</tr></tbody>
      </table></div>`
    : `<p class="empty">Fair Market Rent data unavailable.</p>`;

  const nearby = state.lookup.nearby_lihtc || [];
  $("#nearby").innerHTML = nearby.length
    ? `<div class="table-scroll"><table>
        <thead><tr><th>Property</th><th>Address</th><th class="num">Units</th><th class="num">Low-income</th><th class="num">In service</th><th>Other funding</th></tr></thead>
        <tbody>${nearby.map((p) => `<tr>
          <td>${esc(p.name)}</td><td>${esc(p.address)}</td>
          <td class="num">${esc(p.units ?? "—")}</td><td class="num">${esc(p.low_income_units ?? "—")}</td>
          <td class="num">${esc(p.year_placed_in_service || "—")}</td>
          <td>${esc([p.bond_financed && "Bonds", p.home_funds && "HOME", p.cdbg_funds && "CDBG"].filter(Boolean).join(", ") || "—")}</td>
        </tr>`).join("")}</tbody>
      </table></div>`
    : `<p class="empty">No HUD-recorded LIHTC properties within one mile.</p>`;
}

function renderMap() {
  const { site } = state.lookup;
  if (!window.L) return;
  if (!state.map) {
    state.map = L.map("map", { scrollWheelZoom: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(state.map);
  }
  state.map.eachLayer((layer) => { if (!(layer instanceof L.TileLayer)) state.map.removeLayer(layer); });
  L.circle([site.lat, site.lon], { radius: 1609, color: "#1f6f50", weight: 1, fillOpacity: 0.04 }).addTo(state.map);
  for (const p of state.lookup.nearby_lihtc || []) {
    if (p.lat == null) continue;
    L.circleMarker([p.lat, p.lon], { radius: 5, color: "#7a5600", fillOpacity: 0.7 })
      .bindPopup(`<strong>${esc(p.name)}</strong><br>${esc(p.units ?? "?")} units · ${esc(p.year_placed_in_service || "")}`)
      .addTo(state.map);
  }
  L.marker([site.lat, site.lon]).bindPopup(esc(site.matched_address)).addTo(state.map);
  setTimeout(() => {
    state.map.invalidateSize();
    state.map.fitBounds(L.latLng(site.lat, site.lon).toBounds(2 * 1609), { padding: [8, 8] });
  }, 0);
}

function renderAll() {
  $("#results").hidden = false;
  renderSite();
  renderCity();
  renderPrograms();
  renderMarket();
  selectTab("federal");
  renderMap();
}

// ---------- export ----------

$("#export").addEventListener("click", () => {
  const rows = [["Level", "Program", "Type", "Agency", "Status", "This site", "Eligibility", "Amount", "Timing", "URL"]];
  for (const [level, label] of LEVELS) {
    for (const p of state.lookup.programs[level] || []) {
      rows.push([label, p.name, p.type, p.agency, STATUS_LABEL[p.status] || "", p.reason || "",
        p.eligibility || "", p.amount || "", p.deadline || "", p.url || ""]);
    }
  }
  const csv = rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "site-programs.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---------- chat ----------

const chat = { messages: [], busy: false, greeted: false };

function openChat(open) {
  $("#chat").hidden = !open;
  $("#chat-toggle").hidden = open;
  $("#chat-toggle").setAttribute("aria-expanded", String(open));
  if (open) {
    if (!chat.greeted) {
      chat.greeted = true;
      addBotMessage({
        answer: "Hi! I'm a student prototype assistant. I can answer questions about the programs in this site's database" +
          (state.lookup ? ` and the site at ${state.lookup.site.matched_address}.` : ". Look up an address first if you want answers about a specific site.") +
          " I'll cite a source for every fact, and I'll say when I don't know.",
        sources: [],
      });
    }
    $("#chat-input").focus();
  }
}

function addUserMessage(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.textContent = text;
  $("#chat-log").appendChild(el);
  el.scrollIntoView({ block: "end" });
}

// Escape the answer, then turn [S#] markers into numbered links to the cited sources.
function renderAnswer(text, sources) {
  const number = Object.fromEntries(sources.map((s, i) => [s.id, i + 1]));
  const byId = Object.fromEntries(sources.map((s) => [s.id, s]));
  return esc(text)
    .replace(/\s*\[(S\d+)\]/g, (m, id) => {
      const s = byId[id];
      const url = s && safeUrl(s.url);
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
        const url = safeUrl(s.url);
        return `<li>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</li>`;
      }).join("")}</ol>`
    : "";
  el.innerHTML =
    (tag ? `<span class="tag">${esc(tag)}</span>` : "") +
    (isError ? `<p>${esc(reply.answer)}</p>` : renderAnswer(reply.answer, sources)) +
    sourceList;
  $("#chat-log").appendChild(el);
  el.scrollIntoView({ block: "end" });
  return el;
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || chat.busy) return;
  chat.busy = true;
  input.value = "";
  addUserMessage(text);
  chat.messages.push({ role: "user", content: text });
  const thinking = addBotMessage({ answer: "Thinking…", sources: [] });
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: state.address || "", messages: chat.messages }),
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

$("#chat-toggle").addEventListener("click", () => openChat(true));
$("#chat-close").addEventListener("click", () => openChat(false));

fetch("/api/status").then((r) => r.json()).then((s) => { $("#chat-toggle").hidden = !s.chat_enabled; }).catch(() => {});

// Restore a search from the URL (?address=...)
const initial = new URLSearchParams(location.search).get("address");
if (initial) {
  $("#address").value = initial;
  $("#search").requestSubmit();
}
