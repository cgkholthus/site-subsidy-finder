# Site Subsidy Finder

Enter a development site address in **New Orleans, LA** or **Portland, OR**. You get back the affordable housing tax credits, grants, loans, fee waivers and zoning requirements that apply there, sorted into federal, state, county/city and neighborhood levels.

There is no per-search cost: programs come from a researched database, and only free public map data is checked live.

## How it works

| What | Source |
|---|---|
| Site facts | Census Geocoder: city, county, census tract |
| Federal designations | HUD maps: 2026 Qualified Census Tracts, Difficult Development Areas, Opportunity Zones, Promise Zones |
| Local districts | City GIS layers, checked live for the address (TIF districts, historic districts, inclusionary zoning, cultural and downtown districts, plan districts, neighborhoods) |
| Federal programs | `app/programs.py`, each checked against the site's designations |
| State, county, city and neighborhood programs | `data/cities/new_orleans.json` and `data/cities/portland.json` |
| Market context | HUD Fair Market Rents, plus existing LIHTC properties within 1 mile |

## Run it

```bash
./run.sh
```

Then open http://localhost:8000. Only Python 3 is needed; there are no packages to install.

Optional settings go in a `.env` file (see `.env.example`):

- `GEMINI_API_KEY`: turns on the chatbot (Google Gemini; the free tier is enough).
- `CENSUS_API_KEY`: shows the tract poverty rate for New Markets Tax Credit screening.

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

- `app/server.py`: HTTP server (Python standard library), `/api/lookup` and `/api/chat`
- `app/chat.py`: chatbot prompt, Gemini call, and the code-level rule checks
- `app/geo.py`: Census, HUD and city map lookups
- `app/cities.py`: loads the city databases and decides which programs apply
- `app/programs.py`: federal program rules
- `data/cities/`: the New Orleans and Portland program databases
- `static/`: front end (plain HTML/CSS/JS with a Leaflet map)
