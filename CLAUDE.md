# CLAUDE.md

Site Subsidy Finder: a small website where an affordable housing developer enters a site address in **New Orleans, LA** or **Portland, OR** and sees the federal, state, county/city and neighborhood programs (tax credits, grants, loans, fee waivers, zoning requirements) that apply there.

## Running it

```bash
python3 app/server.py
```

Serves http://localhost:8000. Python 3.9+ standard library only; there are no packages to install (`.venv/` is a leftover and isn't needed).

- The project folder name ends in a trailing space (`Develop Affordable `). Quote paths.
- The desktop app's preview launcher (`preview_start` with `.claude/launch.json`) can't read the Downloads folder (macOS permission). Start the server with Bash in the background, then open `http://localhost:8000` in the browser pane by URL.
- Live site: https://site-subsidy-finder.onrender.com (Render service `srv-dbfcviu7bikc73d274ag`, deployed from the public GitHub repo `cgkholthus/site-subsidy-finder` via its public URL, so pushes do NOT auto-deploy; use Manual Deploy in the Render dashboard). The GitHub repo was filled by drag-and-drop upload of `public-upload/`; the local folder is not a git checkout.
- Public hosting: `render.yaml` (Render free web service). The server binds `HOST` (default 127.0.0.1; Render uses 0.0.0.0) and rate-limits `/api/lookup` and `/api/chat` per visitor (`RATE_LIMITS` in `server.py`). `public-upload/` is a generated, secret-free copy for drag-and-drop upload to GitHub; rebuild it after changes and scan it for keys before uploading.
- After changing Python files, restart the server (`pkill -f app/server.py`, then start it again). Static files don't need a restart.

## Design decisions

- **No AI or paid API calls per search.** Live AI research (Claude, then Gemini) was tried and removed because it cost several dollars per address. Programs come from a researched database; only free public map services are queried live. Don't reintroduce per-search paid calls without the user asking.
- **Chatbot (`app/chat.py`, `/api/chat`)** answers only from the database and the current site lookup, using Gemini over plain HTTP (no SDK) on the free tier: `gemini-flash-lite-latest`, falling back to `gemini-flash-latest` on 429/503. No web search: Google refuses search grounding on this account's free tier. The user's required rules: cite a source for every fact, say "I don't know" when unsure, no legal or tax advice, disclose it's a student prototype. (The user later dropped a fifth rule, offering a human contact; don't add it back unless asked.) Keep the code-level checks in `_enforce_rules` (uncited answers become "I don't know") and the disclosure in `static/index.html`. Rules added after the October 2026 review:
  - **General information is not advice.** Explaining what a program is, its benefits and requirements is allowed. Recommending tax positions, investment decisions or deal structures for the user's situation is declined. `GENERAL_QUESTION` / `PERSONAL_ADVICE` in `chat.py` retry once if a general question was wrongly declined.
  - **Every answer carries essential conditions.** The model often shortens answers, so `ask()` also returns `requirements`: the database's own `eligibility` and `limits` for each cited program, shown in a "Key requirements" box. Don't rely on the prompt alone for this.
  - **Agency contacts and "last verified".** `ask()` returns `contacts` and `last_verified` for cited sources; the UI shows them under each answer.
  - **Wording.** Address results are "potentially relevant programs". Location alone never establishes eligibility.

  Retest all the rules after any prompt or model change.
- **Capital stack page (`static/stack.html`, `static/stack.js`)** is an estimate for learning and planning, never advice: keep the disclaimer box at the top and the line at the bottom. Programs without a predictable amount start at $0 (user enters awards), so the estimate never invents funding. LIHTC equity is capped at the remaining gap (IRC 42(m)(2)); 9% and 4% are separate scenarios. All math is client-side, with every assumption editable. Defaults come from the city file's `market` section (`{key: {value, note, url}}` for cost_per_unit, rent, opex, dscr, lihtc_price, plus `as_of`), shown as "Recommended for <city>" with its source. Refresh these yearly: rents from HUD's MTSP query tool at huduser.gov/datasets/il/il2026/mtsp (it blocks command-line fetches; use the browser pane), and credit pricing from current Novogradac reports. Inputs accept rough entries (`400k`, `1.2m`).
- Supported cities are chosen by Census place GEOID (`place_geoid` in each city file). Other addresses get a clear "this tool covers ..." error.

## Layout

- `app/server.py`: HTTP server, `/api/lookup?address=...`, `/api/suggest?q=...` (address autocomplete), `/api/chat` (POST) and `/api/status`. The lookup response includes `zones`: clickable chips with explanation text. Loads `.env` (`GEMINI_API_KEY` for the chatbot). Caches map lookups per address in memory; programs are re-evaluated per request because they depend on the project answers (`project` query param / chat body field). Only new addresses count toward the lookup rate limit.
- `app/chat.py`: chatbot sources, system prompt, Gemini call and rule enforcement. The chatbot calls location matches "potentially relevant" and never says a project "is eligible".
- `app/project.py`: "About your project" form parsing (`parse`), rule checks and `combine()`, which merges a location result (`yes`/`no`/`maybe`/`na`) with project rules into the final status.
- `app/geo.py`: Census geocoder, HUD ArcGIS layers (QCT, DDA, Opportunity Zones, Promise Zones, Fair Market Rents, LIHTC properties), point-in-polygon queries against each city's district layers, `_nrhp_listings()` for individually listed National Register buildings (NPS `nrhp_locations` points; their coordinates are approximate, so a listing only counts when its street address matches the site's, sets `flags.nr_listed` and `nr_listings`; NPS polygons are unreliable bounding boxes and aren't used), and `suggest()` for autocomplete (New Orleans Site Address Point layer, Portland's Address_Geocoding_PDX suggest service filtered to Portland). Suggestions need a house number first, and input is sanitized before going into map queries.
- `app/cities.py`: loads `data/cities/*.json`, evaluates each program's `area` rule, builds district labels.
- `app/programs.py`: curated federal programs; each `test(ctx)` returns a location result and note, plus `project_rules`. `match(lookup, project)` groups everything into `federal`, `state`, `local` (county + city), `neighborhood`.
- `data/nmtc_tracts.json`: LA and OR tracts from the CDFI Fund's official NMTC eligibility file (`NMTC_LIC_Eligibility_Dataset_9_3_2026.xlsx`, cdfifund.gov geographic reports page); also supplies the tract poverty rate shown on the site. Regenerate when the CDFI Fund publishes a new file.
- `data/cities/new_orleans.json`, `data/cities/portland.json`: the program databases.
- `static/`: plain HTML/CSS/JS front end with a Leaflet map (from cdnjs). No build step.

## City database format

Each city file has `name`, `place_geoid`, `last_reviewed`, `local_context`, `districts` (ArcGIS layer URL, name field, label, optional `display` template and `ignore` list; zone-chip explanations in `about`, with optional `names` for specific districts and `patterns` for name matches, each `{title, text, meaning, url}`), `programs`, `federal_facts` (researched per-city location results for federal programs, e.g. HOME/CDBG direct grantee) and `national_register_districts` (which district keys count as National Register for the federal historic credit). Also `state_name`, `agencies` (`{id: {name, phone, email, url}}`, verified contact details) and `federal_contacts` (`{federal program id: [agency ids]}`).

Program fields: `id`, `name`, `level` (`state` | `county` | `city` | `neighborhood`), `type`, `agency`, `summary`, `amount`, `eligibility`, `deadline`, `url`, `area`, `project_rules` (see `app/project.py`), `contact` (an `agencies` id), optional `limits` (statewide caps, per-taxpayer limits; shown as "Caps and limits"), optional `references` (`[{title, url}]` for extra sources), and optional `kind: "requirement"` (shown as "Applies here"), `status: "eligible"` (citywide program that every site meets), `best_status: "check"` (needs something the form can't capture) and `funding: {status: closed|paused|limited, note}`. Every program needs project rules or an area rule, or it can never leave "Check eligibility".

`area` rules: `null` (citywide), `{"district": key}`, `{"district": key, "name_contains": [...]}`, `{"flag": "opportunity_zone"}`, `{"any": [...]}`, plus optional `outside_status` / `outside_note`.

When updating the database:
- Research from official sources (city, state agency, HFA pages) and don't invent amounts, deadlines or URLs. If something can't be confirmed, say so in the entry.
- Check every changed `url` returns 200 (some government sites block curl's default user agent; use a browser user agent).
- Bump `last_reviewed`.
- Verify with test addresses: `1300 Perdido St, New Orleans, LA 70112` (CBD: inclusionary Core sub-district, Downtown Development District, Opportunity Zone), `801 Chartres St, New Orleans, LA 70116` (French Quarter historic districts), `920 SW 3rd Ave, Portland, OR 97204` (Westside TIF, Central City), `4805 N Williams Ave, Portland, OR 97217` (Interstate Corridor / N/NE Preference Policy).

## Status labels (what a result means)

- **Potentially relevant** (`eligible`, `project_checked` false): the site's location fits. This says nothing about the project yet.
- **Matches key requirements** (`eligible`, `project_checked` true): the location fits and the user's project answers pass the program's published rules.
- **Check requirements** (`check`): something the rule needs is blank or can't be captured by the form.
- **Not eligible here / Doesn't apply here**: the location or an answer rules it out; the card says why.
- **Applies here** (`applies`): a requirement such as inclusionary zoning, not funding.

The administering agency always makes the final decision; cards and chat answers name its contact.

## Program primer (for answers, docs and tests)

Facts below match the database as of 2026-11-11; the database is the source of truth.

| Program | What it does | Essential conditions | Source |
|---|---|---|---|
| 9% LIHTC | Federal tax credit worth about 70% of the present value of eligible costs over 10 years; competitive. Allocations up 12% from 2026. | Rental only; 20/50, 40/60 or income-averaging set-aside; rents capped at 30% of the income limit; 15-year compliance plus extended use (30 years total); awarded under the state QAP. | [IRS LIHTC Audit Technique Guide](https://www.irs.gov/pub/irs-utl/IRC42%20Low%20Income%20Housing%20Credit%20ATG%20Part%201.pdf) |
| 4% LIHTC | About 30% of present value; non-competitive when financed with tax-exempt bonds. | Same set-asides; bonds must finance 25% of basis plus land for bonds issued after 2025 (50% before). | [IRS ATG](https://www.irs.gov/pub/irs-utl/IRC42%20Low%20Income%20Housing%20Credit%20ATG%20Part%201.pdf), [2025 law summary](https://www.williamsmullen.com/insights/news/legal-news/low-income-housing-tax-credit-reform-one-big-beautiful-bill-acts-effect) |
| New Markets Tax Credit | 39% credit over 7 years on investments in low-income communities; permanent, $5B a year. | Low-Income Community tract (poverty 20%+ or income 80% or less of median); through a CDE with an allocation; residential rental generally doesn't qualify alone. | [CDFI Fund](https://www.cdfifund.gov/programs-training/programs/new-markets-tax-credit) |
| Opportunity Zones | Investor tax deferral and exclusion for capital gains put into a Qualified Opportunity Fund; permanent, rezoned January 1, 2027. | Benefits go to the investor, not the developer; property in a zone; existing buildings must be substantially improved. | [IRS](https://www.irs.gov/credits-deductions/businesses/opportunity-zones) |
| Federal historic credit | 20% of qualified rehab costs for income-producing certified historic buildings. | Individually listed or contributing; Secretary of the Interior's Standards; substantial rehab; apply via SHPO and NPS. | [NPS](https://www.nps.gov/subjects/taxincentives/index.htm) |
| HOME | Gap financing for rental or ownership housing. | Households at or below 80% AMI; affordability period; apply to the participating jurisdiction. | [HUD Exchange](https://www.hudexchange.info/programs/home/) |
| Louisiana historic credit | 25% of eligible rehab costs (35% rural, which excludes New Orleans); stacks with the federal credit. | National Register, Downtown Development District or cultural district; costs by December 31, 2028; $85M statewide yearly cap; $5M per taxpayer per district per year. | [LA Division of Historic Preservation](https://www.crt.louisiana.gov/cultural-development/historic-preservation/tax-incentives/) |
| Portland MULTE | 10-year property tax exemption on residential improvements. | 20+ units; must meet Inclusionary Housing (60% or 80% AMI units, 99 years); apply before the building permit is issued; yearly City cap. | [Portland Housing Bureau](https://www.portland.gov/phb/multe) |

## Education outline (organized around developers' questions)

1. **What could help at this address?** Zone chips (QCT, DDA, Opportunity Zone, historic and TIF districts) and the "Potentially relevant programs" list.
2. **Does my project actually qualify?** The "About your project" form, the status labels above and each card's Eligibility and Caps and limits lines.
3. **How much might it be worth?** The capital stack estimate: LIHTC equity capped at the gap, 9% and 4% as separate scenarios, awards entered by the user.
4. **What can stack together?** For example federal plus Louisiana historic credits plus LIHTC; NMTC only for the commercial or community part.
5. **Who decides, and when?** Agency contacts, deadlines, funding status labels and "last verified" dates.
6. **What can't this tool tell me?** No legal or tax advice, no deal structuring, and no award guarantees.

## Worked example: location vs. project

`1300 Perdido St, New Orleans, LA 70112`, looked up on 2026-11-11:

- **With no project answers**:
  - NMTC is **Potentially relevant**, since the tract poverty rate is 30.7%.
  - Opportunity Zone is **Potentially relevant**, since the site is in a designated zone.
  - 9% and 4% LIHTC are **Check requirements**, since the rental and income answers are blank.
  - The federal historic credit is **Check requirements**, since the site is not in a National Register district.
- **With answers** (60 new-construction rental units, at most 60% AMI, housing only):
  - LIHTC becomes **Matches key requirements**.
  - NMTC becomes **Not eligible here**: the location still fits, but a housing-only project doesn't meet its rules.
  - The historic credit becomes **Not eligible here**, because it needs an existing building to renovate.
  - The Opportunity Zone stays **Potentially relevant**. Its benefit goes to investors, so the form can't confirm it.

The location answers "could this apply here?"; the project answers "does this project meet the rules?". Neither is an award.

## Working with the user

- The user is not a programmer. Explain things in plain language and avoid jargon.
- They are cost-sensitive: say up front when something will cost money (API usage, paid services).
- Never ask them to paste API keys or passwords into chat; have them put secrets in `.env` themselves.
