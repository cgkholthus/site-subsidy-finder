"""Independent check of the capital stack page's math.

Works out four sample projects from first principles (standard loan-payment formula, IRC 42 credit
formula) without reusing any code from static/stack.js. Prints the expected numbers; compare them with
the page and the downloaded CSV, or pass a JSON file of the page's numbers to compare automatically:

    python3 tests/check_stack.py                 # print expected numbers
    python3 tests/check_stack.py page.json       # compare with numbers read from the page
"""
import json
import sys


def annual_debt_service_per_dollar(rate, years):
    """Monthly-pay mortgage: payment = P * i / (1 - (1 + i)^-n), times 12."""
    i = rate / 12
    n = years * 12
    return 12 * i / (1 - (1 + i) ** -n)


def project(p):
    tdc = p["units"] * p["cost_per_unit"]
    # Loan sized so year-1 NOI covers the payment p["dscr"] times.
    gross_rent = p["units"] * p["rent"] * 12
    noi = gross_rent * (1 - p["vacancy"]) - p["units"] * p["opex"]
    income_loan = noi / p["dscr"] / annual_debt_service_per_dollar(p["rate"], p["years"])
    loan = min(income_loan, tdc * p["max_ltc"])  # lenders cap the loan at a share of cost
    max_payment = loan * annual_debt_service_per_dollar(p["rate"], p["years"])

    # Land: the entered purchase price, or a share of total cost. A building purchase is part of total cost too.
    land = min(p["land_price"], tdc) if p.get("land_price") else tdc * p["land"]
    acq = max(0.0, min(p.get("building_price", 0), tdc - land))
    qre = min(tdc * p.get("qre_share", 0), max(0.0, tdc - land - acq))  # rehab work excludes purchase prices
    fed_htc_credit = qre * 0.20 if p.get("fed_htc") else 0
    fed_htc_equity = fed_htc_credit * p["fed_htc_price"]
    la_htc_equity = qre * 0.25 * p["la_htc_price"] if p.get("la_htc") else 0
    ahp = 1_000_000 if p.get("ahp") else 0

    # Eligible basis: depreciable cost (no land), the share counted in basis, less the federal
    # historic credit (IRC 50(c) basis reduction).
    eligible = (tdc - land - acq) * p["basis_share"] - fed_htc_credit
    qualified = eligible * (1.3 if p["boost"] else 1.0) * p["affordable"]
    # Acquisition credits: building purchase price at the 4% rate, never boosted (IRC 42(b), 42(d)(5)(B)).
    acq_credit = acq * p["affordable"] * 0.04

    out = {"tdc": tdc, "noi": noi, "loan": loan, "annual_debt_service": max_payment}
    for kind, rate in (("9", 0.09), ("4", 0.04)):
        annual_credit = qualified * rate + acq_credit
        if kind == "9" and p["cap9"]:
            annual_credit = min(annual_credit, p["cap9"])  # state per-project cap on 9% credits
        max_equity = annual_credit * 10 * p["lihtc_price"]
        others = loan + fed_htc_equity + la_htc_equity + ahp
        equity = max(0.0, min(max_equity, tdc - others))  # IRC 42(m)(2): no more than the gap
        fee_room = tdc * p["fee"] * p["deferred"]
        deferred = max(0.0, min(fee_room, tdc - others - equity))
        out[kind] = {
            "max_equity": max_equity,
            "equity": equity,
            "deferred_fee": deferred,
            "gap": tdc - others - equity - deferred,
        }
    out["fed_htc_equity"] = fed_htc_equity
    out["la_htc_equity"] = la_htc_equity
    # Year-by-year operating figures for the CSV check.
    years = []
    for y in range(15):
        gpr = gross_rent * (1 + p["rent_growth"]) ** y
        egi = gpr * (1 - p["vacancy"])
        opex = p["units"] * p["opex"] * (1 + p["expense_growth"]) ** y
        years.append({"noi": egi - opex, "cash_flow": egi - opex - max_payment})
    out["year1_noi"], out["year15_noi"] = years[0]["noi"], years[14]["noi"]
    out["year15_cash_flow"] = years[14]["cash_flow"]
    return out


COMMON = dict(vacancy=0.07, rate=0.065, years=35, dscr=1.2, land=0.05, basis_share=0.95, affordable=1.0, max_ltc=0.60,
              fee=0.12, deferred=0.40, rent_growth=0.02, expense_growth=0.03, lihtc_price=0.83,
              fed_htc_price=0.88, la_htc_price=0.80, ahp=False)

CASES = {
    # A: Portland, 60 new-construction rental units, housing only, no QCT/DDA boost, Portland defaults.
    #    9% credits hit Oregon's $2,000,000 per-project cap.
    "A_portland_new": dict(COMMON, units=60, cost_per_unit=580_000, rent=1600, opex=8500, boost=False, cap9=2_000_000),
    # B: New Orleans renovation, 40 units, in a QCT, federal + Louisiana historic credits on 70% of cost.
    "B_nola_rehab": dict(COMMON, units=40, cost_per_unit=370_000, rent=1100, opex=8000, boost=True,
                         qre_share=0.70, fed_htc=True, la_htc=True, cap9=1_500_000),
    # C: New Orleans, 30 units at a very high $9,000 rent: the loan hits the 60%-of-cost limit.
    "C_nola_loan_cap": dict(COMMON, units=30, cost_per_unit=370_000, rent=9000, opex=8000, boost=False, cap9=1_500_000),
    # D: Portland renovation, 50 units, in a QCT, with entered land ($1.2M) and building ($6M) purchase prices.
    #    Tests the purchase prices, acquisition credits at 4% with no boost, and rehab basis with the boost.
    "D_pdx_purchase": dict(COMMON, units=50, cost_per_unit=450_000, rent=1500, opex=8000, boost=True,
                           land_price=1_200_000, building_price=6_000_000, cap9=0),
}


def flatten(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flatten(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


def main():
    expected = {name: project(p) for name, p in CASES.items()}
    if len(sys.argv) < 2:
        for name, res in expected.items():
            print(name)
            for k, v in flatten(res):
                print(f"  {k:28} {v:>16,.0f}")
        return
    page = json.load(open(sys.argv[1]))
    worst = 0
    for name, res in expected.items():
        print(name)
        got = dict(flatten(page[name]))
        for k, v in flatten(res):
            if k not in got:
                continue
            diff = got[k] - v
            worst = max(worst, abs(diff))
            print(f"  {k:28} expected {v:>14,.0f}  page {got[k]:>14,.0f}  {'OK' if abs(diff) < 1 else 'DIFF ' + format(diff, ',.0f')}")
    print("All match (within $1)." if worst < 1 else f"Largest difference: ${worst:,.0f}")
    sys.exit(0 if worst < 1 else 1)


if __name__ == "__main__":
    main()
