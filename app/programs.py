"""Curated federal programs matched against a site and project; city programs come from cities.py.

Federal rules reflect the July 2025 reconciliation law (OBBBA): 12% permanent boost to 9% LIHTC
allocations, 25% bond test for 4% deals on bonds issued after 2025, permanent NMTC, and a
permanent Opportunity Zone program with a new round of designations starting in 2027.
Program rules change; every entry links to its source so users can verify.
"""

import json
from pathlib import Path

import cities
import project as proj

FEDERAL_LAST_REVIEWED = "2026-11-11"  # bump when the federal program entries below are re-checked
STATUS_ORDER = {"eligible": 0, "applies": 1, "check": 2, "ineligible": 3, "not_applicable": 4}

# CDFI Fund NMTC Low-Income Community eligibility (2016-2020 ACS), Louisiana and Oregon tracts only.
# Source: cdfifund.gov "NMTC_LIC_Eligibility_Dataset_9_3_2026.xlsx".
NMTC_TRACTS = json.loads((Path(__file__).resolve().parent.parent / "data" / "nmtc_tracts.json").read_text())

# Each program's `test(ctx)` returns (location, note): location is "yes", "no", "maybe" or "na"
# (no location test); see project.combine. ctx has flags, site, nmtc, national_register, city.


def _no_location(note=None):
    return lambda ctx: ("na", note)


def _basis_boost(ctx):
    flags = ctx["flags"]
    if flags.get("qct") or flags.get("dda"):
        which = " and ".join(n for n, on in (("a Qualified Census Tract", flags.get("qct")),
                                                ("a Difficult Development Area", flags.get("dda"))) if on)
        return "yes", f"Site is in {which}: eligible basis can be increased up to 130%, raising the credit amount."
    return "na", "Not in a QCT or DDA, so no automatic 130% basis boost (some state agencies can grant one for 9% deals)."


def _oz(ctx):
    oz = ctx["flags"].get("opportunity_zone")
    if oz:
        return "yes", "Site is in a designated Qualified Opportunity Zone tract."
    if oz is False:
        return "no", "Site is not in a current Opportunity Zone. New designations take effect in 2027; recheck then."
    return "maybe", "Opportunity Zone status could not be determined."


def _nmtc(ctx):
    tract = ctx["nmtc"]
    if tract is None:
        return "maybe", "This census tract isn't in the CDFI Fund eligibility list; confirm with the CDFI Fund mapping tool."
    poverty = tract.get("poverty_rate")
    detail = f" (tract poverty rate {poverty:g}%)" if poverty is not None else ""
    if tract["eligible"]:
        severe = " It also meets the CDFI Fund's severe distress test, which many allocatees prioritize." if tract.get("severe_distress") else ""
        return "yes", f"Site is in an NMTC Low-Income Community census tract{detail}.{severe}"
    return "no", f"Site's census tract is not an NMTC Low-Income Community{detail}, per the CDFI Fund's 2016-2020 ACS eligibility list."


def _historic(ctx):
    listing = (ctx["nr_listings"] or [None])[0]
    if listing:
        when = f", listed {listing['listed']}" if listing.get("listed") else ""
        return "yes", (f"The building at this address, {listing['name']}, is individually listed on the National Register "
                       f"(#{listing['reference_number']}{when}), so a certified rehabilitation can qualify.")
    names = ctx["national_register"]
    if names:
        return "yes", f"Site is in a National Register historic district ({', '.join(names)}). A contributing building can qualify."
    return "maybe", "Site is not in a National Register historic district; the building would need to be individually listed or eligible."


def _rural(ctx):
    if ctx["flags"].get("rural"):
        return "yes", "Site is outside a Census Urban Area, so it is likely USDA-eligible rural territory."
    return "no", "Site is inside a Census Urban Area; USDA rural housing programs are unlikely to apply."


def _promise(ctx):
    pz = ctx["flags"].get("promise_zone")
    if pz:
        return "yes", f"Site is in the {pz} Promise Zone: preference points on many federal grant competitions."
    return "no", "Site is not in a federal Promise Zone."


def _city_fact(program_id, fallback):
    """Location facts researched per city (e.g. whether the city gets HOME directly), from the city database."""
    def test(ctx):
        fact = (ctx["city"].get("federal_facts") or {}).get(program_id)
        return (fact["location"], fact["note"]) if fact else ("na", fallback)
    return test


# Plain-language explanations for the federal designations shown as chips on the site summary.
FEDERAL_ZONES = [
    {"flag": "qct", "label": "Qualified Census Tract",
     "title": "Qualified Census Tract (QCT)",
     "text": "A census tract HUD designates each year because at least half of households earn under 60% of area median income, or the poverty rate is 25% or higher.",
     "meaning": "LIHTC projects here can raise their eligible basis by up to 30%, which means more tax credit equity.",
     "url": "https://www.huduser.gov/portal/datasets/qct.html"},
    {"flag": "dda", "label": "Difficult Development Area",
     "title": "Difficult Development Area (DDA)",
     "text": "An area HUD designates each year where construction, land and utility costs are high compared with incomes.",
     "meaning": "Like a QCT, it lets LIHTC projects raise their eligible basis by up to 30%.",
     "url": "https://www.huduser.gov/portal/datasets/qct.html"},
    {"flag": "opportunity_zone", "label": "Opportunity Zone",
     "title": "Opportunity Zone",
     "text": "A low-income census tract where investors get federal capital gains tax breaks for investing through a Qualified Opportunity Fund. The program became permanent in 2025, with new zone designations starting in 2027.",
     "meaning": "It can attract investor equity to a project. In New Orleans, an Opportunity Zone location also qualifies for the Restoration Tax Abatement.",
     "url": "https://opportunityzones.hud.gov/"},
    {"flag": "promise_zone", "label": "Promise Zone",
     "title": "Promise Zone",
     "text": "A high-poverty community that partnered with the federal government for priority help; 22 were named nationwide.",
     "meaning": "Projects here get preference points on many federal grant competitions.",
     "url": "https://www.hudexchange.info/programs/promise-zones/"},
]


def zone_chips(lookup):
    """Federal designation chips (on or off) followed by the city districts the site is inside."""
    flags = lookup["flags"]
    chips = []
    for z in FEDERAL_ZONES:
        on = bool(flags.get(z["flag"]))
        label = z["label"]
        if z["flag"] == "dda" and flags.get("dda_name"):
            label = f"DDA: {flags['dda_name']}"
        if z["flag"] == "promise_zone" and flags.get("promise_zone"):
            label = f"Promise Zone: {flags['promise_zone']}"
        chips.append({"label": label, "on": on, "title": z["title"], "text": z["text"],
                      "meaning": z["meaning"] if on else "This site is not in one, so this benefit doesn't apply here.",
                      "url": z["url"]})
    for listing in lookup.get("nr_listings") or []:
        landmark = " It is also a National Historic Landmark." if listing.get("national_historic_landmark") else ""
        chips.append({
            "label": f"National Register: {listing['name']}", "on": True,
            "title": f"{listing['name']} (National Register of Historic Places)",
            "text": (f"The building at this address is individually listed on the National Register of Historic Places "
                     f"(reference #{listing['reference_number']}" + (f", listed {listing['listed']}" if listing.get("listed") else "")
                     + f").{landmark} Listing recognizes its history; it doesn't by itself restrict what a private owner does."),
            "meaning": ("A certified rehabilitation can qualify for the 20% federal historic tax credit (plus the 25% Louisiana credit "
                        "in New Orleans), which can be combined with LIHTC. Local historic review rules may also apply."),
            "url": listing.get("record_url") or "https://www.nps.gov/subjects/nationalregister/index.htm",
        })
    return chips + cities.district_chips(lookup["city"], lookup["districts"])


RENTAL = {"field": "tenure", "is": "rental", "fail": "This program funds rental housing only."}

FEDERAL_PROGRAMS = [
    {
        "id": "lihtc9",
        "name": "9% Low-Income Housing Tax Credit (competitive)",
        "type": "Tax credit",
        "agency": "IRS, allocated by your state housing finance agency",
        "summary": "Covers roughly 70% of the present value of eligible costs over 10 years. Awarded competitively through the state's Qualified Allocation Plan (QAP). Allocations were permanently increased 12% for 2026 and later years (Public Law 119-21, section 70422, amending IRC 42(h)(3)(I)).",
        "url": "https://www.irs.gov/pub/irs-utl/IRC42%20Low%20Income%20Housing%20Credit%20ATG%20Part%201.pdf",
        "references": [{"title": "26 U.S. Code 42(h)(3)(I): 12% increase in state housing credit ceilings for years after 2025 (amended by Public Law 119-21, section 70422)", "url": "https://www.law.cornell.edu/uscode/text/26/42"}],
                "eligibility": "Rental housing only. The project must meet a minimum set-aside: at least 20% of units at or below 50% AMI, 40% at or below 60% AMI, or income averaging (units averaging 60% AMI, none above 80%). Rents are capped at 30% of the income limit. 10-year credit period and 15-year compliance period, plus an extended-use agreement (at least 30 years in total). Awarded competitively under the state agency's Qualified Allocation Plan.",
"test": _basis_boost,
        "project_rules": [RENTAL, {"field": "ami", "max": 60, "fail": "LIHTC units must be restricted to 60% AMI or below (or average 60% under income averaging, with no unit above 80%)."}],
    },
    {
        "id": "lihtc4",
        "name": "4% LIHTC with tax-exempt private activity bonds",
        "type": "Tax credit + bond financing",
        "agency": "IRS, bonds allocated by state bond cap authority",
        "summary": "Non-competitive credit (about 30% of PV of eligible costs) when the deal is financed with tax-exempt bonds. The bond test drops from 50% to 25% of aggregate basis plus land when at least one bond issue dated after 2025 finances at least 5% of it (Public Law 119-21, section 70422, amending IRC 42(h)(4)(B)).",
        "url": "https://www.law.cornell.edu/uscode/text/26/42",
                "eligibility": "Rental housing only. The project must meet a minimum set-aside: at least 20% of units at or below 50% AMI, 40% at or below 60% AMI, or income averaging (units averaging 60% AMI, none above 80%). Rents are capped at 30% of the income limit. 10-year credit period and 15-year compliance period, plus an extended-use agreement (at least 30 years in total). Tax-exempt private activity bonds must finance at least 50% of aggregate basis plus land, or 25% if at least one bond issue dated after December 31, 2025 finances at least 5% of it. The state allocates bond volume cap.",
        "references": [{"title": "IRS Audit Technique Guide: IRC 42 Low-Income Housing Credit, Part 1 (general rules; written before the 2025 changes)", "url": "https://www.irs.gov/pub/irs-utl/IRC42%20Low%20Income%20Housing%20Credit%20ATG%20Part%201.pdf"}, {"title": "Williams Mullen: summary of the 2025 LIHTC changes", "url": "https://www.williamsmullen.com/insights/news/legal-news/low-income-housing-tax-credit-reform-one-big-beautiful-bill-acts-effect"}],
"test": _basis_boost,
        "project_rules": [RENTAL, {"field": "ami", "max": 60, "fail": "LIHTC units must be restricted to 60% AMI or below (or average 60% under income averaging, with no unit above 80%)."}],
    },
    {
        "id": "home",
        "name": "HOME Investment Partnerships Program",
        "type": "Grant / soft loan",
        "agency": "HUD, through state and local participating jurisdictions",
        "summary": "Gap financing for affordable rental or homeownership housing, new or rehab, for households at or below 80% AMI. Apply to the participating jurisdiction that covers the site.",
        "url": "https://www.hudexchange.info/programs/home/",
                "eligibility": "Assisted units must serve households at or below 80% AMI and stay affordable for a required period. Funds are awarded by the participating jurisdiction (city, county or state) through its own notices.",
"test": _city_fact("home", "Funds flow through the local participating jurisdiction; check its Action Plan and NOFA schedule."),
        "project_rules": [{"field": "ami", "max": 80, "fail": "HOME-assisted units must serve households at or below 80% AMI."}],
    },
    {
        "id": "htf",
        "name": "National Housing Trust Fund (HTF)",
        "type": "Grant / soft loan",
        "agency": "HUD, through the state",
        "summary": "Block grant to states for rental housing serving extremely low-income households (30% AMI or below). Often paired with LIHTC.",
        "url": "https://www.hudexchange.info/programs/htf/",
                "eligibility": "Rental units must serve extremely low-income households (30% AMI or below, or the federal poverty line if higher). Administered by the state, usually alongside LIHTC.",
"test": _no_location("Administered statewide, usually by the housing finance agency."),
        "project_rules": [RENTAL, {"field": "ami", "max": 30, "fail": "HTF units must serve extremely low-income households (30% AMI or below)."}],
    },
    {
        "id": "cdbg",
        "name": "Community Development Block Grant (CDBG)",
        "type": "Grant",
        "agency": "HUD, through entitlement cities/counties or the state",
        "summary": "Flexible funds commonly used for acquisition, site prep, infrastructure, and rehab supporting low- and moderate-income housing (new construction only in limited cases).",
        "url": "https://www.hud.gov/program_offices/comm_planning/cdbg",
                "eligibility": "Activities must meet a national objective, usually benefiting low- and moderate-income households (80% AMI or below). New housing construction is restricted, so CDBG more often pays for acquisition, site work, infrastructure or rehab.",
"test": _city_fact("cdbg", "Check whether the city/county is an entitlement community or applies through the state program."),
        "project_rules": [{"field": "ami", "max": 80, "fail": "CDBG housing must benefit low- and moderate-income households (80% AMI or below)."}],
    },
    {
        "id": "nmtc",
        "name": "New Markets Tax Credit (NMTC)",
        "type": "Tax credit",
        "agency": "CDFI Fund (U.S. Treasury), via Community Development Entities",
        "summary": "39% credit over 7 years on qualified equity investments in low-income communities. The 2025 federal tax law made the program permanent with $5 billion of allocation authority each year. Usually supports community facilities or commercial space in mixed-use projects; residential rental property generally does not qualify on its own.",
        "url": "https://www.cdfifund.gov/programs-training/programs/new-markets-tax-credit",
                "eligibility": "The project must be in a Low-Income Community census tract (poverty rate 20% or more, or median family income at or below 80% of the area or state median). Investment flows through a Community Development Entity that holds an allocation. Residential rental property generally doesn't qualify; the commercial or community portion of a mixed-use project can. 7-year compliance period.",
        "references": [{"title": "26 U.S. Code 45D(f): $5 billion of NMTC allocation for each year after 2019, made permanent by Public Law 119-21, section 70423", "url": "https://www.law.cornell.edu/uscode/text/26/45D"}, {"title": "Forvis Mazars: NMTC program now permanent under the 2025 tax law", "url": "https://www.forvismazars.us/forsights/2025/08/the-new-markets-tax-credit-nmtc-program-now-permanent-under-the-obbba"}],
"test": _nmtc,
        "project_rules": [{"field": "commercial", "is": True, "fail": "NMTC generally needs a commercial or community-facility component; residential rental property alone doesn't qualify."}],
    },
    {
        "id": "oz",
        "name": "Opportunity Zone capital gains incentives",
        "type": "Tax incentive",
        "agency": "IRS / Treasury",
        "summary": "Investors who put capital gains into a Qualified Opportunity Fund can defer tax on those gains, and gains on the new investment held 10 or more years are tax-free. The 2025 federal tax law made the program permanent: states redesignate zones every 10 years (new zones take effect January 1, 2027), and investments from 2027 on get a rolling 5-year deferral and a 10% basis step-up after 5 years (30% for rural funds).",
        "url": "https://www.irs.gov/credits-deductions/businesses/opportunity-zones",
                "eligibility": "The benefits go to the investor, not directly to the developer. Capital gains must be invested through a Qualified Opportunity Fund that holds property in a designated zone; existing buildings generally must be substantially improved.",
        "references": [{"title": "26 U.S. Code 1400Z-1: zone designation rules as amended by Public Law 119-21, section 70421", "url": "https://www.law.cornell.edu/uscode/text/26/1400Z-1"}, {"title": "26 U.S. Code 1400Z-2: investor deferral and exclusion as amended by Public Law 119-21, section 70421", "url": "https://www.law.cornell.edu/uscode/text/26/1400Z-2"}, {"title": "Greenberg Traurig: 2025 law adopts permanent Opportunity Zone rules with rolling deferral", "url": "https://www.gtlaw.com/en/insights/2025/7/president-trump-signs-one-big-beautiful-bill-act-adopting-permanent-qualified-opportunity-zone-provisions-with-rolling-deferral"}],
"test": _oz,
        "project_rules": [],
    },
    {
        "id": "htc",
        "name": "Federal Historic Rehabilitation Tax Credit",
        "type": "Tax credit",
        "agency": "National Park Service / IRS / State Historic Preservation Office",
        "summary": "20% credit on qualified rehabilitation expenses for certified historic structures used to produce income (including rentals). Stacks with LIHTC on adaptive reuse projects.",
        "url": "https://www.nps.gov/subjects/taxincentives/index.htm",
                "eligibility": "The building must be a certified historic structure (individually listed, or contributing to a registered district) and used to produce income, such as rentals. The rehab must meet the Secretary of the Interior's Standards and be substantial (more than the greater of the building's adjusted basis or $5,000). Apply through the State Historic Preservation Office and the National Park Service.",
"test": _historic,
        "project_rules": [
            {"field": "construction", "is": "rehab", "fail": "The historic credit only covers rehabilitating an existing historic building."},
            {"field": "tenure", "is": "rental", "fail": "The federal credit is for income-producing buildings, such as rentals, not homes sold to owners."},
        ],
    },
    {
        "id": "fha221d4",
        "name": "FHA 221(d)(4) mortgage insurance",
        "type": "Insured loan",
        "agency": "HUD Office of Multifamily Housing",
        "summary": "Non-recourse, up to 40-year fixed-rate construction-to-permanent debt for new construction or substantial rehab, with higher leverage for affordable deals.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/rentcoophsg221d3n4",
                "eligibility": "Multifamily rental of 5 or more units, new construction or substantial rehab; HUD underwriting and Davis-Bacon wage rules apply.",
"test": _no_location("Available nationwide."),
        "project_rules": [RENTAL, {"field": "units", "min": 5, "fail": "221(d)(4) is for multifamily projects of 5 or more units."}],
    },
    {
        "id": "fhlb_ahp",
        "name": "FHLBank Affordable Housing Program (AHP)",
        "type": "Grant",
        "agency": "Your regional Federal Home Loan Bank, through a member bank",
        "summary": "Competitive grants (typically up to ~$1–2M per project) for units serving households at or below 80% AMI. Requires a sponsoring member bank. Rounds are usually annual.",
        "url": "https://www.fhlbanks.com/affordable-housing-programs/",
                "eligibility": "Apply through a member bank of your regional FHLBank. Assisted units must serve households at or below 80% AMI, rental projects carry a retention (affordability) period, and applications are scored competitively in the bank's annual round.",
"test": _no_location("Apply through a member bank during the regional FHLBank's round."),
        "project_rules": [{"field": "ami", "max": 80, "fail": "AHP-assisted units must serve households at or below 80% AMI."}],
    },
    {
        "id": "s811",
        "name": "Section 811 Supportive Housing for Persons with Disabilities",
        "type": "Rental subsidy",
        "agency": "HUD, through state housing agencies",
        "summary": "Project rental assistance for units set aside for extremely low-income people with disabilities.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/disab811",
                "eligibility": "Units set aside for extremely low-income people with disabilities, through the state housing agency's Section 811 program.",
"test": _no_location("Administered through the state housing agency."),
        "project_rules": [RENTAL, {"field": "populations", "has": "disability", "fail": "Section 811 is only for units set aside for people with disabilities."}],
    },
    {
        "id": "s202",
        "name": "Section 202 Supportive Housing for the Elderly",
        "type": "Capital advance / rental subsidy",
        "agency": "HUD",
        "summary": "Capital advances and rental assistance for very low-income senior housing developed by nonprofit sponsors. Funded through periodic NOFOs.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/eld202",
                "eligibility": "Nonprofit sponsor; very low-income households (50% AMI or below) with at least one member 62 or older. Funded only when HUD issues a notice of funding.",
"test": _no_location(),
        "project_rules": [
            RENTAL,
            {"field": "populations", "has": "seniors", "fail": "Section 202 is only for senior housing."},
            {"field": "owner", "is": "nonprofit", "fail": "Section 202 sponsors must be nonprofits."},
            {"field": "ami", "max": 50, "fail": "Section 202 serves very low-income seniors (50% AMI or below)."},
        ],
    },
    {
        "id": "usda515",
        "name": "USDA Section 515 / 538 Rural Rental Housing",
        "type": "Direct loan / loan guarantee",
        "agency": "USDA Rural Development",
        "summary": "Section 515 offers direct 1% loans and Section 538 guarantees private loans for rental housing in eligible rural areas.",
        "url": "https://www.rd.usda.gov/programs-services/multi-family-housing-programs",
                "eligibility": "Eligible rural areas only; rental housing for very low-, low- and moderate-income households.",
"test": _rural,
        "project_rules": [RENTAL],
    },
    {
        "id": "promise",
        "name": "Promise Zone preference",
        "type": "Competitive preference",
        "agency": "HUD and partner agencies",
        "summary": "Projects in a Promise Zone receive priority consideration for many federal grant programs.",
        "url": "https://www.hudexchange.info/programs/promise-zones/",
                "eligibility": "Applies only inside a designated Promise Zone; it gives preference points on grant competitions, not money.",
"test": _promise,
        "project_rules": [],
    },
    {
        "id": "cmf",
        "name": "CDFI Capital Magnet Fund",
        "type": "Grant (via CDFIs/nonprofits)",
        "agency": "CDFI Fund (U.S. Treasury)",
        "summary": "Awards to CDFIs and nonprofit housing organizations, which re-lend or invest in affordable housing for households up to 120% AMI. Look for local CDFIs with active awards.",
        "url": "https://www.cdfifund.gov/programs-training/programs/cmf",
                "eligibility": "Accessed through a CDFI or nonprofit housing organization that holds a Capital Magnet Fund award; housing must serve households up to 120% AMI.",
"test": _no_location("Accessed through CDFIs that hold awards in your region."),
        "project_rules": [{"field": "ami", "max": 120, "fail": "Capital Magnet Fund housing serves households up to 120% AMI."}],
    },
]


def site_facts(lookup):
    """Location facts federal tests use, computed once per site."""
    city = cities.CITIES_BY_ID[lookup["city"]["id"]]
    nr_keys = city.get("national_register_districts", [])
    nr_names = sorted({cities.display_name(n) for k in nr_keys for n in lookup["districts"].get(k, [])})
    return {
        "flags": lookup["flags"],
        "site": lookup["site"],
        "city": city,
        "nmtc": NMTC_TRACTS.get(lookup["site"].get("tract_geoid") or ""),
        "national_register": nr_names,
        "nr_listings": lookup.get("nr_listings") or [],
    }


def match(lookup, project=None):
    """Federal programs checked against the site and project, plus the city database grouped by level."""
    project = project or {}
    ctx = site_facts(lookup)
    federal = []
    federal_contacts = ctx["city"].get("federal_contacts") or {}
    for p in FEDERAL_PROGRAMS:
        location, note = p["test"](ctx)
        status, reason = proj.combine(location, note, p["project_rules"], project)
        federal.append({k: v for k, v in p.items() if k not in ("test", "project_rules")} | {
            "status": status, "reason": reason,
            "project_checked": proj.evaluate(p["project_rules"], project)[0] == "pass",
            "contact": cities.agency(ctx["city"], federal_contacts.get(p["id"])),
            "last_reviewed": FEDERAL_LAST_REVIEWED,
        })

    local = cities.match(ctx["city"], lookup["districts"], lookup["flags"], project)
    groups = {"federal": federal, "state": [], "local": [], "neighborhood": []}
    for p in local:
        groups["local" if p["level"] in ("county", "city") else p["level"]].append(p)
    for items in groups.values():
        items.sort(key=lambda p: STATUS_ORDER[p["status"]])
    return groups
