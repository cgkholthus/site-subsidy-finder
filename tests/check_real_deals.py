"""Compare the capital stack page's LIHTC formula with real 2025-2026 awards.

Each deal's published total development cost (TDC) and annual credit come from the agency documents
listed in SOURCES. The page estimates eligible basis as (TDC - land) x basis share, so the useful test
is: what share of TDC did each real deal actually carry as eligible basis?

    implied basis share = annual credit / (credit rate x boost x TDC)

A deal's site address (and so its QCT/DDA boost) isn't always published, so both readings are shown;
a share above 100% is impossible, which tells you the deal was boosted. Deals whose credits hit the
state's per-project cap, or were sized down to their funding gap, don't measure basis and are listed
separately.

    python3 tests/check_real_deals.py
"""
from statistics import median

SOURCES = {
    "OHCS-NOV": "https://www.oregon.gov/ohcs/hsc/Documents/meetings/2026-NOV-06-HSC-Meeting-Packet.pdf",
    "OHCS-OCT": "https://www.oregon.gov/ohcs/hsc/Documents/meetings/2026-OCT-02-HSC-Meeting-Packet.pdf",
    "OHCS-AUG": "https://www.oregon.gov/ohcs/hsc/Documents/meetings/2026-AUG-07-HSC-Meeting-Packet.pdf",
    "LHC-2025": "https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Funding%20Opportunities/LIHTC/Final%202025%20QAP%20Rankings%20as%20of%2010.15.25.pdf",
}

# name, source, kind ("9" or "4"), units, TDC, annual credit, land cost if published
DEALS = [
    ("Gordly Burch House, Portland", "OHCS-NOV", "9", 22, 12_565_598, 1_002_100, 103_211),
    ("Garfield Commons, Portland", "OHCS-AUG", "4", 59, 988_000 + 22_154_815 + 12_549_190, 1_669_690, 988_000),
    ("Flatworks Building, Portland", "OHCS-OCT", "4", 143, 49_944_318 + 27_789_434, 3_520_693, None),
    ("Blueberry Hill 2 Homes, Orleans Parish", "LHC-2025", "9", 47, 15_125_000, 1_480_000, None),
    ("Marrero Village, Jefferson Parish", "LHC-2025", "9", 39, 13_966_360, 1_469_357, None),
    # Louisiana 2025 urban and rural new construction awards below the $1.5M cap
    ("Riser Senior Town Homes", "LHC-2025", "9", 20, 5_361_343, 575_000, None),
    ("Woodlawn", "LHC-2025", "9", 24, 6_153_139, 665_000, None),
    ("Chesapeake Apartments", "LHC-2025", "9", 22, 6_384_226, 679_960, None),
    ("Holly Cove Apartments", "LHC-2025", "9", 28, 8_062_110, 847_380, None),
    ("Oak Springs Apartments", "LHC-2025", "9", 36, 8_830_459, 898_999, None),
    ("Telemaque", "LHC-2025", "9", 50, 13_328_233, 1_400_000, None),
    ("Fondren Place", "LHC-2025", "9", 24, 6_208_506, 650_000, None),
    ("Opelousas North Homes", "LHC-2025", "9", 28, 9_502_445, 1_000_000, None),
]
AT_CAP = [
    ("Torchwood South, Tigard (Oregon cap $2,000,000)", "OHCS-NOV", "9", 48, 28_423_147, 2_000_000, 1_850_000),
    ("Louisiana: 8 of 45 awards at exactly $1,500,000 (e.g. Northside Place, Holmes Drive, Sharlo Senior)", "LHC-2025", "9", None, None, 1_500_000, None),
]

MODELS = {
    "old defaults (land 8%, basis 85%)": 0.92 * 0.85,
    "new defaults (land 5%, basis 95%)": 0.95 * 0.95,
}


def main():
    print(f"{'Deal':42} {'TDC/unit':>9} {'credit/TDC':>10} {'basis if not boosted':>21} {'if boosted':>11}")
    shares = []
    for name, src, kind, units, tdc, credit, land in DEALS:
        rate = 0.09 if kind == "9" else 0.04
        plain = credit / (rate * tdc)
        boosted = plain / 1.3
        fit = boosted if plain > 1 else plain  # over 100% is impossible, so the deal was boosted
        shares.append(fit)
        print(f"{name[:42]:42} {tdc / units:>9,.0f} {credit / tdc:>9.1%} {plain:>20.0%}{'*' if plain > 1 else ' '} {boosted:>10.0%}")
    print("* over 100% of total cost, so this deal must have had the 130% boost.\n")
    lo, mid, hi = min(shares), median(shares), max(shares)
    print(f"Eligible basis as a share of TDC, using the boosted reading only where it's required: "
          f"low {lo:.0%}, median {mid:.0%}, high {hi:.0%}")
    print("(Deals without the 130% boost that could be read either way are taken as not boosted, so the median is a ceiling.)\n")
    for label, share in MODELS.items():
        print(f"Page, {label}: basis = {share:.1%} of TDC")
    print("\nDeals at the state cap (they test the cap, not the basis formula):")
    for name, src, *_ in AT_CAP:
        print(f"  {name}")
    print("\nSources:")
    for k, u in SOURCES.items():
        print(f"  {k}: {u}")


if __name__ == "__main__":
    main()
