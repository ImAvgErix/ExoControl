"""Check Epic catalog portrait coverage + download samples for visual review."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
OUT = Path(r"C:\Users\Erix\AppData\Local\Temp\epic-art")


def search(term: str):
    query = (
        '{Catalog{searchStore(keywords:"%s",count:8,country:"US",locale:"en-US")'
        "{elements{title keyImages{type url}}}}}" % term.replace('"', "")
    )
    url = "https://store.epicgames.com/graphql?query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    return data["data"]["Catalog"]["searchStore"]["elements"]


def norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()


def best_tall(term: str):
    try:
        els = search(term)
    except Exception as e:
        return None, f"ERROR {e}"
    want = norm(term)
    for el in els:
        if norm(el["title"]) != want:
            continue
        for k in el["keyImages"]:
            if "Tall" in k["type"]:
                return k["url"], el["title"]
    # no exact title match
    if els:
        return None, f"no exact match (top: {els[0]['title']!r})"
    return None, "no results"


TITLES = [
    "VALORANT", "League of Legends", "Teamfight Tactics", "Legends of Runeterra",
    "Beast of Reincarnation", "MECCHA CHAMELEON", "WUCHANG: Fallen Feathers",
    "Counter-Strike 2", "Deadlock", "God of War", "Marvel Rivals", "Mortal Shell",
    "NBA 2K26", "Rocket League", "Thymesia", "Species: Unknown", "Storm Striker",
]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    hits = 0
    for t in TITLES:
        url, why = best_tall(t)
        if url:
            hits += 1
            safe = "".join(c if c.isalnum() else "_" for c in t) + ".jpg"
            try:
                req = urllib.request.Request(url + "?h=900&w=600&resize=1&quality=high",
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=25) as r:
                    (OUT / safe).write_bytes(r.read())
                size = (OUT / safe).stat().st_size
                print(f"  OK   {t:<26} {size//1024:>4} KB  {why}")
            except Exception as e:
                print(f"  DL   {t:<26} failed {e}")
        else:
            print(f"  --   {t:<26} {why}")
    print(f"\nportrait art found for {hits}/{len(TITLES)}")
    print("saved to", OUT)
