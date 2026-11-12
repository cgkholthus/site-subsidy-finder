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

import project as proj

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "cities"

FLAG_LABELS = {"opportunity_zone": "an Opportunity Zone", "qct": "a Qualified Census Tract",
               "nr_listed": "a building individually listed on the National Register"}


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
        value = flags.get(rule["flag"])
        if not value:
            return []
        if rule["flag"] == "nr_listed":  # the flag holds the building's name
            return [f"the {value} building, which is individually listed on the National Register"]
        return [FLAG_LABELS.get(rule["flag"], rule["flag"])]
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


def _about(layer, name):
    """Explanation for one district: a name-specific note, then a name pattern, then the layer's general text."""
    shown = display_name(name)
    for key, info in (layer.get("names") or {}).items():
        if key.lower() in shown.lower():
            return info
    for pattern in layer.get("patterns") or []:
        if pattern["contains"].lower() in shown.lower():
            return pattern
    return layer.get("about")


def district_chips(city, districts):
    """Every local district the site is inside, with a short label and an explanation for the site summary."""
    chips = []
    for key, names in districts.items():
        layer = city["districts"][key]
        if key == "neighborhood":
            continue
        for n in names:
            if n in layer.get("ignore", []):
                continue
            text = layer.get("display", "the {name} " + layer["label"]).format(name=display_name(n))
            info = _about(layer, n) or {}
            chips.append({
                "label": text[4:] if text.startswith("the ") else text,
                "on": True,
                "title": info.get("title"),
                "text": info.get("text"),
                "meaning": info.get("meaning"),
                "url": info.get("url"),
            })
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


def location_result(program, city, districts, flags):
    """("yes" | "no" | "maybe" | "na", note) for the program's area rule; see project.combine."""
    area = program.get("area")
    if not area:
        return ("yes" if program.get("status") == "eligible" else "na"), None
    found = _matches(area, city, districts, flags)
    if found:
        return "yes", "Site is inside " + _join(found) + "."
    outside = "maybe" if area.get("outside_status") == "check" else "no"
    return outside, area.get("outside_note") or f"Site is not inside {_describe_rule(area, city)}."


def _join(items):
    items = list(dict.fromkeys(items))
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def agency(city, agency_id):
    """Contact details for an agency in the city's directory, or None."""
    info = (city.get("agencies") or {}).get(agency_id or "")
    return {"id": agency_id, **info} if info else None


def match(city, districts, flags, project=None):
    out = []
    for p in city["programs"]:
        location, note = location_result(p, city, districts, flags)
        rules = p.get("project_rules", [])
        status, reason = proj.combine(location, note, rules, project or {},
                                      is_requirement=p.get("kind") == "requirement", best=p.get("best_status", "eligible"))
        hidden = ("area", "status", "project_rules", "best_status", "contact")
        out.append({k: v for k, v in p.items() if k not in hidden} | {
            "status": status, "reason": reason,
            # True when the "yes" rests on the project answers too, not just the location.
            "project_checked": proj.evaluate(rules, project or {})[0] == "pass",
            "contact": agency(city, p.get("contact")),
            "last_reviewed": city.get("last_reviewed"),
        })
    return out
