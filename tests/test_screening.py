"""End-to-end screening test: one address per city, through the running local server.

For each address it checks the mapped districts, then changes one project answer and checks that
the program's status changes for the expected reason. Start the server first (python3 app/server.py).

    python3 tests/test_screening.py

The mapped districts were also checked by hand against official sources on 2026-11-17 (see
tests/VERIFICATION.md).
"""
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"


def lookup(address, project=None):
    q = {"address": address}
    if project is not None:
        q["project"] = json.dumps(project)
    with urllib.request.urlopen(f"{BASE}/api/lookup?{urllib.parse.urlencode(q)}", timeout=90) as r:
        return json.load(r)


def program(result, pid):
    return next(p for group in result["programs"].values() for p in group if p["id"] == pid)


CASES = [
    {
        "address": "1300 Perdido St, New Orleans, LA 70112",
        "districts": {"special": ["Downtown Development District", "Opportunity Zone"],
                      "miz": ["Core Sub-District"]},
        "tract": "22071013400",
        "program": "nmtc",
        "change": "commercial",
        # Housing only fails NMTC's rule; adding commercial space passes it. The location fits either way.
        "before": ({"tenure": "rental", "commercial": "no"}, "ineligible", "commercial"),
        "after": ({"tenure": "rental", "commercial": "yes"}, "eligible", None),
    },
    {
        "address": "4805 N Williams Ave, Portland, OR 97217",
        "districts": {"tif": ["Interstate Corridor"], "neighborhood": ["Humboldt"]},
        "tract": "41051003401",
        "program": "pdx_multe",
        "change": "units",
        # MULTE is tied to Inclusionary Housing, which covers buildings of 20 or more units.
        "before": ({"tenure": "rental", "units": 19}, "ineligible", "20+ units"),
        "after": ({"tenure": "rental", "units": 20}, "eligible", None),
    },
]


def main():
    failures = 0

    def check(ok, text):
        nonlocal failures
        print(("  PASS " if ok else "  FAIL ") + text)
        failures += 0 if ok else 1

    for case in CASES:
        print(case["address"])
        base = lookup(case["address"])
        check(base["site"]["tract_geoid"] == case["tract"], f"census tract {base['site']['tract_geoid']}")
        for key, wanted in case["districts"].items():
            found = base["districts"].get(key, [])
            for w in wanted:
                check(any(w in name for name in found), f"district {key}: {w!r} in {found}")

        pid = case["program"]
        before_answers, before_status, before_reason = case["before"]
        after_answers, after_status, _ = case["after"]
        b = program(lookup(case["address"], before_answers), pid)
        a = program(lookup(case["address"], after_answers), pid)
        check(b["status"] == before_status,
              f"{pid} with {case['change']}={before_answers[case['change']]!r}: {b['status']} ({b['reason']})")
        check(before_reason.lower() in b["reason"].lower(), f"reason mentions {before_reason!r}")
        check(a["status"] == after_status and a["project_checked"],
              f"{pid} with {case['change']}={after_answers[case['change']]!r}: {a['status']} ({a['reason']})")
    print("All checks passed." if not failures else f"{failures} check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
