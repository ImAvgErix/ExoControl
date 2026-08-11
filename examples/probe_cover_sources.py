"""Find a keyless source of real portrait poster art for titles Steam lacks."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TERMS = ["VALORANT", "Beast of Reincarnation", "WUCHANG: Fallen Feathers",
         "MECCHA CHAMELEON", "Hollow Knight: Silksong"]


def fetch(url: str, data: bytes | None = None, headers: dict | None = None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def epic_graphql(term: str):
    query = (
        "query searchStoreQuery($keywords: String!) {"
        "  Catalog { searchStore(keywords: $keywords, count: 5, country: \"US\","
        "            locale: \"en-US\") {"
        "    elements { title keyImages { type url } } } } }"
    )
    body = json.dumps({"query": query, "variables": {"keywords": term}}).encode()
    return fetch("https://store.epicgames.com/graphql", body,
                 {"Content-Type": "application/json"})


def epic_get(term: str):
    query = (
        '{Catalog{searchStore(keywords:"%s",count:5,country:"US",locale:"en-US")'
        "{elements{title keyImages{type url}}}}}" % term.replace('"', "")
    )
    url = "https://store.epicgames.com/graphql?query=" + urllib.parse.quote(query)
    return fetch(url)


def show_epic(label, fn):
    print(f"--- {label} ---")
    for term in TERMS:
        try:
            data = fn(term)
        except Exception as e:
            print(f"  {term}: ERROR {e}")
            continue
        try:
            els = data["data"]["Catalog"]["searchStore"]["elements"]
        except Exception:
            print(f"  {term}: unexpected shape {str(data)[:120]}")
            continue
        if not els:
            print(f"  {term}: no results")
            continue
        el = els[0]
        talls = [k for k in el["keyImages"] if "Tall" in k["type"]]
        print(f"  {term} -> {el['title'][:32]!r} tall={len(talls)}")
        for k in talls[:1]:
            print(f"      {k['type']}: {k['url'][:110]}")


def steamgriddb_public():
    """Confirm whether SteamGridDB needs a key."""
    print("--- steamgriddb (keyless attempt) ---")
    try:
        fetch("https://www.steamgriddb.com/api/v2/grids/steam/2001760?dimensions=600x900")
        print("  keyless works")
    except Exception as e:
        print(f"  keyless blocked: {e}")


if __name__ == "__main__":
    show_epic("epic graphql POST", epic_graphql)
    show_epic("epic graphql GET", epic_get)
    steamgriddb_public()
