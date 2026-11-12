"""Project details from the "About your project" form, and the rules programs use to check them.

A program's `project_rules` is a list of checks; each names a form field and says what passes:
  {"field": "tenure", "is": "rental", "fail": "Rental housing only."}
  {"field": "construction", "in": ["new", "rehab"], "fail": "..."}
  {"field": "units", "min": 10, "fail": "..."}            (also "max")
  {"field": "ami", "max": 60, "fail": "..."}              highest income limit for the affordable units, % of AMI
  {"field": "owner", "is": "nonprofit", "fail": "..."}
  {"field": "populations", "has": "seniors", "fail": "..."}
  {"field": "commercial", "is": true, "fail": "..."}
A rule whose field the user left blank can't be decided, so the program stays "Check eligibility".
"""

FIELDS = {
    "tenure": {"rental", "ownership"},
    "construction": {"new", "rehab"},
    "owner": {"nonprofit", "forprofit"},
    "commercial": {"yes", "no"},
}
AMI_LEVELS = {30, 50, 60, 80, 120}
POPULATIONS = {"seniors", "disability", "homeless"}


def parse(raw):
    """Clean the form values from the browser; anything unrecognized is treated as unanswered."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for field, allowed in FIELDS.items():
        value = str(raw.get(field) or "").strip().lower()
        if value in allowed:
            out[field] = value
    if "commercial" in out:
        out["commercial"] = out["commercial"] == "yes"
    try:
        units = int(raw.get("units"))
        if 1 <= units <= 10_000:
            out["units"] = units
    except (TypeError, ValueError):
        pass
    try:
        ami = int(raw.get("ami"))
        if ami in AMI_LEVELS:
            out["ami"] = ami
    except (TypeError, ValueError):
        pass
    # The browser only sends populations once a box (including "None of these") is checked,
    # so an empty list means "none" and a missing key means "not answered".
    pops = raw.get("populations")
    if isinstance(pops, list):
        out["populations"] = sorted({p for p in pops if p in POPULATIONS})
    return out


def _check(rule, project):
    """True (passes), False (fails) or None (field not answered)."""
    value = project.get(rule["field"])
    if value is None:
        return None
    if "is" in rule:
        return value == rule["is"]
    if "in" in rule:
        return value in rule["in"]
    if "has" in rule:
        return rule["has"] in value
    if "min" in rule and value < rule["min"]:
        return False
    if "max" in rule and value > rule["max"]:
        return False
    return True


def evaluate(rules, project):
    """("pass" | "fail" | "unknown", [failure messages])."""
    if not rules or not project:
        return "unknown", []
    results = [(_check(r, project), r) for r in rules]
    failures = [r["fail"] for ok, r in results if ok is False]
    if failures:
        return "fail", failures
    if any(ok is None for ok, _ in results):
        return "unknown", []
    return "pass", []


def combine(location, location_note, rules, project, is_requirement=False, best="eligible"):
    """Final status and reason from the location result and the project rules.

    location: "yes" (site meets the location test), "no" (it doesn't), "maybe" (can't tell from maps),
              or "na" (the program has no location test).
    best: the highest status the program can reach, e.g. "check" when it needs something the form
          doesn't ask about (like an existing tax credit award).
    """
    outcome, failures = evaluate(rules, project)
    yes, no = ("applies", "not_applicable") if is_requirement else ("eligible", "ineligible")

    if location == "no":
        return no, location_note
    if outcome == "fail":
        return no, " ".join(failures)

    if location == "yes":
        status = yes  # the site qualifies; unanswered project questions don't take that away
    elif location == "na" and outcome == "pass":
        status = yes
    else:
        status = "check"
    if best == "check" and status == yes:
        status = "check"

    if outcome == "pass" and status == yes:
        extra = "Your project details meet the published requirements."
        return status, f"{location_note} {extra}" if location_note else extra
    return status, location_note
