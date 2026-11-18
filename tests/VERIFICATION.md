# Verification log

Checks of the calculator, the screening logic and the sources, run on 2026-11-17 (two rounds: the second added the real-deal calibration in section 4 and updated the numbers below). Rerun the scripts after changing `static/stack.js`, `app/project.py`, `app/programs.py` or the city files.

## 1. Calculator and CSV

`tests/check_stack.py` works out three sample projects from textbook formulas. It shares no code with the page.

| | Project A | Project B | Project C |
|---|---|---|---|
| Market | Portland | New Orleans | New Orleans |
| Units | 60 | 40 | 30 |
| Type | New construction rental | Renovation rental, 70% of cost is historic rehab work | New rental at an unrealistic $9,000 rent |
| Credits | 9% and 4% LIHTC | 9% and 4% LIHTC, federal and Louisiana historic credits, QCT/DDA boost | 9% and 4% LIHTC |
| What it tests | Oregon's $2M cap on 9% credits | Historic credit basis reduction, gap sizing | The 60% loan cap |
| Total cost | $34,800,000 | $14,800,000 | $11,100,000 |
| Permanent loan | $6,452,546 | $1,966,017 | $6,660,000 (income alone: $31.9M) |
| 9% LIHTC equity | $16,600,000 (capped from $2,826,630/yr to $2,000,000/yr) | $8,938,623 (cut to the gap) | $4,440,000 (cut to the gap) |
| 4% LIHTC equity | $10,427,124 | $4,870,606 | $3,325,893 |
| Gap after deferred fee, 9% / 4% | $10,077,054 / $16,249,930 | $0 / $3,357,617 | $0 / $581,307 |

The page's displayed estimate and its CSV download were compared line by line with the script for 17 figures per project (51 in all in the second round). These were:

- total cost and NOI;
- the loan and its annual debt service;
- the maximum and actual credit equity for 9% and 4%;
- the deferred fee and the remaining gap;
- the historic credit equity;
- year-1 and year-15 NOI and year-15 cash flow.

**All matched to within $1.** The page's numbers are saved in `page_numbers_2026-11-17.json`; to rerun the comparison:

```bash
python3 tests/check_stack.py tests/page_numbers_2026-11-17.json
```

Napkin checks:

- The loan payment is 7.25% of the loan a year, which is right for 6.5% interest over 35 years.
- In project A, 9% credit equity is 48% of total cost because Oregon's cap binds. The remaining $10 million gap is realistic: the real Portland 9% deals each filled their gaps with about $3–4 million or more of state and city funds (Gordly Burch House: $4,000,000 in state supportive housing funds).

**Bug found and fixed (first round).** The page didn't reduce LIHTC eligible basis by the federal historic credit.

- IRC 50(c) reduces a building's basis by the amount of the rehabilitation credit claimed, so the LIHTC basis drops too.
- In the first round's project B ($16 million), this overstated 4% credit equity by about $970,000.
- The page now subtracts the credit and says so in the formula line.
- The chatbot's description of the method (`STACK_METHOD`) was updated to match.

**Left out on purpose** (see section 4 for what was later compared with real deals):

- the 4% deal's bond test;
- agency limits on developer fees;
- syndicator pricing differences;
- the master-lease historic structure, where the basis cut doesn't apply.

**Worth knowing:** in project B, operating costs grow 3% a year and rents 2%. NOI therefore falls from $171,040 in year 1 to $163,888 in year 15, and debt coverage slips below 1.20. That's the pro forma working as designed, but a developer should notice it.

## 2. Screening, end to end

`tests/test_screening.py` runs through the local server:

```bash
python3 tests/test_screening.py
```

### 1300 Perdido St, New Orleans (tract 22071013400)

- **Downtown Development District:** La. R.S. 33:2740.3 bounds the district by the Pontchartrain Expressway, the lake side of Claiborne Avenue, Iberville Street and the river. 1300 Perdido is inside. (https://legis.la.gov/Legis/Law.aspx?d=89989)
- **Opportunity Zone:** the tract appears in the CDFI Fund's official list of designated Qualified Opportunity Zones (designated-qozs.12.14.18.xlsx).
- **Input changed:** "commercial space" from no to yes.
  - NMTC went from **Not eligible** (reason: needs a commercial or community-facility part) to **Matches key requirements**.
  - The location result stayed the same.

### 4805 N Williams Ave, Portland (tract 41051003401)

- **Interstate Corridor TIF district:** the site's point is inside the district boundary in Prosper Portland's own map (its Google My Maps file, linked from prosperportland.us/our-work/interstate-corridor/).
- **Other districts:** PortlandMaps shows the nearest parcel, 4835 N Williams Ave, in the Humboldt neighborhood with no plan, historic or National Register district. This matches the site.
- **The address itself:** 4805 isn't an actual parcel in PortlandMaps. The geocoder places it on the street between real addresses, which is fine for a district test.
- **Not an Opportunity Zone:** confirmed, since the tract isn't on the CDFI Fund list.
- **Input changed:** units from 19 to 20.
  - MULTE went from **Not eligible** (reason: tied to Inclusionary Housing, 20+ units) to **Matches key requirements**.

**Found and fixed:** Prosper Portland lists the Interstate Corridor district as **sunsetting**, meaning "no additional funds will be flowing to the district". The district chip and the TIF program now say so and cite that page.

## 3. Evidence quality

### Rule changes now cite the law

Each recent change now cites Public Law 119-21 (July 4, 2025) through the amended Internal Revenue Code section (Cornell LII, all checked to return 200):

- **9% LIHTC +12%:** section 70422, IRC 42(h)(3)(I). Before, this was cited only to an IRS guide written before the change.
- **4% bond test 50% → 25%:** section 70422, IRC 42(h)(4)(B). The wording is now exact: 25% applies when at least one bond issue dated after 2025 finances at least 5% of basis plus land.
- **NMTC permanent, $5 billion a year:** section 70423, IRC 45D(f).
- **Opportunity Zones permanent, rezoned 2027:** section 70421, IRC 1400Z-1 and 1400Z-2.

### Assumption labels

Every assumption on the capital stack page, and in the CSV's new "Evidence" column, is labeled:

- **Published figure:** a city market number with a cited published source, used unchanged.
- **Estimate:** the site's own rough default, such as New Orleans operating cost, Portland's DSCR, land share and vacancy.
- **Your number:** typed by the user, or the unit count from the project form.

## 4. Second round: edge cases and calibration against real deals

### Edge cases

These were run on the page and found no blank values, errors, or broken CSV:

- zero units;
- 0% interest;
- 0 coverage ratio;
- 0-year term;
- negative operating income;
- 40% affordable;
- a $10 billion project;
- homeownership;
- 100% historic rehab;
- commercial space.

Two results were unrealistic and are fixed:

- **No loan limit.** A $9,000 rent sized a $63 million loan on a $24 million project, with a negative gap. Loans are now capped at 60% of total cost, editable as "Largest permanent loan as a share of total cost".
- **No per-project credit cap.** Each state caps 9% credits per project. The page now applies the cap:

| State | Cap per year | Source |
|---|---|---|
| Louisiana (8 metro parishes, including Orleans) | $1,500,000 | LHC 2025 QAP; 8 of 45 2025 awards hit it |
| Oregon | $2,000,000 | OHCS 9% guidance; Torchwood South hit it |
| Elsewhere (general default) | $1,500,000 | estimate |

### Real deals

`tests/check_real_deals.py` compares the formula with 13 awards. Each award's total cost and annual credits are published:

- Oregon (Housing Stability Council packets, Aug–Nov 2026): Gordly Burch House, Garfield Commons, Flatworks;
- Louisiana (LHC 2025 rankings): Blueberry Hill 2 (Orleans), Marrero Village (Jefferson) and 8 other new construction awards.

The finding:

- **Real basis:** these deals carried eligible basis of 84–92% of total cost, median 90%.
- **Old defaults:** land 8% and 85% of the rest gave 78%, under-sizing tax credit equity by about 13%.
- **New defaults:** land 5% and 95% of the rest give 90%.

### Market numbers updated from agency underwriting rules and recent awards

| | Before | Now | Source |
|---|---|---|---|
| Portland cost per unit | $400,000 | $580,000 | four 2026 awards, $543,592–$604,949 per unit |
| New Orleans cost per unit | $400,000 | $370,000 | four recent awards, $321,809–$394,000 per unit |
| Portland debt coverage | estimate | published: 1.15–1.30 | OHCS General Policy and Guideline Manual, July 2026 |
| Portland operating cost | — | $6,500–$8,500 range noted | OHCS manual, July 2026 |
| Vacancy | 7% (estimate) | 7% (published) | LHC: greater of 7% or market study; OHCS: 5–7% |
| Rent / expense growth | 2% / 3% (estimate) | 2% / 3% (published) | required by both agencies |

### Still not checked

- **Full sources and uses:** none of the published award memos gave the permanent loan amount or rate, so the loan sizing and the final gap haven't been compared with a real deal.
- **Deferred fee caps:** Louisiana's $2,000,000 fee cap for 9% deals and Oregon's fee tables (12–22% depending on size and credit type) aren't modeled; the page uses a 12% fee.
- **The 4% bond test** isn't modeled.
- **Louisiana's disaster-area boost:** LHC grants the 30% boost to 9% projects in federally declared disaster areas, and the 2025 New Orleans-area awards were sized as if boosted. The page applies the boost only when the site is in a QCT or DDA, or when you check the box.

## 5. Land and building purchase prices (2026-11-18)

The page now accepts a land purchase price and, for renovations, an existing building purchase price, in place of the land percentage. Both are part of total cost, not added to it.

- The building purchase is basis of its own: acquisition credits use the 4% rate and never get the 130% QCT/DDA boost, which covers only new buildings and rehab spending (IRC 42(b), 42(d)(5)(B)). Acquisition credits need the building to have last been placed in service at least 10 years earlier (IRC 42(d)(2)); the page says so but doesn't check it.
- Historic rehab costs can't exceed total cost minus the purchase prices.
- `tests/check_stack.py` adds project D (Portland renovation, 50 units at $450,000, QCT, $1.2 million land, $6 million building). The page matches on all 9 figures compared (`tests/page_numbers_2026-11-18.json`): 9% equity $16,106,938 from $14,535,000 of rehab basis × 130% × 9% plus $6,000,000 × 4%.
- Projects A-C are unchanged when no purchase prices are entered.
- A note warns when the purchase prices leave little or nothing for construction.
