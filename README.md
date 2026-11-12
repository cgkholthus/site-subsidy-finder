# Site Subsidy Finder

Enter a development site address in **New Orleans, LA** or **Portland, OR**. You get back the affordable housing tax credits, grants, loans, fee waivers and zoning requirements that apply there, sorted into federal, state, county/city and neighborhood levels.

There is no per-search cost: programs come from a researched database, and only free public map data is checked live.

## How it works

| What | Source |
|---|---|
| Site facts | Census Geocoder: city, county, census tract |
| Federal designations | HUD maps: 2026 Qualified Census Tracts, Difficult Development Areas, Opportunity Zones, Promise Zones |
| Individually listed historic buildings | National Park Service National Register points, matched to the site by street address |
| Local districts | City GIS layers, checked live for the address (TIF districts, historic districts, inclusionary zoning, cultural and downtown districts, plan districts, neighborhoods) |
| Federal programs | `app/programs.py`, each checked against the site's designations |
| NMTC eligibility | `data/nmtc_tracts.json`: Louisiana and Oregon tracts from the CDFI Fund's official 2016-2020 ACS eligibility file (September 2026 release) |
| State, county, city and neighborhood programs | `data/cities/new_orleans.json` and `data/cities/portland.json` |
| Market context | HUD Fair Market Rents, plus existing LIHTC properties within 1 mile |

## Run it

```bash
./run.sh
```

Then open http://localhost:8000. Only Python 3 is needed; there are no packages to install.

Optional: put `GEMINI_API_KEY` in a `.env` file (see `.env.example`) to turn on the chatbot (Google Gemini; the free tier is enough).

## Project details form

"About your project" asks seven optional questions: rental or ownership, new or rehab, units, highest income limit, owner type, commercial space, and special populations. Each program can list `project_rules`; the site combines them with the location checks:

- **Potentially relevant**: the location fits (or the program has no location test). **Matches key requirements**: the location fits and every project rule passes with your answers.
- **Not eligible here / Doesn't apply here**: the location or any answer rules it out; the card says why.
- **Check requirements**: an answer the program depends on is blank, or the program needs something the form doesn't ask (`best_status: "check"`).

Answers are kept in the page link, so a shared link shows the same results. Programs with no open funding round carry a `funding` note shown as a label.

## Zone explanations

Every zone chip on the site summary (Opportunity Zone, QCT, BioDistrict, TIF districts and so on) is clickable. It opens a plain-language explanation, what it means for a project, and a source link. Federal zone text lives in `FEDERAL_ZONES` in `app/programs.py`; city district text lives in each city file's `districts` entries (`about`, plus optional `names` for specific districts and `patterns` for name matches).

## Address autocomplete

Typing a house number and street shows suggestions from each city's official address records: New Orleans' Site Address Point layer and Portland's address geocoding service (filtered to Portland). The `/api/suggest` endpoint queries both and is rate-limited per visitor.

## Capital stack estimate

`stack.html` ("Estimate a capital stack for this site" on the results page) combines the programs not ruled out for the site and project into a rough sources-and-uses estimate. It's clearly labeled as an estimate for learning and planning, not financial, legal or tax advice.

- A permanent loan is sized from rents and operating costs (home sale proceeds for homeownership projects).
- LIHTC equity comes from eligible basis, with the 130% boost in a QCT or DDA. It's capped at the remaining gap, because agencies only award the credits a project needs (IRC 42(m)(2)).
- Historic credits use renovation costs; NMTC applies only to commercial space; FHLBank AHP uses an assumed typical award.
- Programs without a predictable amount (city NOFAs, HOME, CDBG and others) start at $0 with a box to enter an expected award.
- 9% and 4% credits can't be combined, so both appear as separate scenarios when both are possible.
- Tax abatements, fee waivers and rent subsidies are listed as "also helps" rather than counted.

The page starts with a few quick inputs (units, cost per unit, rent, operating cost, plus commercial or renovation cost when the project has them) that accept rough entries like `400k`, `1.2m` or `$1,100`. The rest sit under "More assumptions". Defaults come from each city file's `market` section: researched, sourced recommendations for cost per unit, 60% AMI rent (from HUD's FY2026 MTSP limits), operating cost, debt coverage and LIHTC pricing. All calculations run in the browser (`static/stack.js`).

"Download pro forma (CSV)" exports a spreadsheet-ready file: the disclaimer, every assumption (with the recommended value and source), uses with per-unit amounts, sources for each scenario with how each was estimated, and a 15-year operating cash flow (rent, vacancy, operating costs, net operating income, debt service, cash flow and debt coverage, with rent and expense growth from "More assumptions").

Each scenario shows two bars at the same scale: "Where the money comes from" (sources grouped into up to six blocks, plus a hatched "Remaining gap" block) and "Where the money goes" (land, construction, soft costs, developer fee, commercial space). Hovering or tabbing to a block shows its amount and share. Colors come from a palette validated for colorblind safety in light and dark mode.

## Deploying to a public link (Render)

`render.yaml` sets up a free Render web service. Render sets `PORT`; the file sets `HOST=0.0.0.0`. Add `GEMINI_API_KEY` in the Render dashboard (never commit `.env`). The server limits each visitor to 20 lookups a minute (300 a day) and 6 chat questions a minute (60 a day) so the free Gemini quota can't be drained. Free Render services sleep after about 15 minutes without visitors, so the first visit after a quiet spell takes up to a minute to load.

## Chatbot

The "Ask a question" button opens an assistant that answers questions about the program database and the site you looked up. It follows these rules:

1. **Cites a source for every fact.** Answers carry numbered links to the program pages and map data they came from. The server drops any answer without a valid citation and replaces it with "I don't know".
2. **Says "I don't know" when unsure.** It only answers from this site's data, not general knowledge.
3. **No legal or tax advice.** It describes programs but refers advice questions to an attorney or tax professional.
4. **Discloses that it is a student prototype**, in the chat panel and its first message.

It uses `gemini-flash-lite-latest`, falling back to `gemini-flash-latest` when busy (override with `GEMINI_CHAT_MODELS`). Each question sends the relevant database entries to Google; on the free tier that costs nothing, but Google may use free-tier conversations to improve its products.

## Updating the program database

Each city file lists its programs, the date it was last reviewed (`last_reviewed`), and the map layers used for district checks. To update a program, edit its entry and bump `last_reviewed`.

A program's `area` rule decides where it applies:

- `null`: applies citywide (shown as "Check eligibility", or set `"status": "eligible"`)
- `{"district": "tif"}`: only inside a district from that city's `districts` layers
- `{"district": "tif", "name_contains": ["Interstate Corridor"]}`: only inside specific named districts
- `{"flag": "opportunity_zone"}`: only in an Opportunity Zone
- `{"any": [...]}`: any of several rules; add `"outside_status": "check"` and `"outside_note"` when sites outside can still qualify

Set `"kind": "requirement"` for obligations such as inclusionary zoning or historic design review, so they show as "Applies here" rather than as funding.

To add a city, copy one of the JSON files, set `place_geoid` to the city's Census place GEOID, and point `districts` at that city's ArcGIS layers.

## Files

- `app/server.py`: HTTP server (Python standard library), `/api/lookup`, `/api/suggest` and `/api/chat`
- `app/chat.py`: chatbot prompt, Gemini call, and the code-level rule checks
- `app/project.py`: project form parsing and the rule engine
- `app/geo.py`: Census, HUD and city map lookups
- `app/cities.py`: loads the city databases and decides which programs apply
- `app/programs.py`: federal program rules
- `data/cities/`: the New Orleans and Portland program databases
- `data/nmtc_tracts.json`: NMTC Low-Income Community tracts for Louisiana and Oregon
- `static/`: front end (plain HTML/CSS/JS with a Leaflet map); `stack.html` and `stack.js` are the capital stack estimate page
