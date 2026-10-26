"""Curated federal programs matched against a site's flags; city programs come from cities.py.

Federal rules reflect the July 2025 reconciliation law (OBBBA): 12% permanent boost to 9% LIHTC
allocations, 25% bond test for 4% deals on bonds issued after 2025, permanent NMTC, and a
permanent Opportunity Zone program with a new round of designations starting in 2027.
Program rules change; every entry links to its source so users can verify.
"""

import cities

STATUS_ORDER = {"eligible": 0, "applies": 1, "check": 2, "ineligible": 3, "not_applicable": 4}

# Each program: `applies(flags, site)` returns (status, reason). Status is one of
# "eligible" (site-level test met), "check" (depends on project/sponsor), "ineligible".


def _always(reason):
    return lambda flags, site: ("check", reason)


def _basis_boost(flags, site):
    if flags.get("qct") or flags.get("dda"):
        which = " and ".join(n for n, on in (("a Qualified Census Tract", flags.get("qct")),
                                                ("a Difficult Development Area", flags.get("dda"))) if on)
        return "eligible", f"Site is in {which}: eligible basis can be increased up to 130%, raising the credit amount."
    return "check", "Not in a QCT or DDA. Many state HFAs can still grant a discretionary 130% boost for 9% deals."


def _oz(flags, site):
    if flags.get("opportunity_zone"):
        return "eligible", "Site is in a designated Qualified Opportunity Zone tract."
    if flags.get("opportunity_zone") is False:
        return "ineligible", "Site is not in a current Opportunity Zone. New designations take effect in 2027; recheck then."
    return "check", "Opportunity Zone status could not be determined."


def _nmtc(flags, site, stats):
    if stats and stats.get("poverty_rate") is not None:
        if stats["poverty_rate"] >= 20:
            return "eligible", f"Tract poverty rate is {stats['poverty_rate']}% (20%+ qualifies as a Low-Income Community)."
        return "check", (f"Tract poverty rate is {stats['poverty_rate']}%. It may still qualify on the median family "
                         "income test (80% of area MFI or less); confirm with the CDFI Fund mapping tool.")
    if flags.get("qct"):
        return "check", "QCTs usually also qualify as NMTC Low-Income Communities; confirm with the CDFI Fund mapping tool."
    return "check", "Confirm Low-Income Community status with the CDFI Fund mapping tool. NMTC typically funds the commercial/mixed-use portion."


def _rural(flags, site):
    if flags.get("rural"):
        return "eligible", "Site is outside a Census Urban Area, so it is likely USDA-eligible rural territory."
    return "ineligible", "Site is inside a Census Urban Area; USDA rural housing programs are unlikely to apply."


def _promise(flags, site):
    if flags.get("promise_zone"):
        return "eligible", f"Site is in the {flags['promise_zone']} Promise Zone: preference points on many federal grant competitions."
    return "ineligible", "Site is not in a federal Promise Zone."


FEDERAL_PROGRAMS = [
    {
        "id": "lihtc9",
        "name": "9% Low-Income Housing Tax Credit (competitive)",
        "type": "Tax credit",
        "agency": "IRS, allocated by your state housing finance agency",
        "summary": "Covers roughly 70% of the present value of eligible costs over 10 years. Awarded competitively through the state's Qualified Allocation Plan (QAP). Allocations were permanently increased 12% starting 2026.",
        "url": "https://www.huduser.gov/portal/datasets/lihtc.html",
        "test": _basis_boost,
    },
    {
        "id": "lihtc4",
        "name": "4% LIHTC with tax-exempt private activity bonds",
        "type": "Tax credit + bond financing",
        "agency": "IRS, bonds allocated by state bond cap authority",
        "summary": "Non-competitive credit (about 30% of PV of eligible costs) when the deal is financed with tax-exempt bonds. Bonds issued after 2025 only need to cover 25% of aggregate basis plus land, down from 50%.",
        "url": "https://www.huduser.gov/portal/datasets/lihtc.html",
        "test": _basis_boost,
    },
    {
        "id": "home",
        "name": "HOME Investment Partnerships Program",
        "type": "Grant / soft loan",
        "agency": "HUD, through state and local participating jurisdictions",
        "summary": "Gap financing for rental construction/rehab for households at or below 80% AMI. Apply to your city, county, or state, whichever is the participating jurisdiction for the site.",
        "url": "https://www.hudexchange.info/programs/home/",
        "test": _always("Funds flow through the local participating jurisdiction; check its Action Plan and NOFA schedule."),
    },
    {
        "id": "htf",
        "name": "National Housing Trust Fund (HTF)",
        "type": "Grant / soft loan",
        "agency": "HUD, through the state",
        "summary": "Block grant to states for rental housing serving extremely low-income households (30% AMI or below). Often paired with LIHTC.",
        "url": "https://www.hudexchange.info/programs/htf/",
        "test": _always("Administered by the state, usually the HFA. Requires ELI-restricted units."),
    },
    {
        "id": "cdbg",
        "name": "Community Development Block Grant (CDBG)",
        "type": "Grant",
        "agency": "HUD, through entitlement cities/counties or the state",
        "summary": "Flexible funds commonly used for acquisition, site prep, infrastructure, and rehab supporting low- and moderate-income housing (new construction only in limited cases).",
        "url": "https://www.hud.gov/program_offices/comm_planning/cdbg",
        "test": _always("Check whether the city/county is an entitlement community or applies through the state program."),
    },
    {
        "id": "pbv",
        "name": "Project-Based Vouchers (Section 8)",
        "type": "Rental subsidy",
        "agency": "Local public housing agency (PHA)",
        "summary": "Long-term rental assistance contracts attached to units, which supports debt sizing. PHAs issue competitive RFPs.",
        "url": "https://www.hud.gov/program_offices/public_indian_housing/programs/hcv/project",
        "test": _always("Contact the local PHA for PBV RFP availability."),
    },
    {
        "id": "nmtc",
        "name": "New Markets Tax Credit (NMTC)",
        "type": "Tax credit",
        "agency": "CDFI Fund (U.S. Treasury), via Community Development Entities",
        "summary": "39% credit over 7 years on qualified equity investments in low-income communities. Made permanent in 2025. Usually supports community facilities or commercial space in mixed-use projects; residential rental property generally does not qualify on its own.",
        "url": "https://www.cdfifund.gov/programs-training/programs/new-markets-tax-credit",
        "test": None,  # needs tract stats, handled in match()
    },
    {
        "id": "oz",
        "name": "Opportunity Zone capital gains incentives",
        "type": "Tax incentive",
        "agency": "IRS / Treasury",
        "summary": "Investors can defer and reduce capital gains by investing through a Qualified Opportunity Fund, and gains on the new investment held 10+ years are tax-free. The program is now permanent with rolling 10-year designations.",
        "url": "https://www.irs.gov/credits-deductions/businesses/opportunity-zones",
        "test": _oz,
    },
    {
        "id": "htc",
        "name": "Federal Historic Rehabilitation Tax Credit",
        "type": "Tax credit",
        "agency": "National Park Service / IRS / State Historic Preservation Office",
        "summary": "20% credit on qualified rehabilitation expenses for certified historic structures. Stacks with LIHTC on adaptive reuse projects.",
        "url": "https://www.nps.gov/subjects/taxincentives/index.htm",
        "test": _always("Only applies if the building is listed on, or eligible for, the National Register (individually or in a historic district)."),
    },
    {
        "id": "fha221d4",
        "name": "FHA 221(d)(4) mortgage insurance",
        "type": "Insured loan",
        "agency": "HUD Office of Multifamily Housing",
        "summary": "Non-recourse, up to 40-year fixed-rate construction-to-permanent debt for new construction or substantial rehab, with higher leverage for affordable deals.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/rentcoophsg221d3n4",
        "test": _always("Available nationwide; underwriting depends on the project."),
    },
    {
        "id": "fhlb_ahp",
        "name": "FHLBank Affordable Housing Program (AHP)",
        "type": "Grant",
        "agency": "Your regional Federal Home Loan Bank, through a member bank",
        "summary": "Competitive grants (typically up to ~$1–2M per project) for units serving households at or below 80% AMI. Requires a sponsoring member bank.",
        "url": "https://www.fhlbanks.com/affordable-housing-programs/",
        "test": _always("Apply through a member financial institution during the regional bank's annual round."),
    },
    {
        "id": "s811",
        "name": "Section 811 Supportive Housing for Persons with Disabilities",
        "type": "Rental subsidy",
        "agency": "HUD, through state housing agencies",
        "summary": "Project rental assistance for units set aside for extremely low-income people with disabilities.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/disab811",
        "test": _always("Relevant if the project includes supportive units; check with the state HFA."),
    },
    {
        "id": "s202",
        "name": "Section 202 Supportive Housing for the Elderly",
        "type": "Capital advance / rental subsidy",
        "agency": "HUD",
        "summary": "Capital advances and rental assistance for very low-income senior housing developed by nonprofit sponsors.",
        "url": "https://www.hud.gov/program_offices/housing/mfh/progdesc/eld202",
        "test": _always("Relevant for nonprofit-sponsored senior housing; funded through periodic NOFOs."),
    },
    {
        "id": "usda515",
        "name": "USDA Section 515 / 538 Rural Rental Housing",
        "type": "Direct loan / loan guarantee",
        "agency": "USDA Rural Development",
        "summary": "Section 515 offers direct 1% loans and Section 538 guarantees private loans for rental housing in eligible rural areas.",
        "url": "https://www.rd.usda.gov/programs-services/multi-family-housing-programs",
        "test": _rural,
    },
    {
        "id": "promise",
        "name": "Promise Zone preference",
        "type": "Competitive preference",
        "agency": "HUD and partner agencies",
        "summary": "Projects in a Promise Zone receive priority consideration for many federal grant programs.",
        "url": "https://www.hudexchange.info/programs/promise-zones/",
        "test": _promise,
    },
    {
        "id": "cmf",
        "name": "CDFI Capital Magnet Fund",
        "type": "Grant (via CDFIs/nonprofits)",
        "agency": "CDFI Fund (U.S. Treasury)",
        "summary": "Awards to CDFIs and nonprofit housing organizations, which re-lend or invest in affordable housing. Look for local CDFIs with active awards.",
        "url": "https://www.cdfifund.gov/programs-training/programs/cmf",
        "test": _always("Accessed indirectly through CDFIs that hold awards in your region."),
    },
]


def match(lookup):
    """Federal programs checked against the site, plus the city database grouped by level."""
    flags, site, stats = lookup["flags"], lookup["site"], lookup.get("tract_stats")
    federal = []
    for p in FEDERAL_PROGRAMS:
        status, reason = _nmtc(flags, site, stats) if p["id"] == "nmtc" else p["test"](flags, site)
        federal.append({k: v for k, v in p.items() if k != "test"} | {"status": status, "reason": reason})

    local = cities.match(lookup["city"], lookup["districts"], flags)
    groups = {"federal": federal, "state": [], "local": [], "neighborhood": []}
    for p in local:
        groups["local" if p["level"] in ("county", "city") else p["level"]].append(p)
    for items in groups.values():
        items.sort(key=lambda p: STATUS_ORDER[p["status"]])
    return groups
