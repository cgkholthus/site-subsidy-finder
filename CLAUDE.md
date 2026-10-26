# CLAUDE.md

Site Subsidy Finder: a small website where an affordable housing developer enters a site address in **New Orleans, LA** or **Portland, OR** and sees the federal, state, county/city and neighborhood programs (tax credits, grants, loans, fee waivers, zoning requirements) that apply there.

## Running it

```bash
python3 app/server.py
```

Serves http://localhost:8000. Python 3.9+ standard library only; there are no packages to install (`.venv/` is a leftover and isn't needed).

- The project folder name ends in a trailing space (`Develop Affordable `). Quote paths.
- The desktop app's preview launcher (`preview_start` with `.claude/launch.json`) can't read the Downloads folder (macOS permission). Start the server with Bash in the background, then open `http://localhost:8000` in the browser pane by URL.
- Public hosting: `render.yaml` (Render free web service). The server binds `HOST` (default 127.0.0.1; Render uses 0.0.0.0) and rate-limits `/api/lookup` and `/api/chat` per visitor (`RATE_LIMITS` in `server.py`). `public-upload/` is a generated, secret-free copy for drag-and-drop upload to GitHub; rebuild it after changes and scan it for keys before uploading.
- After changing Python files, restart the server (`pkill -f app/server.py`, then start it again). Static files don't need a restart.

## Design decisions

- **No AI or paid API calls per search.** Live AI research (Claude, then Gemini) was tried and removed because it cost several dollars per address. Programs come from a researched database; only free public map services are queried live. Don't reintroduce per-search paid calls without the user asking.
- **Chatbot (`app/chat.py`, `/api/chat`)** answers only from the database and the current site lookup, using Gemini over plain HTTP (no SDK) on the free tier: `gemini-flash-lite-latest`, falling back to `gemini-flash-latest` on 429/503. No web search: Google refuses search grounding on this account's free tier. The user's required rules: cite a source for every fact, say "I don't know" when unsure, no legal or tax advice, disclose it's a student prototype. (The user later dropped a fifth rule, offering a human contact; don't add it back unless asked.) Keep the code-level checks in `_enforce_rules` (uncited answers become "I don't know") and the disclosure in `static/index.html`. Retest all four rules after any prompt or model change.
- Supported cities are chosen by Census place GEOID (`place_geoid` in each city file). Other addresses get a clear "this tool covers ..." error.

## Layout

- `app/server.py`: HTTP server, `/api/lookup?address=...`, `/api/chat` (POST) and `/api/status`. Loads `.env` (`GEMINI_API_KEY` for the chatbot, optional `CENSUS_API_KEY`). Caches lookups in memory.
- `app/chat.py`: chatbot sources, system prompt, Gemini call and rule enforcement.
- `app/geo.py`: Census geocoder, HUD ArcGIS layers (QCT, DDA, Opportunity Zones, Promise Zones, Fair Market Rents, LIHTC properties), and point-in-polygon queries against each city's district layers.
- `app/cities.py`: loads `data/cities/*.json`, evaluates each program's `area` rule, builds district labels.
- `app/programs.py`: curated federal programs with per-site tests; `match()` groups everything into `federal`, `state`, `local` (county + city), `neighborhood`.
- `data/cities/new_orleans.json`, `data/cities/portland.json`: the program databases.
- `static/`: plain HTML/CSS/JS front end with a Leaflet map (from cdnjs). No build step.

## City database format

Each city file has `name`, `place_geoid`, `last_reviewed`, `local_context`, `districts` (ArcGIS layer URL, name field, label, optional `display` template and `ignore` list) and `programs`.

Program fields: `id`, `name`, `level` (`state` | `county` | `city` | `neighborhood`), `type`, `agency`, `summary`, `amount`, `eligibility`, `deadline`, `url`, `area`, and optional `kind: "requirement"` (shown as "Applies here") or `status` (overrides the default "check" for citywide programs).

`area` rules: `null` (citywide), `{"district": key}`, `{"district": key, "name_contains": [...]}`, `{"flag": "opportunity_zone"}`, `{"any": [...]}`, plus optional `outside_status` / `outside_note`.

When updating the database:
- Research from official sources (city, state agency, HFA pages) and don't invent amounts, deadlines or URLs. If something can't be confirmed, say so in the entry.
- Check every changed `url` returns 200 (some government sites block curl's default user agent; use a browser user agent).
- Bump `last_reviewed`.
- Verify with test addresses: `1300 Perdido St, New Orleans, LA 70112` (CBD: inclusionary Core sub-district, Downtown Development District, Opportunity Zone), `801 Chartres St, New Orleans, LA 70116` (French Quarter historic districts), `920 SW 3rd Ave, Portland, OR 97204` (Westside TIF, Central City), `4805 N Williams Ave, Portland, OR 97217` (Interstate Corridor / N/NE Preference Policy).

## Working with the user

- The user is not a programmer. Explain things in plain language and avoid jargon.
- They are cost-sensitive: say up front when something will cost money (API usage, paid services).
- Never ask them to paste API keys or passwords into chat; have them put secrets in `.env` themselves.
