const $ = (sel) => document.querySelector(sel);

const state = {
  lookup: null,
  address: "",
  project: {},
  map: null,
};

// Location alone never establishes eligibility, so a location-only match is "potentially relevant";
// only a match that also passes the project answers says it meets the key requirements.
const STATUS_LABEL = {
  eligible: "Potentially relevant",
  applies: "Applies here",
  check: "Check requirements",
  ineligible: "Not eligible here",
  not_applicable: "Doesn't apply here",
};
function statusLabel(p) {
  if (p.status === "eligible" && p.project_checked) return "Matches key requirements";
  return STATUS_LABEL[p.status] || p.status;
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
const FUNDING_LABEL = { closed: "No open funding round right now", paused: "Approvals paused", limited: "Limited funds left" };
const LEVELS = [["federal", "Federal"], ["state", "State"], ["local", "County & City"], ["neighborhood", "Neighborhood"]];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function safeUrl(url) {
  try {
    const u = new URL(url, window.location.origin);
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
  closeSuggestions();
  const button = e.submitter || $("#search button");
  button.disabled = true;
  button.textContent = "Looking up…";
  $("#search-error").hidden = true;
  try {
    state.lookup = await fetchLookup(address);
    state.address = address;
    updateUrl();
    renderAll();
  } catch (err) {
    $("#search-error").textContent = err.message;
    $("#search-error").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Look up site";
  }
});

async function fetchLookup(address) {
  const params = new URLSearchParams({ address });
  if (Object.keys(state.project).length) params.set("project", JSON.stringify(state.project));
  const res = await fetch("/api/lookup?" + params);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Lookup failed");
  return data;
}

function updateUrl() {
  const params = new URLSearchParams({ address: state.address });
  if (Object.keys(state.project).length) params.set("project", JSON.stringify(state.project));
  history.replaceState(null, "", "?" + params);
  $("#stack-link").href = "/stack.html?" + params; // the estimate page uses the same site and answers
}

// ---------- project form ----------

function readProjectForm() {
  const form = $("#project-form");
  const out = {};
  for (const name of ["tenure", "construction", "ami", "owner", "commercial"]) {
    const v = form.elements[name].value;
    if (v) out[name] = name === "ami" ? Number(v) : v;
  }
  const units = parseInt(form.elements.units.value, 10);
  if (units > 0) out.units = units;
  const checked = [...form.querySelectorAll('input[name="populations"]:checked')].map((c) => c.value);
  if (checked.length) out.populations = checked.filter((v) => v !== "none");
  return out;
}

function fillProjectForm(project) {
  const form = $("#project-form");
  form.reset();
  for (const name of ["tenure", "construction", "ami", "owner", "commercial", "units"]) {
    if (project[name] != null) form.elements[name].value = String(project[name] === true ? "yes" : project[name] === false ? "no" : project[name]);
  }
  if (Array.isArray(project.populations)) {
    const values = project.populations.length ? project.populations : ["none"];
    form.querySelectorAll('input[name="populations"]').forEach((c) => (c.checked = values.includes(c.value)));
  }
}

let refreshTimer = null;
function onProjectChange(e) {
  // "None of these" and the specific groups are mutually exclusive.
  if (e && e.target.name === "populations") {
    const boxes = $("#project-form").querySelectorAll('input[name="populations"]');
    if (e.target.value === "none" && e.target.checked) boxes.forEach((c) => { if (c.value !== "none") c.checked = false; });
    if (e.target.value !== "none" && e.target.checked) boxes.forEach((c) => { if (c.value === "none") c.checked = false; });
  }
  state.project = readProjectForm();
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refreshPrograms, 300);
}

async function refreshPrograms() {
  if (!state.address) return;
  try {
    state.lookup = await fetchLookup(state.address);
    updateUrl();
    renderSite();
    renderPrograms();
  } catch (err) {
    $("#search-error").textContent = err.message;
    $("#search-error").hidden = false;
  }
}

$("#project-form").addEventListener("change", onProjectChange);
$("#project-form").addEventListener("input", (e) => { if (e.target.name === "units") onProjectChange(e); });
$("#project-clear").addEventListener("click", () => { fillProjectForm({}); onProjectChange(); });

// ---------- address autocomplete ----------

const suggest = { items: [], active: -1, timer: null, controller: null };

function closeSuggestions() {
  $("#address-suggestions").hidden = true;
  $("#address").setAttribute("aria-expanded", "false");
  suggest.items = [];
  suggest.active = -1;
}

function renderSuggestions() {
  const list = $("#address-suggestions");
  if (!suggest.items.length) return closeSuggestions();
  list.innerHTML = suggest.items
    .map((text, i) => `<li role="option" id="sugg-${i}" aria-selected="${i === suggest.active}" data-i="${i}">${esc(text)}</li>`)
    .join("") + `<li class="note" aria-hidden="true">Official address records for New Orleans and Portland</li>`;
  list.hidden = false;
  $("#address").setAttribute("aria-expanded", "true");
  $("#address").setAttribute("aria-activedescendant", suggest.active >= 0 ? `sugg-${suggest.active}` : "");
}

function pickSuggestion(i) {
  const text = suggest.items[i];
  if (!text) return;
  $("#address").value = text;
  closeSuggestions();
  $("#search").requestSubmit();
}

$("#address").addEventListener("input", () => {
  clearTimeout(suggest.timer);
  const text = $("#address").value.trim();
  if (text.length < 4 || !/^\d+\s+\S/.test(text)) return closeSuggestions();
  suggest.timer = setTimeout(async () => {
    suggest.controller?.abort();
    suggest.controller = new AbortController();
    try {
      const res = await fetch("/api/suggest?q=" + encodeURIComponent(text), { signal: suggest.controller.signal });
      const data = await res.json();
      if ($("#address").value.trim() !== text) return; // the user kept typing
      suggest.items = data.suggestions || [];
      suggest.active = -1;
      renderSuggestions();
    } catch {
      /* aborted or offline: just don't suggest */
    }
  }, 250);
});

$("#address").addEventListener("keydown", (e) => {
  if ($("#address-suggestions").hidden) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    // Cycle through the suggestions and back to the typed text (-1).
    const n = suggest.items.length;
    let next = suggest.active + (e.key === "ArrowDown" ? 1 : -1);
    if (next >= n) next = -1;
    if (next < -1) next = n - 1;
    suggest.active = next;
    renderSuggestions();
  } else if (e.key === "Enter" && suggest.active >= 0) {
    e.preventDefault();
    pickSuggestion(suggest.active);
  } else if (e.key === "Escape") {
    closeSuggestions();
  }
});

$("#address-suggestions").addEventListener("mousedown", (e) => {
  const li = e.target.closest("li[data-i]");
  if (li) {
    e.preventDefault(); // keep focus in the box
    pickSuggestion(Number(li.dataset.i));
  }
});
$("#address").addEventListener("blur", () => setTimeout(closeSuggestions, 150));

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
        <span class="badge ${esc(p.status)}${p.project_checked ? " checked" : ""}">${esc(statusLabel(p))}</span>
      </div>
      <p>${esc(p.summary)}</p>
      ${p.reason ? `<p class="reason"><strong>Why:</strong> ${esc(p.reason)}</p>` : ""}
      ${p.eligibility ? `<p class="reason"><strong>Eligibility:</strong> ${esc(p.eligibility)}</p>` : ""}
      ${p.limits ? `<p class="reason"><strong>Caps and limits:</strong> ${esc(p.limits)}</p>` : ""}
      ${details ? `<div class="details">${details}</div>` : ""}
      ${p.funding ? `<span class="funding" title="${esc(p.funding.note)}">${esc(FUNDING_LABEL[p.funding.status] || "Check funding")}: ${esc(p.funding.note)}</span>` : ""}
      ${p.contact ? `<p class="contact-line"><strong>Contact:</strong> ${contactHtml(p.contact)}</p>` : ""}
      <p class="source-line">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">Official source ↗</a>` : ""}${p.last_reviewed ? `<span class="verified">Last verified ${esc(formatDate(p.last_reviewed))}</span>` : ""}</p>
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
  const { site, tract_stats: stats, neighborhood, city } = state.lookup;
  $("#site-address").textContent = site.matched_address;
  const facts = [
    ["City", city.name],
    ["Neighborhood", neighborhood],
    ["County", site.county_name],
    ["Census tract", `${site.tract_name || "—"} (${site.tract_geoid || "—"})`],
  ];
  if (stats && stats.poverty_rate != null) facts.push(["Tract poverty rate", stats.poverty_rate + "%"]);
  $("#site-facts").innerHTML = facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v || "—")}</dd>`).join("");

  const zones = state.lookup.zones || [];
  $("#flags").innerHTML = zones
    .map((z, i) => `<button type="button" class="flag ${z.on ? "on" : ""}" data-zone="${i}" aria-expanded="false"
        title="What does this mean?">${z.on ? "✓ " : ""}${esc(z.label)} <span class="flag-info" aria-hidden="true">ⓘ</span></button>`)
    .join("");
  $("#zone-detail").hidden = true;
}

function showZone(index) {
  const z = (state.lookup.zones || [])[index];
  const panel = $("#zone-detail");
  const buttons = document.querySelectorAll("#flags .flag");
  const alreadyOpen = !panel.hidden && panel.dataset.zone === String(index);
  buttons.forEach((b) => b.setAttribute("aria-expanded", "false"));
  if (!z || alreadyOpen) {
    panel.hidden = true;
    return;
  }
  const url = safeUrl(z.url);
  panel.dataset.zone = String(index);
  panel.innerHTML = `
    <div class="zone-head">
      <strong>${esc(z.title || z.label)}</strong>
      <span class="zone-status ${z.on ? "on" : ""}">${z.on ? "This site is inside" : "This site is not inside"}</span>
      <button type="button" class="zone-close" aria-label="Close">×</button>
    </div>
    ${z.text ? `<p>${esc(z.text)}</p>` : ""}
    ${z.meaning ? `<p><strong>What it means for your project:</strong> ${esc(z.meaning)}</p>` : ""}
    ${url ? `<p><a href="${esc(url)}" target="_blank" rel="noopener">Source ↗</a></p>` : ""}`;
  panel.hidden = false;
  buttons[index].setAttribute("aria-expanded", "true");
  panel.querySelector(".zone-close").addEventListener("click", () => showZone(index));
}

$("#flags").addEventListener("click", (e) => {
  const btn = e.target.closest(".flag");
  if (btn) showZone(Number(btn.dataset.zone));
});

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
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", "map-legend");
      div.innerHTML = `
        <div><span class="key pin"></span>Your site</div>
        <div><span class="key dot"></span>Existing LIHTC property (click for details)</div>
        <div><span class="key ring"></span>1-mile radius</div>`;
      return div;
    };
    legend.addTo(state.map);
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
  $("#intro").hidden = true; // the tool overview only shows before the first search
  renderSite();
  renderCity();
  renderPrograms();
  renderMarket();
  selectTab("federal");
  renderMap();
}

// ---------- export ----------

$("#export").addEventListener("click", () => {
  const rows = [["Level", "Program", "Type", "Agency", "Status", "This site", "Eligibility", "Amount", "Timing",
    "Contact", "Phone", "Email", "URL", "Last verified"]];
  for (const [level, label] of LEVELS) {
    for (const p of state.lookup.programs[level] || []) {
      const c = p.contact || {};
      rows.push([label, p.name, p.type, p.agency, statusLabel(p), p.reason || "",
        p.eligibility || "", p.amount || "", p.deadline || "", c.name || "", c.phone || "", c.email || "", p.url || "",
        p.last_reviewed || ""]);
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

// The chatbot lives in chat.js (shared with the capital stack page); this tells it which site is open.
window.siteChatContext = () => ({
  page: "results",
  address: state.address,
  project: state.project,
  matchedAddress: state.lookup && state.lookup.site.matched_address,
  stackHref: $("#stack-link").getAttribute("href"),
});

// Restore a search from the URL (?address=...)
const initialParams = new URLSearchParams(location.search);
try {
  state.project = JSON.parse(initialParams.get("project") || "{}") || {};
} catch {
  state.project = {};
}
fillProjectForm(state.project);
const initial = initialParams.get("address");
if (initial) {
  $("#address").value = initial;
  $("#search").requestSubmit();
}
