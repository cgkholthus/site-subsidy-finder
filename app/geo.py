"""Site lookups against free public data: Census geocoder, HUD eGIS layers and city GIS layers."""

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import cities

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
HUD_ARCGIS = "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services"

HUD_LAYERS = {
    "qct": "QUALIFIED_CENSUS_TRACTS_2026/FeatureServer/0",
    "dda": "Difficult_Development_Areas_2026/FeatureServer/0",
    "opportunity_zone": "Opportunity_Zones/FeatureServer/13",
    "promise_zone": "Promise_Zones/FeatureServer/14",
    "fmr": "Fair_Market_Rents/FeatureServer/0",
}
LIHTC_LAYER = "LIHTC/FeatureServer/0"

# Address autocomplete: each city's own official address data.
NOLA_ADDRESSES = "https://maps.nola.gov/server/rest/services/Addresses/Site_Address_Point/MapServer/0/query"
PDX_SUGGEST = "https://www.portlandmaps.com/arcgis/rest/services/Public/Address_Geocoding_PDX/GeocodeServer/suggest"
MAX_SUGGESTIONS = 5
NEARBY_RADIUS_METERS = 1609  # one mile

# National Park Service's National Register points. Their locations are approximate (often +/- 12 m or more),
# so a listing only counts when its street address matches the site's address, not just because it's nearby.
NPS_NRHP_POINTS = "https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/0/query"
NRHP_SEARCH_METERS = 150
STREET_WORDS = {"SAINT": "ST", "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD",
                "PLACE": "PL", "COURT": "CT", "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
                "NORTHWEST": "NW", "NORTHEAST": "NE", "SOUTHWEST": "SW", "SOUTHEAST": "SE"}
STREET_NOISE = {"ST", "AVE", "BLVD", "DR", "RD", "PL", "CT", "PKWY", "N", "S", "E", "W", "NW", "NE", "SW", "SE", "WAY", "LN", "HWY"}


class LookupError_(Exception):
    pass


def _get_json(url, params, timeout=30):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "affordable-housing-research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(address):
    data = _get_json(CENSUS_GEOCODER, {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    })
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise LookupError_("No match for that address. Try including street, city, state and ZIP.")
    m = matches[0]
    geos = m["geographies"]

    def first(layer):
        items = geos.get(layer) or []
        return items[0] if items else None

    state = first("States") or {}
    county = first("Counties") or {}
    tract = first("Census Tracts") or {}
    place = first("Incorporated Places")
    subdivision = first("County Subdivisions")
    urban = first("Urban Areas")
    district = first("120th Congressional Districts")
    return {
        "matched_address": m["matchedAddress"],
        "lon": m["coordinates"]["x"],
        "lat": m["coordinates"]["y"],
        "zip": m.get("addressComponents", {}).get("zip"),
        "state_name": state.get("NAME"),
        "state_abbr": state.get("STUSAB"),
        "state_fips": state.get("STATE"),
        "county_name": county.get("NAME"),
        "county_fips": county.get("COUNTY"),
        "tract_geoid": tract.get("GEOID"),
        "tract_name": tract.get("NAME"),
        "tract_code": tract.get("TRACT"),
        # Unincorporated sites have no place; fall back to the county subdivision (township etc).
        "city": (place or {}).get("NAME") or (subdivision or {}).get("NAME"),
        "place_geoid": (place or {}).get("GEOID"),
        "incorporated": place is not None,
        "urban_area": (urban or {}).get("NAME"),
        "congressional_district": (district or {}).get("NAME"),
    }


def _point_query(layer, lon, lat, extra=None):
    params = {
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    params.update(extra or {})
    data = _get_json(f"{HUD_ARCGIS}/{layer}/query", params)
    if "error" in data:
        raise LookupError_(data["error"].get("message", "HUD query failed"))
    return [f["attributes"] for f in data.get("features", [])]


def _district_names(layer_url, field, lon, lat):
    """Names of the city district features (TIF, historic, zoning overlay...) that contain the point."""
    data = _get_json(f"{layer_url}/query", {
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": field,
        "returnGeometry": "false",
        "f": "json",
    })
    if "error" in data:
        raise LookupError_(data["error"].get("message", "City map query failed"))
    names = [str(f["attributes"].get(field) or "").strip() for f in data.get("features", [])]
    return sorted({n for n in names if n})


def _street_key(text):
    """Distinctive words of a street name, e.g. "St. Charles Ave." -> ("CHARLES",), "SW 3RD AVE" -> ("3RD",)."""
    words = [STREET_WORDS.get(w, w) for w in re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split()]
    return tuple(w for w in words if w not in STREET_NOISE)


def _split_address(text):
    """("920, 924-928 SW 3rd Ave.") -> ({920, 924, 925, 926, 927, 928}, street key)."""
    m = re.match(r"^\s*([\d\s,&\-–and]+?)\s+([A-Za-z].*)$", text or "")
    if not m:
        return set(), ()
    numbers = set()
    for part in re.split(r"[,&]|\band\b", m.group(1)):
        bounds = [int(n) for n in re.findall(r"\d+", part)]
        if len(bounds) == 2 and 0 <= bounds[1] - bounds[0] <= 200:
            numbers.update(range(bounds[0], bounds[1] + 1))
        else:
            numbers.update(bounds)
    return numbers, _street_key(m.group(2))


def _nrhp_listings(site):
    """National Register listings whose address matches the site (individually listed buildings and structures)."""
    number, street = _split_address(site["matched_address"].split(",")[0])
    if not number or not street:
        return []
    data = _get_json(NPS_NRHP_POINTS, {
        "geometry": json.dumps({"x": site["lon"], "y": site["lat"], "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "distance": NRHP_SEARCH_METERS,
        "units": "esriSRUnit_Meter",
        "outFields": "RESNAME,ResType,Address,NRIS_Refnum,CertDate,Is_NHL,NARA_URL,STATUS",
        "returnGeometry": "false",
        "f": "json",
    }, timeout=15)
    if "error" in data:
        raise LookupError_(data["error"].get("message", "National Register query failed"))
    found = []
    for f in data.get("features", []):
        a = f["attributes"]
        if (a.get("ResType") or "").lower() == "district" or (a.get("STATUS") or "Listed") != "Listed":
            continue
        numbers, key = _split_address(a.get("Address") or "")
        if number & numbers and key == street:
            found.append({
                "name": a.get("RESNAME"),
                "reference_number": a.get("NRIS_Refnum"),
                "listed": (a.get("CertDate") or "")[:4] or None,
                "national_historic_landmark": (a.get("Is_NHL") or "").strip().upper() == "X",
                "record_url": a.get("NARA_URL"),
            })
    return found


def _nearby_lihtc(lon, lat):
    params = {
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "distance": NEARBY_RADIUS_METERS,
        "units": "esriSRUnit_Meter",
        "outFields": "PROJECT,PROJ_ADD,PROJ_CTY,N_UNITS,LI_UNITS,YR_PIS,BOND,HOME,CDBG,NON_PROF",
        "returnGeometry": "true",
        "outSR": 4326,
        "resultRecordCount": 200,
        "f": "json",
    }
    data = _get_json(f"{HUD_ARCGIS}/{LIHTC_LAYER}/query", params)
    if "error" in data:
        raise LookupError_(data["error"].get("message", "HUD query failed"))
    out = []
    for f in data.get("features", []):
        a = f["attributes"]
        g = f.get("geometry") or {}
        out.append({
            "name": a.get("PROJECT"),
            "address": a.get("PROJ_ADD"),
            "units": a.get("N_UNITS"),
            "low_income_units": a.get("LI_UNITS"),
            "year_placed_in_service": a.get("YR_PIS"),
            "bond_financed": a.get("BOND") == 1,
            "home_funds": a.get("HOME") == 1,
            "cdbg_funds": a.get("CDBG") == 1,
            "nonprofit_sponsor": a.get("NON_PROF") == 1,
            "lat": g.get("y"),
            "lon": g.get("x"),
        })
    out.sort(key=lambda p: -(p["units"] or 0))
    return out


def lookup_site(address):
    site = geocode(address)
    city = cities.city_for(site)
    if city is None:
        where = ", ".join(x for x in (site.get("city"), site.get("state_abbr")) if x) or "an unsupported area"
        raise LookupError_(f"This tool covers {cities.supported_names()} only. That address is in {where}.")
    lon, lat = site["lon"], site["lat"]

    jobs = {name: (_point_query, (layer, lon, lat)) for name, layer in HUD_LAYERS.items()}
    jobs["nearby_lihtc"] = (_nearby_lihtc, (lon, lat))
    jobs["nrhp"] = (_nrhp_listings, (site,))
    for key, url, field in cities.district_jobs(city):
        jobs["district:" + key] = (_district_names, (url, field, lon, lat))

    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(fn, *args) for name, (fn, args) in jobs.items()}
        for name, fut in futures.items():
            try:
                results[name] = fut.result()
            except Exception as e:  # one failed layer shouldn't sink the whole lookup
                errors[name] = str(e)

    dda_rows = results.get("dda") or []
    fmr_rows = results.get("fmr") or []
    pz_rows = results.get("promise_zone") or []
    oz_rows = results.get("opportunity_zone") or []
    flags = {
        "qct": bool(results.get("qct")) if "qct" in results else None,
        "dda": bool(dda_rows) if "dda" in results else None,
        "dda_name": dda_rows[0].get("DDA_NAME") if dda_rows else None,
        "opportunity_zone": bool(oz_rows) if "opportunity_zone" in results else None,
        "promise_zone": pz_rows[0].get("COMMUNITY") if pz_rows else None,
        "rural": site["urban_area"] is None,
        # Name of the individually listed National Register building at this address, if any.
        "nr_listed": (results.get("nrhp") or [{}])[0].get("name"),
    }
    fmr = None
    if fmr_rows:
        r = fmr_rows[0]
        fmr = {
            "area": r.get("FMR_AREANAME"),
            "studio": r.get("FMR_0BDR"), "one_br": r.get("FMR_1BDR"), "two_br": r.get("FMR_2BDR"),
            "three_br": r.get("FMR_3BDR"), "four_br": r.get("FMR_4BDR"),
        }
    districts = {key: results.get("district:" + key, []) for key in city["districts"]}
    return {
        "site": site,
        "city": city,
        "districts": districts,
        "flags": flags,
        "fair_market_rents": fmr,
        "nearby_lihtc": results.get("nearby_lihtc", []),
        "nr_listings": results.get("nrhp", []),
        "errors": errors,
    }


def _clean_query(text):
    """Keep letters, digits and a few address characters; anything else could break a map query."""
    return re.sub(r"[^A-Za-z0-9 #.,'-]", "", text).strip()[:80]


def _nola_suggest(text):
    street = re.split(r",", text)[0].strip().upper().replace("'", "''")
    if not re.match(r"^\d", street):
        return []
    variants = [street]
    if re.search(r"\bST\b", street):  # "St Claude" is stored as "Saint Claude"
        variants.append(re.sub(r"\bST\b(?=\s+[A-Z])", "SAINT", street, count=1))
    where = " OR ".join(f"UPPER(FULLADDR) LIKE '{v}%'" for v in variants)
    data = _get_json(NOLA_ADDRESSES, {
        "where": f"({where}) AND UNITID IS NULL AND STATUS = 'Current'",
        "outFields": "FULLADDR",
        "returnGeometry": "false",
        "returnDistinctValues": "true",
        "orderByFields": "FULLADDR",
        "resultRecordCount": MAX_SUGGESTIONS,
        "f": "json",
    }, timeout=8)
    return [f"{f['attributes']['FULLADDR']}, New Orleans, LA" for f in data.get("features", [])]


def _pdx_suggest(text):
    if not re.match(r"^\d", text):
        return []
    data = _get_json(PDX_SUGGEST, {"text": text, "maxSuggestions": MAX_SUGGESTIONS, "f": "json"}, timeout=8)
    # The service also covers suburbs (West Linn, Gresham...); only Portland addresses are supported here.
    return [s["text"] for s in data.get("suggestions", [])
            if not s.get("isCollection") and ", portland, or" in s["text"].lower()]


def suggest(text):
    """Address suggestions from New Orleans and Portland as the user types (needs a house number first)."""
    text = _clean_query(text)
    if len(text) < 4 or not re.match(r"^\d+\s+\S", text):
        return []
    lower = text.lower()
    sources = []
    if "portland" not in lower and " or" not in lower:
        sources.append(_nola_suggest)
    if "new orleans" not in lower and " la" not in lower:
        sources.append(_pdx_suggest)
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for fut in [pool.submit(fn, text) for fn in sources]:
            try:
                results.extend(fut.result())
            except Exception:
                pass  # one city's service being slow or down shouldn't block the other
    return results[: MAX_SUGGESTIONS * 2]
