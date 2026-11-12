// Capital stack estimate: combines the potentially relevant programs for a site into rough sources and uses.
// Everything here is a simplified planning estimate, not advice; every assumption is editable on the page.

const $ = (sel) => document.querySelector(sel);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const usd = (n) => (n < 0 ? "−$" : "$") + Math.round(Math.abs(n)).toLocaleString();
const pct = (n) => (n * 100).toFixed(0) + "%";

const state = { lookup: null, values: {}, custom: {} };

// ---------- assumptions ----------

// Each assumption: key, label, unit ("usd", "pct", "num", "ratio", "price"), default (number or fn of lookup), help.
// `quick` ones show at the top; `show(lookup)` hides inputs that don't apply to this project.
// Where the city database has a researched market number (city.market[key]), it becomes the default and is shown
// as the recommendation with its source.
const isOwnership = (l) => l.project.tenure === "ownership";
const ASSUMPTIONS = [
  { quick: true, key: "units", label: "Housing units", unit: "num", def: (l) => l.project.units || 60 },
  { quick: true, key: "cost_per_unit", label: "Total development cost per unit", unit: "usd", def: 400000,
    help: "Everything: land, construction, fees and financing costs, divided by units." },
  { quick: true, key: "rent", label: "Average monthly rent per unit", unit: "usd", def: 1200, show: (l) => !isOwnership(l),
    help: "Use the program's rent limits for your income levels." },
  { quick: true, key: "sale_price", label: "Affordable sale price per home", unit: "usd", def: 250000, show: isOwnership,
    help: "Placeholder; use the program's price limits." },
  { quick: true, key: "opex", label: "Yearly operating cost per unit", unit: "usd", def: 8000, show: (l) => !isOwnership(l),
    help: "Management, maintenance, insurance, utilities, taxes and reserves." },
  { quick: true, key: "commercial_cost", label: "Commercial or community space cost", unit: "usd",
    def: (l) => (l.project.commercial ? 1500000 : 0), show: (l) => !!l.project.commercial,
    help: "Only used for New Markets Tax Credits." },
  { quick: true, key: "qre_pct", label: "Share of cost that is historic renovation work", unit: "pct",
    def: (l) => (l.project.construction === "rehab" ? 70 : 0), show: (l) => l.project.construction === "rehab",
    help: "Only used for historic tax credits." },

  { key: "land_pct", label: "Land share of total cost", unit: "pct", def: 8 },
  { key: "affordable_pct", label: "Share of units that are affordable", unit: "pct", def: 100 },
  { key: "vacancy", label: "Vacancy and collection loss", unit: "pct", def: 7 },
  { key: "rent_growth", label: "Yearly rent growth (pro forma)", unit: "pct", def: 2,
    help: "Used only in the downloadable pro forma's 15-year cash flow." },
  { key: "expense_growth", label: "Yearly operating cost growth (pro forma)", unit: "pct", def: 3,
    help: "Oregon's housing agency underwrites a standard 3% yearly expense increase." },
  { key: "rate", label: "Permanent loan interest rate", unit: "pct", def: 6.5 },
  { key: "amort", label: "Loan term (years)", unit: "num", def: 35 },
  { key: "dscr", label: "Debt coverage ratio required", unit: "ratio", def: 1.2 },
  { key: "basis_pct", label: "Share of housing cost in tax credit basis", unit: "pct", def: 85,
    help: "Some costs (land, reserves, some financing costs) don't count toward LIHTC basis." },
  { key: "lihtc_price", label: "LIHTC price per $1 of credit", unit: "price", def: 0.83 },
  { key: "fed_htc_price", label: "Federal historic credit price per $1", unit: "price", def: 0.88 },
  { key: "state_htc_price", label: "State historic credit price per $1", unit: "price", def: 0.8 },
  { key: "nmtc_net_pct", label: "NMTC net benefit (share of commercial cost)", unit: "pct", def: 20 },
  { key: "soft_pct", label: "Soft costs and financing (share of housing cost)", unit: "pct", def: 20,
    help: "Design, permits, legal, insurance, interest and reserves. Only changes the \"where it goes\" chart." },
  { key: "dev_fee_pct", label: "Developer fee (share of total cost)", unit: "pct", def: 12 },
  { key: "deferred_pct", label: "Most of the fee that can be deferred", unit: "pct", def: 40 },
];

function market(key) {
  return (state.lookup.city.market || {})[key] || null;
}

function defaultFor(a) {
  const m = market(a.key);
  if (m) return m.value;
  return typeof a.def === "function" ? a.def(state.lookup) : a.def;
}

// Rough entries are fine: "400k", "1.2m", "$1,100", "8%", "0.83".
function parseRough(text) {
  const s = String(text).trim().toLowerCase().replace(/[$,%\s]/g, "");
  const m = s.match(/^(-?\d*\.?\d+)([kmb])?$/);
  if (!m) return null;
  const mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2]] || 1;
  return parseFloat(m[1]) * mult;
}

function formatValue(a, v) {
  if (a.unit === "usd") return "$" + Math.round(v).toLocaleString();
  if (a.unit === "pct") return `${+v.toFixed(2)}%`;
  if (a.unit === "price") return "$" + v.toFixed(2);
  if (a.unit === "ratio") return v.toFixed(2);
  return String(Math.round(v * 100) / 100);
}

function fieldHtml(a) {
  const m = market(a.key);
  const rec = m ? `<small class="rec">Recommended for ${esc(state.lookup.city.name)}: <strong>${esc(formatValue(a, m.value))}</strong>. ${esc(m.note)}
      ${m.url ? `<a href="${esc(m.url)}" target="_blank" rel="noopener">Source ↗</a>` : ""}</small>` : "";
  return `
    <label>${esc(a.label)}
      <input type="text" inputmode="decimal" name="${a.key}" value="${esc(formatValue(a, state.values[a.key]))}" autocomplete="off">
      ${rec}
      ${a.help ? `<small>${esc(a.help)}</small>` : ""}
    </label>`;
}

function renderAssumptions() {
  const visible = ASSUMPTIONS.filter((a) => !a.show || a.show(state.lookup));
  const quick = visible.filter((a) => a.quick);
  const more = visible.filter((a) => !a.quick);
  const asOf = (state.lookup.city.market || {}).as_of;
  $("#assumptions").innerHTML = `
    <div class="quick">${quick.map(fieldHtml).join("")}</div>
    <p class="rough-hint">Rough numbers are fine: type 400k, 1.2m or $1,100.</p>
    <button type="button" id="use-recommended" class="secondary">Use recommended ${esc(state.lookup.city.name)} numbers</button>
    ${asOf ? `<p class="rough-hint">Recommendations reviewed ${esc(asOf)}; they're starting points, not quotes.</p>` : ""}
    <details class="more">
      <summary>More assumptions (optional)</summary>
      ${more.map(fieldHtml).join("")}
    </details>`;
  $("#use-recommended").addEventListener("click", () => {
    for (const a of ASSUMPTIONS) state.values[a.key] = defaultFor(a);
    const wasOpen = $("#assumptions details.more").open;
    renderAssumptions();
    $("#assumptions details.more").open = wasOpen;
    renderScenarios();
  });
}

// Recalculate as people type; tidy the number's formatting when they leave the box.
$("#assumptions").addEventListener("input", (e) => {
  if (!e.target.name) return;
  const v = parseRough(e.target.value);
  e.target.classList.toggle("invalid", v === null && e.target.value.trim() !== "");
  if (v === null) return;
  state.values[e.target.name] = Math.max(0, v);
  renderScenarios();
});
$("#assumptions").addEventListener("focusout", (e) => {
  const a = ASSUMPTIONS.find((x) => x.key === e.target.name);
  if (a) {
    e.target.value = formatValue(a, state.values[a.key]);
    e.target.classList.remove("invalid");
  }
});

// ---------- programs ----------

function allPrograms() {
  return Object.values(state.lookup.programs).flat();
}

function program(id) {
  return allPrograms().find((p) => p.id === id);
}

// A program can be counted if it isn't ruled out for this site and project.
function usable(id) {
  const p = program(id);
  return p && (p.status === "eligible" || p.status === "check") ? p : null;
}

// Sources with no predictable amount: start at $0 so they never inflate the estimate; the user can enter an award.
const ENTERED_SOURCES = [
  { id: "home", hint: "City HOME award, if expected (structure as a loan so it doesn't reduce LIHTC basis)" },
  { id: "cdbg", hint: "City CDBG award, if expected" },
  { id: "htf", hint: "State Housing Trust Fund award, if expected" },
  { id: "nola_gap", hint: "City gap financing award, if expected (historically 10-15% of cost)" },
  { id: "la_home_htf_gap", hint: "Up to $2,000,000 per project, only after a LIHTC award" },
  { id: "phb_nofa", hint: "Housing Bureau award (bond, TIF or other local money), if expected" },
  { id: "metro_bond", hint: "Metro bond award, if expected (nearly fully allocated)" },
  { id: "or_lift_rental", hint: "LIFT Rental award, if expected" },
  { id: "pdx_pcef", hint: "Clean energy grant, if expected" },
  { id: "cmf", hint: "Loan or grant from a local CDFI with Capital Magnet Fund money" },
];

// Programs that improve the budget in other ways; listed, not counted as sources.
const ALSO_HELPS = {
  oz: "Opportunity Zone investors may accept lower returns, which can help raise equity.",
  nola_rta: "Freezes property taxes at the pre-renovation value for 5 years, lowering operating costs.",
  nola_pilot: "A PILOT lowers property taxes, which raises net income and the loan the project can support.",
  pdx_multe: "A 10-year property tax exemption raises net income and the loan the project can support.",
  pdx_nplte: "A nonprofit property tax exemption raises net income and the loan the project can support.",
  pdx_sdc_temp: "Waived system development charges lower development cost (enter your reduced cost above).",
  pdx_sdc_affordable: "SDC exemption for affordable units lowers development cost.",
  or_oahtc: "A lower interest rate on the permanent loan (lower the rate above to see the effect).",
  nola_hano_pbv: "Project-based vouchers raise the rent the project collects, supporting a bigger loan.",
  home_forward_pbv: "Project-based vouchers raise the rent the project collects, supporting a bigger loan.",
  metro_shs: "Rent assistance and services funding for supportive units.",
  s811: "Rental assistance for units set aside for people with disabilities.",
  promise: "Preference points on federal grant competitions.",
  pdx_tif: "District TIF money for affordable housing flows through Housing Bureau awards (enter it on that line).",
};

// ---------- calculations ----------

function loanConstant(ratePct, years) {
  const r = ratePct / 100 / 12;
  const n = years * 12;
  if (r === 0) return 12 / n;
  return (r / (1 - Math.pow(1 + r, -n))) * 12;
}

function calcScenario(kind) {
  const v = state.values;
  const flags = state.lookup.flags;
  const housingCost = v.units * v.cost_per_unit;
  const tdc = housingCost + v.commercial_cost;
  const rows = [];
  const add = (row) => rows.push(row);

  // Rentals: a permanent loan sized from net operating income. Homeownership: sale proceeds repay the construction loan.
  const noi = v.units * v.rent * 12 * (1 - v.vacancy / 100) - v.units * v.opex;
  const loan = noi > 0 && v.dscr > 0 ? noi / v.dscr / loanConstant(v.rate, v.amort) : 0;
  if (state.lookup.project.tenure === "ownership") {
    add({ name: "Home sale proceeds", amount: v.units * v.sale_price,
          how: `${v.units} homes × ${usd(v.sale_price)} affordable sale price (repays construction financing)` });
  } else {
    add({ name: kind === "4" ? "Permanent loan (tax-exempt bond financed)" : "Permanent loan", amount: loan,
          how: `Net operating income ${usd(noi)}/yr ÷ ${v.dscr} coverage, at ${v.rate}% over ${v.amort} years` });
  }

  // Historic credits on qualified rehab work.
  const qre = tdc * (v.qre_pct / 100);
  if (qre > 0 && usable("htc")) {
    add({ name: "Federal historic tax credit equity", amount: qre * 0.2 * v.fed_htc_price, programId: "htc",
          how: `Rehab costs ${usd(qre)} × 20% × $${v.fed_htc_price}` });
  }
  if (qre > 0 && usable("la_historic_credit")) {
    add({ name: "Louisiana historic tax credit equity", amount: qre * 0.25 * v.state_htc_price, programId: "la_historic_credit",
          how: `Rehab costs ${usd(qre)} × 25% × $${v.state_htc_price}` });
  }

  // NMTC on the commercial part only.
  if (v.commercial_cost > 0 && usable("nmtc")) {
    add({ name: "New Markets Tax Credit net benefit (commercial space)", amount: v.commercial_cost * (v.nmtc_net_pct / 100), programId: "nmtc",
          how: `Commercial cost ${usd(v.commercial_cost)} × ${v.nmtc_net_pct}% typical net benefit` });
  }

  // FHLBank AHP: typical award size from the program description.
  if (usable("fhlb_ahp")) {
    add({ name: "FHLBank AHP grant", amount: state.custom.fhlb_ahp ?? 1000000, programId: "fhlb_ahp", editable: true,
          how: "Assumed $1,000,000 (typical awards are up to about $1-2 million)" });
  }

  // Awards the user enters.
  for (const src of ENTERED_SOURCES) {
    const p = usable(src.id);
    if (!p) continue;
    add({ name: p.name, amount: state.custom[src.id] ?? 0, programId: src.id, editable: true, how: src.hint });
  }

  // LIHTC equity comes after the other sources: agencies may only award the credits a project needs to be
  // feasible (IRC 42(m)(2)), so use the smaller of the formula maximum and the remaining gap.
  if (kind === "9" || kind === "4") {
    const landShare = tdc > 0 ? housingCost / tdc : 1;
    const basis = (housingCost - tdc * (v.land_pct / 100) * landShare) * (v.basis_pct / 100);
    const boosted = flags.qct || flags.dda;
    const qualified = basis * (boosted ? 1.3 : 1) * (v.affordable_pct / 100);
    const rate = kind === "9" ? 0.09 : 0.04;
    const maxEquity = qualified * rate * 10 * v.lihtc_price;
    const otherSources = rows.reduce((sum, r) => sum + r.amount, 0);
    const equity = Math.max(0, Math.min(maxEquity, tdc - otherSources));
    const formula = `Eligible basis ${usd(basis)}${boosted ? " × 130% boost (QCT/DDA)" : ""} × ${v.affordable_pct}% affordable × ${rate * 100}% × 10 years × $${v.lihtc_price} = up to ${usd(maxEquity)}`;
    rows.splice(1, 0, {
      name: `${kind}% LIHTC equity`, amount: equity, programId: kind === "9" ? "lihtc9" : "lihtc4",
      how: equity < maxEquity - 1
        ? `${formula}. Sized down to the remaining gap, because agencies only award the credits a project needs.`
        : formula,
    });
  }

  const subtotal = rows.reduce((s, r) => s + r.amount, 0);
  const deferredMax = tdc * (v.dev_fee_pct / 100) * (v.deferred_pct / 100);
  const deferred = Math.max(0, Math.min(deferredMax, tdc - subtotal));
  add({ name: "Deferred developer fee", amount: deferred,
        how: `Fills the gap up to ${v.deferred_pct}% of a ${v.dev_fee_pct}% fee (${usd(deferredMax)})` });

  const total = subtotal + deferred;

  // Uses: where the money goes. Land, developer fee and soft costs are shares of cost; construction is the rest.
  const land = tdc * (v.land_pct / 100);
  const fee = tdc * (v.dev_fee_pct / 100);
  const soft = housingCost * (v.soft_pct / 100);
  const uses = [
    { key: "land", name: "Land", amount: land },
    { key: "hard", name: "Construction", amount: Math.max(0, tdc - land - fee - soft - v.commercial_cost) },
    { key: "soft", name: "Soft costs and financing", amount: soft },
    { key: "fee", name: "Developer fee", amount: fee },
    { key: "commercial", name: "Commercial space", amount: v.commercial_cost },
  ];
  return { kind, tdc, rows, total, gap: tdc - total, noi, loan, uses };
}

// ---------- sources-and-uses chart ----------

// Sources are grouped into at most six blocks, each with a fixed color slot so a source keeps its color
// across scenarios. The gap is a neutral block, not a source.
const SOURCE_GROUPS = [
  { key: "loan", slot: 1 },
  { key: "lihtc", slot: 2, name: "Housing tax credit equity" },
  { key: "historic", slot: 3, name: "Historic tax credits" },
  { key: "grants", slot: 4, name: "Grants and local awards" },
  { key: "nmtc", slot: 5, name: "New Markets Tax Credits" },
  { key: "fee", slot: 6, name: "Deferred developer fee" },
];

function sourceGroup(row) {
  if (row.programId === "lihtc9" || row.programId === "lihtc4") return "lihtc";
  if (row.programId === "htc" || row.programId === "la_historic_credit") return "historic";
  if (row.programId === "nmtc") return "nmtc";
  if (row.editable) return "grants";
  if (row.name.startsWith("Deferred")) return "fee";
  return "loan";
}

function chartParts(s) {
  const sources = SOURCE_GROUPS.map((g) => ({
    ...g,
    name: g.name || (state.lookup.project.tenure === "ownership" ? "Home sale proceeds" : "Permanent loan"),
    amount: s.rows.filter((r) => sourceGroup(r) === g.key).reduce((sum, r) => sum + r.amount, 0),
  })).filter((p) => p.amount > 0.5);
  if (s.gap > 1) sources.push({ key: "gap", name: "Remaining gap", amount: s.gap, gap: true });
  const uses = s.uses.filter((u) => u.amount > 0.5).map((u, i) => ({ ...u, shade: i + 1 }));
  return { sources, uses };
}

function segmentedBar(parts, scale, title, kindClass) {
  const total = parts.reduce((sum, p) => sum + p.amount, 0);
  const blocks = parts.map((p) => {
    const share = total > 0 ? p.amount / total : 0;
    const width = scale > 0 ? (p.amount / scale) * 100 : 0;
    const cls = p.gap ? "seg gap" : kindClass === "uses" ? `seg use-${p.shade}` : `seg src-${p.slot}`;
    const tip = `${p.name}: ${usd(p.amount)} (${pct(share)})`;
    return `<span class="${cls}" style="width:${width}%" tabindex="0" role="img" aria-label="${esc(tip)}" data-tip="${esc(tip)}"><span class="seg-label">${pct(share)}</span></span>`;
  }).join("");
  const legend = parts.map((p) => {
    const cls = p.gap ? "gap" : kindClass === "uses" ? `use-${p.shade}` : `src-${p.slot}`;
    return `<li><span class="swatch ${cls}"></span>${esc(p.name)}</li>`;
  }).join("");
  return `
    <div class="sau-row">
      <div class="sau-head"><span>${esc(title)}</span><span class="sau-total">${usd(total)}</span></div>
      <div class="segbar" role="group" aria-label="${esc(title)}">${blocks}</div>
      <ul class="sau-legend">${legend}</ul>
    </div>`;
}

function sourcesUsesChart(s) {
  const { sources, uses } = chartParts(s);
  const scale = Math.max(sources.reduce((a, p) => a + p.amount, 0), uses.reduce((a, p) => a + p.amount, 0));
  return `
    <figure class="sau">
      ${segmentedBar(sources, scale, "Where the money comes from", "sources")}
      ${segmentedBar(uses, scale, "Where the money goes", "uses")}
      <figcaption>Hover or tab to a block for its amount. The table below lists every source.</figcaption>
    </figure>`;
}

// Percentages only print inside blocks wide enough to hold them; the tooltip and table carry the rest.
function fitSegmentLabels() {
  document.querySelectorAll(".segbar .seg").forEach((seg) => {
    const label = seg.querySelector(".seg-label");
    label.hidden = false;
    label.hidden = label.scrollWidth + 12 > seg.clientWidth;
  });
}

const chartTip = document.createElement("div");
chartTip.className = "chart-tip";
chartTip.hidden = true;
document.body.appendChild(chartTip);

function showTip(seg) {
  chartTip.textContent = seg.dataset.tip;
  chartTip.hidden = false;
  const r = seg.getBoundingClientRect();
  const tipW = chartTip.offsetWidth;
  const left = Math.min(Math.max(8, r.left + r.width / 2 - tipW / 2), window.innerWidth - tipW - 8);
  chartTip.style.left = `${left + window.scrollX}px`;
  chartTip.style.top = `${r.top + window.scrollY - chartTip.offsetHeight - 8}px`;
}
const hideTip = () => { chartTip.hidden = true; };
for (const evt of ["mouseover", "focusin"]) {
  $("#scenarios").addEventListener(evt, (e) => { const seg = e.target.closest(".seg"); if (seg) showTip(seg); });
}
for (const evt of ["mouseout", "focusout"]) {
  $("#scenarios").addEventListener(evt, (e) => { if (e.target.closest(".seg")) hideTip(); });
}
window.addEventListener("resize", fitSegmentLabels);
window.addEventListener("scroll", hideTip, { passive: true }); // scrolling moves blocks out from under the pointer

// ---------- rendering ----------

function scenarioKinds() {
  if (state.lookup.project.tenure === "ownership") return ["none"];
  const kinds = [];
  if (usable("lihtc9")) kinds.push("9");
  if (usable("lihtc4")) kinds.push("4");
  return kinds.length ? kinds : ["none"];
}

function statusNote(row) {
  const p = row.programId && program(row.programId);
  return p && p.status === "check" ? ` <span class="verify">verify eligibility</span>` : "";
}

function renderScenarios() {
  const kinds = scenarioKinds();
  const titles = { 9: "9% LIHTC (competitive)", 4: "4% LIHTC with tax-exempt bonds", none: "Estimate without housing tax credits" };
  $("#scenarios").innerHTML = kinds.map((k, idx) => {
    const s = calcScenario(k);
    const label = kinds.length > 1 ? `Scenario ${"AB"[idx]}: ${titles[k]}` : titles[k];
    return `
      <article class="scenario">
        <h2>${esc(label)}</h2>
        ${sourcesUsesChart(s)}
        <div class="table-scroll"><table>
          <thead><tr><th>Source</th><th class="num">Amount</th><th class="num">Share</th></tr></thead>
          <tbody>
            ${s.rows.map((r) => `
              <tr>
                <td>${esc(r.name)}${statusNote(r)}<small>${esc(r.how)}</small></td>
                <td class="num">${r.editable
                  ? `<input class="amount" type="number" min="0" step="1000" data-id="${esc(r.programId)}" value="${Math.round(r.amount)}" aria-label="${esc(r.name)} amount">`
                  : usd(r.amount)}</td>
                <td class="num">${s.tdc > 0 ? pct(r.amount / s.tdc) : "—"}</td>
              </tr>`).join("")}
          </tbody>
          <tfoot>
            <tr><th>Total sources</th><th class="num">${usd(s.total)}</th><th class="num">${s.tdc > 0 ? pct(s.total / s.tdc) : "—"}</th></tr>
            <tr><th>Total development cost</th><th class="num">${usd(s.tdc)}</th><th></th></tr>
            <tr class="${s.gap > 1 ? "gap" : "surplus"}"><th>${s.gap > 1 ? "Remaining gap" : s.gap < -1 ? "Surplus" : "Fully funded (gap)"}</th><th class="num">${usd(Math.abs(s.gap))}</th><th class="num">${s.tdc > 0 ? pct(Math.abs(s.gap) / s.tdc) : "—"}</th></tr>
          </tfoot>
        </table></div>
      </article>`;
  }).join("");

  renderNotes(kinds);
  hideTip();
  fitSegmentLabels();
}

function renderNotes(kinds) {
  const v = state.values;
  const notes = [];
  if (kinds.includes("9") && kinds.includes("4")) {
    notes.push("9% and 4% housing credits can't be used on the same building, so they're shown as separate scenarios.");
  }
  if (kinds.includes("9")) {
    notes.push("9% credits are competitive, and state agencies cap credits per project; those caps aren't modeled.");
  }
  if (kinds.includes("4")) {
    const tdc = v.units * v.cost_per_unit + v.commercial_cost;
    notes.push(`4% credits need tax-exempt bonds covering at least 25% of eligible basis plus land (the rule for bonds issued after 2025), roughly ${usd(tdc * 0.25)} here. Part of the bonds is often repaid when construction ends.`);
  }
  if (kinds.includes("none") && state.lookup.project.tenure === "ownership") {
    notes.push("This page models rental projects. Homeownership financing (buyer mortgages and down payment help) works differently, so only a simple cost-and-subsidy view is shown.");
  } else if (kinds.includes("none")) {
    notes.push("Housing tax credits aren't counted because they're ruled out by your project answers (they need rental units at 60% AMI or below).");
  }
  if (usable("nmtc") && v.commercial_cost > 0) notes.push("New Markets Tax Credits are counted only for the commercial or community space; they can't finance the tax-credit housing itself.");
  if (usable("htc") || usable("la_historic_credit")) notes.push("Historic credits can be combined with housing credits; how they interact with eligible basis isn't modeled here.");
  if (usable("home")) notes.push("Federal grants can reduce LIHTC eligible basis, so HOME money is usually structured as a loan.");
  notes.push("Programs marked \"verify eligibility\" depend on project answers you left blank or on agency review.");
  notes.push("Only programs that aren't ruled out for this site and project are included.");
  $("#combine-notes").innerHTML = notes.map((n) => `<li>${esc(n)}</li>`).join("");

  const helps = Object.entries(ALSO_HELPS).filter(([id]) => usable(id)).map(([id, text]) => `<li><strong>${esc(program(id).name)}:</strong> ${esc(text)}</li>`);
  $("#also-helps").innerHTML = helps.length ? helps.join("") : "<li>None found for this site and project.</li>";
}

$("#scenarios").addEventListener("input", (e) => {
  if (!e.target.classList.contains("amount")) return;
  const v = parseFloat(e.target.value);
  state.custom[e.target.dataset.id] = Number.isFinite(v) ? Math.max(0, v) : 0;
  // Update totals without re-rendering the box being typed in.
  clearTimeout(state.timer);
  state.timer = setTimeout(() => {
    const focused = document.activeElement?.dataset?.id;
    renderScenarios();
    if (focused) document.querySelector(`#scenarios input[data-id="${focused}"]`)?.focus();
  }, 500);
});

// ---------- pro forma export ----------

const PROFORMA_YEARS = 15; // the LIHTC compliance period

function csvCell(v) {
  if (typeof v === "number") return Number.isFinite(v) ? String(Math.round(v * 100) / 100) : "";
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// Yearly operating cash flow. Rent and expenses grow at their own rates; the loan payment stays flat.
function operatingYears(s) {
  const v = state.values;
  const debtService = s.loan * loanConstant(v.rate, v.amort);
  const years = [];
  for (let y = 1; y <= PROFORMA_YEARS; y++) {
    const gpr = v.units * v.rent * 12 * Math.pow(1 + v.rent_growth / 100, y - 1);
    const vacancy = gpr * (v.vacancy / 100);
    const egi = gpr - vacancy;
    const opex = v.units * v.opex * Math.pow(1 + v.expense_growth / 100, y - 1);
    const noi = egi - opex;
    years.push({ gpr, vacancy, egi, opex, noi, debtService, cashFlow: noi - debtService, dscr: debtService > 0 ? noi / debtService : null });
  }
  return years;
}

function buildProformaCsv() {
  const l = state.lookup;
  const v = state.values;
  const kinds = scenarioKinds();
  const titles = { 9: "9% LIHTC (competitive)", 4: "4% LIHTC with tax-exempt bonds", none: "Without housing tax credits" };
  const scenarios = kinds.map((k) => ({ title: titles[k], s: calcScenario(k) }));
  const rows = [];
  const blank = () => rows.push([]);

  rows.push(["Development pro forma (estimate)"]);
  rows.push(["Site", l.site.matched_address]);
  rows.push(["City", l.city.name]);
  rows.push(["Prepared", new Date().toLocaleDateString()]);
  rows.push(["Disclaimer", "Estimate for learning and early planning only. Not financial, investment, legal or tax advice, and not an offer or commitment of funding. Student prototype. Confirm all figures with funding agencies, a syndicator or lender, an attorney and a CPA."]);
  blank();

  rows.push(["ASSUMPTIONS"]);
  rows.push(["Assumption", "Value", "Recommended for " + l.city.name, "Source / note"]);
  for (const a of ASSUMPTIONS) {
    if (a.show && !a.show(l)) continue;
    const m = market(a.key);
    rows.push([a.label, formatValue(a, v[a.key]), m ? formatValue(a, m.value) : "", m ? `${m.note}${m.url ? " " + m.url : ""}` : (a.help || "")]);
  }
  blank();

  const tdc = scenarios[0].s.tdc;
  rows.push(["USES (where the money goes)"]);
  rows.push(["Use", "Amount", "Share of total", "Per housing unit"]);
  for (const u of scenarios[0].s.uses) {
    if (u.amount <= 0.5) continue;
    rows.push([u.name, u.amount, tdc > 0 ? `${(u.amount / tdc * 100).toFixed(1)}%` : "", v.units > 0 ? u.amount / v.units : ""]);
  }
  rows.push(["Total development cost", tdc, "100%", v.units > 0 ? tdc / v.units : ""]);
  blank();

  for (const { title, s } of scenarios) {
    rows.push([`SOURCES: ${title}`]);
    rows.push(["Source", "Amount", "Share of total cost", "How it was estimated"]);
    for (const r of s.rows) {
      if (r.amount <= 0.5 && r.editable) continue; // skip unentered awards
      rows.push([r.name, r.amount, s.tdc > 0 ? `${(r.amount / s.tdc * 100).toFixed(1)}%` : "", r.how]);
    }
    rows.push(["Total sources", s.total, s.tdc > 0 ? `${(s.total / s.tdc * 100).toFixed(1)}%` : ""]);
    rows.push([s.gap > 1 ? "Remaining gap" : "Gap", Math.max(0, s.gap), s.tdc > 0 ? `${(Math.max(0, s.gap) / s.tdc * 100).toFixed(1)}%` : ""]);
    blank();
  }

  if (l.project.tenure === "ownership") {
    rows.push(["HOMEOWNERSHIP SALES"]);
    rows.push(["Homes", v.units]);
    rows.push(["Affordable sale price per home", v.sale_price]);
    rows.push(["Total sale proceeds", v.units * v.sale_price]);
  } else {
    // The loan is the same in every scenario, so one operating table covers them all.
    const years = operatingYears(scenarios[0].s);
    rows.push([`OPERATING PRO FORMA (${PROFORMA_YEARS} years; loan payment applies to every scenario)`]);
    rows.push(["Line item", ...years.map((_, i) => `Year ${i + 1}`)]);
    const line = (name, key) => rows.push([name, ...years.map((y) => y[key])]);
    line("Gross potential rent", "gpr");
    line("Less vacancy and collection loss", "vacancy");
    line("Effective gross income", "egi");
    line("Operating expenses", "opex");
    line("Net operating income", "noi");
    line("Debt service (permanent loan)", "debtService");
    line("Cash flow after debt service", "cashFlow");
    rows.push(["Debt coverage ratio", ...years.map((y) => (y.dscr == null ? "" : y.dscr.toFixed(2)))]);
    blank();
    rows.push(["Permanent loan amount", scenarios[0].s.loan]);
    rows.push(["Loan terms", `${v.rate}% interest, ${v.amort}-year term, sized at ${v.dscr} debt coverage in year 1`]);
    rows.push(["Growth", `Rent +${v.rent_growth}% per year; operating costs +${v.expense_growth}% per year`]);
  }

  return "﻿" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
}

function downloadProforma() {
  const csv = buildProformaCsv();
  const name = state.lookup.site.matched_address.split(",")[0].toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `proforma-${name || "site"}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

$("#download-proforma").addEventListener("click", downloadProforma);

// ---------- load ----------

async function load() {
  const params = new URLSearchParams(location.search);
  const address = params.get("address");
  $("#back-link").href = "/?" + params.toString();
  if (!address) {
    $("#stack-loading").hidden = true;
    $("#stack-error").textContent = "Look up an address on the main page first, then open the capital stack estimate from there.";
    $("#stack-error").hidden = false;
    return;
  }
  try {
    const res = await fetch("/api/lookup?" + params.toString());
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Lookup failed");
    state.lookup = data;
  } catch (err) {
    $("#stack-loading").hidden = true;
    $("#stack-error").textContent = err.message;
    $("#stack-error").hidden = false;
    return;
  }
  $("#stack-site").textContent = `${state.lookup.site.matched_address} · ${state.lookup.city.name}. Combines the programs this site isn't ruled out for into a rough sources-and-uses estimate.`;
  for (const a of ASSUMPTIONS) state.values[a.key] = defaultFor(a);
  renderAssumptions();
  renderScenarios();
  $("#stack-loading").hidden = true;
  $("#stack").hidden = false;
}

// The chatbot (chat.js, shared with the results page) asks about this page's site and project answers.
window.siteChatContext = () => {
  const params = new URLSearchParams(location.search);
  let project = {};
  try {
    project = JSON.parse(params.get("project") || "{}") || {};
  } catch {
    project = {};
  }
  return {
    page: "stack",
    address: params.get("address") || "",
    project,
    matchedAddress: state.lookup && state.lookup.site.matched_address,
    stackHref: location.href,
  };
};

load();
