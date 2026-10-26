"""Site lookups against free public data: Census geocoder, HUD eGIS layers, Census ACS."""

import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import cities

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
HUD_ARCGIS = "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services"
ACS_URL = "https://api.census.gov/data/2023/acs/acs5"

HUD_LAYERS = {
    "qct": "QUALIFIED_CENSUS_TRACTS_2026/FeatureServer/0",
    "dda": "Difficult_Development_Areas_2026/FeatureServer/0",
    "opportunity_zone": "Opportunity_Zones/FeatureServer/13",
    "promise_zone": "Promise_Zones/FeatureServer/14",
    "fmr": "Fair_Market_Rents/FeatureServer/0",
}
LIHTC_LAYER = "LIHTC/FeatureServer/0"
NEARBY_RADIUS_METERS = 1609  # one mile


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


def _acs_tract_stats(state_fips, county_fips, tract_code):
    """Poverty rate and median family income for NMTC screening. Needs CENSUS_API_KEY."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        return None
    rows = _get_json(ACS_URL, {
        "get": "B17001_001E,B17001_002E,B19113_001E,B01003_001E",
        "for": f"tract:{tract_code}",
        "in": f"state:{state_fips} county:{county_fips}",
        "key": key,
    })
    header, values = rows[0], rows[1]
    r = dict(zip(header, values))
    total, below = float(r["B17001_001E"] or 0), float(r["B17001_002E"] or 0)
    mfi = float(r["B19113_001E"]) if r["B19113_001E"] not in (None, "", "-666666666") else None
    return {
        "population": int(float(r["B01003_001E"] or 0)),
        "poverty_rate": round(below / total * 100, 1) if total else None,
        "median_family_income": mfi if mfi and mfi > 0 else None,
    }


def lookup_site(address):
    site = geocode(address)
    city = cities.city_for(site)
    if city is None:
        where = ", ".join(x for x in (site.get("city"), site.get("state_abbr")) if x) or "an unsupported area"
        raise LookupError_(f"This tool covers {cities.supported_names()} only. That address is in {where}.")
    lon, lat = site["lon"], site["lat"]

    jobs = {name: (_point_query, (layer, lon, lat)) for name, layer in HUD_LAYERS.items()}
    jobs["nearby_lihtc"] = (_nearby_lihtc, (lon, lat))
    for key, url, field in cities.district_jobs(city):
        jobs["district:" + key] = (_district_names, (url, field, lon, lat))
    if site["tract_code"]:
        jobs["acs"] = (_acs_tract_stats, (site["state_fips"], site["county_fips"], site["tract_code"]))

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
        "tract_stats": results.get("acs"),
        "nearby_lihtc": results.get("nearby_lihtc", []),
        "errors": errors,
    }
