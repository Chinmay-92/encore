"""Realistic fixture data for mock mode.

Shapes mirror Qloo responses (entity_id, name, types, properties, popularity,
query.affinity, query.explainability, tags). IDs are synthetic and stable.
These are NOT real Qloo IDs; set QLOO_API_KEY to use the live taste graph.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _id(name: str) -> str:
    h = hashlib.sha1(name.lower().encode()).hexdigest().upper()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _score(*parts: str) -> float:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()
    return int(h[:6], 16) / 0xFFFFFF


def _e(name: str, urn: str, pop: float, tags: list[str], **props: Any) -> dict:
    return {
        "entity_id": _id(name),
        "name": name,
        "types": [urn],
        "subtype": None,
        "popularity": pop,
        "properties": props,
        "tags": [{"id": f"urn:tag:genre:{t.lower().replace(' ', '_')}", "name": t, "type": "urn:tag:genre"} for t in tags],
    }


A, M, T, B, P = "urn:entity:artist", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:book", "urn:entity:place"


def _place(name: str, pop: float, categories: list[str], genres: list[str], **props: Any) -> dict:
    e = _e(name, P, pop, genres, **props)
    e["tags"] = [
        {"id": f"urn:tag:category:place:{c.lower().replace(' ', '_')}", "name": c, "type": "urn:tag:category:place"} for c in categories
    ] + e["tags"]
    if props.get("business_rating", 0) >= 4.5:
        e["tags"].append({"id": "urn:tag:accessibility:place:wheelchair_accessible_entrance", "name": "Wheelchair accessible entrance"})
    return e


CATALOG: list[dict] = [
    # Artists
    _e("Elvis Presley", A, 0.99, ["Rock and Roll", "Rockabilly"], short_description="The King of Rock and Roll"),
    _e("Vera Lynn", A, 0.93, ["Traditional Pop", "Wartime"], short_description="The Forces' Sweetheart"),
    _e("Doris Day", A, 0.94, ["Traditional Pop", "Vocal Jazz"]),
    _e("The Beatles", A, 0.99, ["Rock", "Merseybeat"]),
    _e("Cliff Richard", A, 0.92, ["Rock and Roll", "Pop"]),
    _e("Shirley Bassey", A, 0.93, ["Vocal", "Traditional Pop"]),
    _e("Dusty Springfield", A, 0.91, ["Soul", "Pop"]),
    _e("Frank Sinatra", A, 0.98, ["Vocal Jazz", "Swing"]),
    _e("Matt Monro", A, 0.80, ["Traditional Pop", "Easy Listening"]),
    _e("Petula Clark", A, 0.86, ["Pop", "Chanson"]),
    _e("Tom Jones", A, 0.94, ["Pop", "Soul"]),
    _e("The Shadows", A, 0.85, ["Instrumental Rock", "Surf"]),
    _e("Nat King Cole", A, 0.95, ["Vocal Jazz", "Swing"]),
    _e("Glenn Miller", A, 0.90, ["Big Band", "Swing"]),
    _e("Buddy Holly", A, 0.92, ["Rock and Roll"]),
    _e("Lonnie Donegan", A, 0.74, ["Skiffle"]),
    _e("Julie Andrews", A, 0.88, ["Show Tunes", "Traditional Pop"]),
    _e("Bob Marley & The Wailers", A, 0.98, ["Reggae", "Roots"]),
    _e("Desmond Dekker", A, 0.78, ["Ska", "Rocksteady"]),
    _e("Lord Kitchener", A, 0.66, ["Calypso"]),
    _e("Millie Small", A, 0.70, ["Ska", "Pop"]),
    _e("Lata Mangeshkar", A, 0.95, ["Filmi", "Playback"]),
    _e("Mohammed Rafi", A, 0.93, ["Filmi", "Ghazal"]),
    _e("Kishore Kumar", A, 0.94, ["Filmi", "Playback"]),
    # Movies
    _e("The Sound of Music", M, 0.97, ["Musical", "Family"], release_year=1965, description="A governess brings music to the von Trapp family."),
    _e("Mary Poppins", M, 0.96, ["Musical", "Family"], release_year=1964),
    _e("My Fair Lady", M, 0.92, ["Musical", "Romance"], release_year=1964),
    _e("Brief Encounter", M, 0.84, ["Romance", "Drama"], release_year=1945),
    _e("Genevieve", M, 0.62, ["Comedy"], release_year=1953),
    _e("Oliver!", M, 0.88, ["Musical", "Family"], release_year=1968),
    _e("Calamity Jane", M, 0.80, ["Musical", "Western"], release_year=1953),
    _e("The Italian Job", M, 0.91, ["Comedy", "Caper"], release_year=1969),
    _e("Singin' in the Rain", M, 0.95, ["Musical", "Comedy"], release_year=1952),
    _e("Summer Holiday", M, 0.68, ["Musical", "Comedy"], release_year=1963),
    _e("Carry On Nurse", M, 0.66, ["Comedy"], release_year=1959),
    _e("Roman Holiday", M, 0.92, ["Romance", "Comedy"], release_year=1953),
    _e("Blue Hawaii", M, 0.78, ["Musical", "Romance"], release_year=1961),
    _e("Jailhouse Rock", M, 0.80, ["Musical", "Drama"], release_year=1957),
    _e("The Dam Busters", M, 0.82, ["War", "Drama"], release_year=1955),
    _e("Mughal-e-Azam", M, 0.86, ["Romance", "Historical", "Musical"], release_year=1960),
    _e("Pakeezah", M, 0.78, ["Romance", "Musical"], release_year=1972),
    _e("The Harder They Come", M, 0.74, ["Crime", "Music"], release_year=1972),
    # TV
    _e("Dad's Army", T, 0.86, ["Sitcom"], release_year=1968),
    _e("The Morecambe & Wise Show", T, 0.84, ["Comedy", "Variety"], release_year=1968),
    _e("Coronation Street", T, 0.90, ["Soap"], release_year=1960),
    _e("Fawlty Towers", T, 0.93, ["Sitcom"], release_year=1975),
    _e("Steptoe and Son", T, 0.75, ["Sitcom"], release_year=1962),
    _e("Come Dancing", T, 0.60, ["Ballroom", "Reality"], release_year=1950),
    _e("The Good Old Days", T, 0.55, ["Variety", "Music Hall"], release_year=1953),
    _e("Hancock's Half Hour", T, 0.62, ["Sitcom"], release_year=1956),
    _e("Juke Box Jury", T, 0.52, ["Music", "Panel"], release_year=1959),
    # Books
    _e("Murder on the Orient Express", B, 0.93, ["Mystery", "Crime"], release_year=1934),
    _e("Rebecca", B, 0.90, ["Gothic", "Romance"], release_year=1938),
    _e("All Creatures Great and Small", B, 0.85, ["Memoir", "Countryside"], release_year=1972),
    _e("Cider with Rosie", B, 0.74, ["Memoir", "Countryside"], release_year=1959),
    _e("The Lonely Londoners", B, 0.68, ["Literary Fiction", "Windrush"], release_year=1956),
    # Places (around Brighton & Hove by default; address rewritten to the queried locality).
    # Category tags use real Qloo IDs so default outing filters behave as they do live.
    _place("The Regency Tea Rooms", 0.71, ["Tea house", "Cafe"], ["Afternoon Tea"], address="Seafront", business_rating=4.6, price_level=2),
    _place("Bandstand on the Promenade", 0.66, ["Promenade", "Tourist attraction"], ["Live Music", "Outdoor"], address="Promenade", business_rating=4.5),
    _place("The Palace Pier", 0.83, ["Pier", "Tourist attraction"], ["Seaside", "Fish and Chips"], address="Madeira Drive", business_rating=4.4, price_level=1),
    _place("Grand Ballroom Tea Dance", 0.58, ["Concert hall", "Event venue"], ["Tea Dance", "Live Music"], address="Town Hall", business_rating=4.7, price_level=1),
    _place("Botanic Glasshouse & Garden", 0.69, ["Botanical garden", "Park"], ["Accessible"], address="Park Lane", business_rating=4.8),
    _place("Classic Picture House", 0.64, ["Movie theater"], ["Classic Films", "Dementia Friendly Screenings"], address="High Street", business_rating=4.6, price_level=1),
    _place("Town Museum & Art Gallery", 0.72, ["Museum", "Art gallery"], ["Local History"], address="Church Street", business_rating=4.6),
    _place("Caribbean Kitchen", 0.61, ["Caribbean restaurant", "Restaurant"], [], address="Market Street", business_rating=4.5, price_level=2),
    _place("Spice of Punjab", 0.63, ["Indian restaurant", "Restaurant"], ["Punjabi"], address="Station Road", business_rating=4.4, price_level=2),
    # Unsuitable for these outings; the default filters must keep them out (as live Qloo would return them).
    _place("The Seven Stars", 0.88, ["Pub", "Bar"], ["Live Music"], address="Ship Street", business_rating=4.3, price_level=2),
    _place("Club Neon", 0.85, ["Night club", "Bar"], ["Dance"], address="West Street", business_rating=3.9, price_level=2),
]

BY_NAME = {e["name"].lower(): e for e in CATALOG}
BY_ID = {e["entity_id"]: e for e in CATALOG}

_TAGS = [
    {"id": "urn:tag:category:place:tea_house", "name": "Tea house", "type": "urn:tag:category:place"},
    {"id": "urn:tag:category:place:fish_and_chips_restaurant", "name": "Fish and chips restaurant", "type": "urn:tag:category:place"},
    {"id": "urn:tag:genre:media:musical", "name": "Musical", "type": "urn:tag:genre:media"},
    {"id": "urn:tag:genre:music:big_band", "name": "Big Band", "type": "urn:tag:genre:music"},
    {"id": "urn:tag:category:place:caribbean_restaurant", "name": "Caribbean restaurant", "type": "urn:tag:category:place"},
    {"id": "urn:tag:category:place:indian_restaurant", "name": "Indian restaurant", "type": "urn:tag:category:place"},
    {"id": "urn:tag:category:place:garden", "name": "Garden", "type": "urn:tag:category:place"},
]


def mock_search(query: str, urn: str | None) -> list[dict]:
    q = query.lower().strip()
    hits = [e for e in CATALOG if (q in e["name"].lower() or e["name"].lower() in q) and (urn is None or urn in e["types"])]
    if hits:
        return sorted(hits, key=lambda e: -e["popularity"])
    # Unknown name: synthesise a plausible entity so the flow continues.
    return [_e(query.title(), urn or A, 0.5, [])]


def _year_ok(e: dict, params: dict) -> bool:
    y = e["properties"].get("release_year")
    lo = params.get("filter.release_year.min")
    hi = params.get("filter.release_year.max")
    if y is None:
        return True
    if lo is not None and y < int(lo):
        return False
    if hi is not None and y > int(hi):
        return False
    return True


def _ids(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [x for x in v.split(",") if x]
    return list(v)


def mock_insights(params: dict[str, Any]) -> list[dict]:
    urn = params.get("filter.type", A)
    signal_ids = _ids(params.get("signal.interests.entities"))
    only_ids = set(_ids(params.get("filter.results.entities")))
    exclude_tags = {t.split(":")[-1] for t in _ids(params.get("filter.exclude.tags"))}
    include_tags = set(_ids(params.get("filter.tags")))  # OR semantics, like Qloo's default
    take = int(params.get("take", 10))
    loc = params.get("filter.location.query") or params.get("signal.location.query")
    seed = ",".join(sorted(signal_ids)) + "|" + str(params.get("signal.demographics.age", ""))

    pool = [e for e in CATALOG if urn in e["types"]]
    if only_ids:
        pool = [e for e in CATALOG if e["entity_id"] in only_ids]
    out = []
    for e in pool:
        if e["entity_id"] in signal_ids and not only_ids:
            continue
        if not _year_ok(e, params):
            continue
        if include_tags and not any(t["id"] in include_tags for t in e["tags"]):
            continue
        if exclude_tags and any(t["id"].split(":")[-1] in exclude_tags for t in e["tags"]):
            continue
        # Shared genres with the input signals drive affinity, like a taste graph would.
        sig_tags = {t["name"] for sid in signal_ids for t in BY_ID.get(sid, {}).get("tags", [])}
        overlap = len(sig_tags & {t["name"] for t in e["tags"]})
        affinity = min(0.99, 0.35 + 0.18 * overlap + 0.3 * _score(seed, e["entity_id"]))
        item = {**e, "properties": dict(e["properties"]), "query": {"affinity": affinity}}
        if loc and urn == P:
            item["properties"]["address"] = f"{e['properties'].get('address', '')}, {loc}".strip(", ")
        if params.get("feature.explainability") and signal_ids:
            drivers = sorted(
                ({"entity_id": s, "score": round(0.2 + 0.8 * _score(s, e["entity_id"]), 2)} for s in signal_ids),
                key=lambda d: -d["score"],
            )
            item["query"]["explainability"] = {"signal.interests.entities": drivers}
        out.append(item)
    out.sort(key=lambda e: -e["query"]["affinity"])
    return out[:take]


def mock_tags(query: str, tag_type: str | None = None) -> list[dict]:
    q = query.lower()
    pool = [t for t in _TAGS if tag_type is None or t["type"] == tag_type]
    return [t for t in pool if q in t["name"].lower()] or pool[:3]
