"""City program databases (data/cities/*.json) and the district checks that decide which programs apply.

Each program may have an `area` rule. Rules test the site against city GIS district layers or site flags:
  {"district": "<key>"}                              site is inside any feature of that layer
  {"district": "<key>", "name_contains": [...]}      ...whose name contains one of these strings
  {"flag": "opportunity_zone"}                       a flag from the HUD lookups is true
  {"any": [rule, ...]}                               any of the rules match
Top-level rules may also set "outside_status" (default "ineligible") and "outside_note".
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "cities"

FLAG_LABELS = {"opportunity_zone": "an Opportunity Zone", "qct": "a Qualified Census Tract"}


def load_cities():
    return {c["place_geoid"]: c for c in (json.loads(p.read_text()) for p in sorted(DATA_DIR.glob("*.json")))}


CITIES = load_cities()
CITIES_BY_ID = {c["id"]: c for c in CITIES.values()}


def supported_names():
    return " and ".join(c["name"] for c in CITIES.values())


def city_for(site):
    return CITIES.get(site.get("place_geoid") or "")


def district_jobs(city):
    """(key, layer_url, field) for every district layer the city's rules use."""
    return [(key, d["url"], d["field"]) for key, d in city["districts"].items()]


def _matches(rule, city, districts, flags):
    """Descriptions of what the site is inside, for this rule; empty if it doesn't match."""
    if "any" in rule:
        return [m for sub in rule["any"] for m in _matches(sub, city, districts, flags)]
    if "flag" in rule:
        return [FLAG_LABELS.get(rule["flag"], rule["flag"])] if flags.get(rule["flag"]) else []
    names = districts.get(rule["district"]) or []
    wanted = rule.get("name_contains")
    if wanted:
        names = [n for n in names if any(w.lower() in n.lower() for w in wanted)]
    layer = city["districts"][rule["district"]]
    template = layer.get("display", "the {name} " + layer["label"])
    return [template.format(name=display_name(n)) for n in names]


def display_name(name):
    """Layer values like "MIZ ... Sub-Districts; Core Sub-District" read better as their last part."""
    name = name.rsplit(";", 1)[-1].strip()
    return name.title() if name.isupper() else name


def district_chips(city, districts):
    """Short labels for every local district the site is inside, for the site summary."""
    chips = []
    for key, names in districts.items():
        layer = city["districts"][key]
        if key == "neighborhood":
            continue
        for n in names:
            if n in layer.get("ignore", []):
                continue
            text = layer.get("display", "the {name} " + layer["label"]).format(name=display_name(n))
            chips.append(text[4:] if text.startswith("the ") else text)
    return chips


def _describe_rule(rule, city):
    if "any" in rule:
        return " or ".join(_describe_rule(r, city) for r in rule["any"])
    if "flag" in rule:
        return FLAG_LABELS.get(rule["flag"], rule["flag"])
    label = city["districts"][rule["district"]]["label"]
    if rule.get("name_contains"):
        return " or ".join(f"the {n}" for n in rule["name_contains"])
    return f"a {label}"


def evaluate(program, city, districts, flags):
    is_requirement = program.get("kind") == "requirement"
    area = program.get("area")
    if not area:
        return program.get("status", "check"), None
    found = _matches(area, city, districts, flags)
    if found:
        return ("applies" if is_requirement else "eligible"), "Site is inside " + _join(found) + "."
    status = area.get("outside_status", "not_applicable" if is_requirement else "ineligible")
    return status, area.get("outside_note") or f"Site is not inside {_describe_rule(area, city)}."


def _join(items):
    items = list(dict.fromkeys(items))
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def match(city, districts, flags):
    out = []
    for p in city["programs"]:
        status, reason = evaluate(p, city, districts, flags)
        out.append({k: v for k, v in p.items() if k not in ("area", "status")} | {"status": status, "reason": reason})
    return out
