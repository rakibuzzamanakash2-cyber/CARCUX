"""Build app/data/bd_gazetteer.json, the place list used to put news items on the map.

Sources:
- Districts (with coordinates), divisions and upazilas, English and Bangla names:
  nuhil/bangladesh-geocode (MIT License, (c) 2014 Nuhil Mehdy),
  https://github.com/nuhil/bangladesh-geocode
- City localities: approximate centres added by CARCUX (precision 2.5 km).

Run from backend/:  python scripts/build_gazetteer.py <dir with districts.json etc.>
The three input files are the repository's districts/, divisions/ and upazilas/ JSON.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "bd_gazetteer.json"

# Names after the 2018 spelling changes, plus older and common spellings.
DISTRICT_ALIASES = {
    "Chattogram": ["Chittagong", "Ctg"],
    "Comilla": ["Cumilla"],
    "Barisal": ["Barishal"],
    "Jashore": ["Jessore"],
    "Bogura": ["Bogra"],
    "Coxsbazar": ["Cox's Bazar", "Coxs Bazar", "Cox’s Bazar"],
    "Jhalakathi": ["Jhalokati", "Jhalokathi"],
    "Chapainawabganj": ["Chapai Nawabganj", "Chapainababganj"],
    "Netrokona": ["Netrakona"],
    "Moulvibazar": ["Maulvibazar"],
    "Khagrachhari": ["Khagrachari"],
    "Lakshmipur": ["Laxmipur"],
}
DISTRICT_DISPLAY = {"Coxsbazar": "Cox's Bazar", "Barisal": "Barishal", "Comilla": "Cumilla"}
DIVISION_DISPLAY = {"Chattagram": "Chattogram", "Barisal": "Barishal"}
DIVISION_ALIASES = {"Chattagram": ["Chittagong", "Chattogram"], "Barisal": ["Barishal"]}

# Upazila names that are also districts, Dhaka localities, ordinary words, or too
# short to match safely are left out; so are names shared by several upazilas.
UPAZILA_SKIP = {"Mirpur", "Sadarsouth", "Companiganj", "Nawabganj", "Kaliganj"}

# (name, aliases, bangla, district, lat, lon): approximate centres.
LOCALITIES = [
    ("Mirpur", ["Mirpur 10", "Mirpur-10"], "মিরপুর", "Dhaka", 23.807, 90.368),
    ("Dhanmondi", [], "ধানমন্ডি", "Dhaka", 23.746, 90.374),
    ("Mohammadpur", [], "মোহাম্মদপুর", "Dhaka", 23.766, 90.358),
    ("Uttara", [], "উত্তরা", "Dhaka", 23.874, 90.398),
    ("Gulshan", [], "গুলশান", "Dhaka", 23.792, 90.416),
    ("Banani", [], "বনানী", "Dhaka", 23.794, 90.404),
    ("Motijheel", [], "মতিঝিল", "Dhaka", 23.733, 90.418),
    ("Jatrabari", [], "যাত্রাবাড়ী", "Dhaka", 23.710, 90.434),
    ("Badda", [], "বাড্ডা", "Dhaka", 23.780, 90.426),
    ("Tejgaon", [], "তেজগাঁও", "Dhaka", 23.763, 90.393),
    ("Farmgate", [], "ফার্মগেট", "Dhaka", 23.757, 90.389),
    ("Shantinagar", [], "শান্তিনগর", "Dhaka", 23.739, 90.413),
    ("Malibagh", [], "মালিবাগ", "Dhaka", 23.749, 90.413),
    ("Rampura", [], "রামপুরা", "Dhaka", 23.762, 90.421),
    ("Old Dhaka", ["Puran Dhaka"], "পুরান ঢাকা", "Dhaka", 23.711, 90.407),
    ("Mohakhali", [], "মহাখালী", "Dhaka", 23.778, 90.400),
    ("Karwan Bazar", ["Kawran Bazar", "Kawran Bazaar"], "কারওয়ান বাজার", "Dhaka", 23.751, 90.393),
    ("Shahbagh", [], "শাহবাগ", "Dhaka", 23.738, 90.395),
    ("Azimpur", [], "আজিমপুর", "Dhaka", 23.728, 90.385),
    ("Khilgaon", [], "খিলগাঁও", "Dhaka", 23.752, 90.426),
    ("Agrabad", [], "আগ্রাবাদ", "Chattogram", 22.325, 91.811),
    ("Muradpur", [], "মুরাদপুর", "Chattogram", 22.367, 91.837),
    ("Bahaddarhat", [], "বহদ্দারহাট", "Chattogram", 22.369, 91.846),
    ("Chawkbazar", ["Chowkbazar"], "চকবাজার", "Chattogram", 22.350, 91.838),
    ("Halishahar", [], "হালিশহর", "Chattogram", 22.327, 91.786),
]


def table(path: Path) -> list[dict]:
    return next(x for x in json.loads(path.read_text()) if x.get("type") == "table")["data"]


def main(src: Path) -> None:
    divisions = table(src / "divisions.json")
    districts = table(src / "districts.json")
    upazilas = table(src / "upazilas.json")

    div_name = {d["id"]: DIVISION_DISPLAY.get(d["name"], d["name"]) for d in divisions}
    by_div = defaultdict(list)
    dist_out = []
    dist_by_id = {}
    for d in districts:
        lat, lon = round(float(d["lat"]), 4), round(float(d["lon"]), 4)
        name = DISTRICT_DISPLAY.get(d["name"], d["name"])
        aliases = sorted({d["name"], *DISTRICT_ALIASES.get(d["name"], [])} - {name})
        row = {
            "name": name,
            "aliases": aliases,
            "bn": d["bn_name"],
            "division": div_name[d["division_id"]],
            "lat": lat,
            "lon": lon,
        }
        dist_out.append(row)
        dist_by_id[d["id"]] = row
        by_div[d["division_id"]].append((lat, lon))

    div_out = []
    for d in divisions:
        pts = by_div[d["id"]]
        name = div_name[d["id"]]
        div_out.append(
            {
                "name": name,
                "aliases": sorted(set(DIVISION_ALIASES.get(d["name"], [])) - {name}),
                "bn": d["bn_name"],
                "lat": round(sum(p[0] for p in pts) / len(pts), 4),
                "lon": round(sum(p[1] for p in pts) / len(pts), 4),
            }
        )

    district_names = {r["name"].lower() for r in dist_out} | {
        a.lower() for r in dist_out for a in r["aliases"]
    }
    counts = Counter(u["name"] for u in upazilas)
    upa_out = []
    for u in upazilas:
        name = u["name"]
        if (
            counts[name] > 1
            or name in UPAZILA_SKIP
            or "Sadar" in name
            or len(name) < 5
            or name.lower() in district_names
        ):
            continue
        dist = dist_by_id[u["district_id"]]
        upa_out.append({"name": name, "bn": u["bn_name"], "district": dist["name"]})

    loc_out = [
        {"name": n, "aliases": a, "bn": bn, "district": dist, "lat": lat, "lon": lon}
        for n, a, bn, dist, lat, lon in LOCALITIES
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "credits": "Districts, divisions, upazilas: nuhil/bangladesh-geocode (MIT). "
                "Localities: approximate centres by CARCUX.",
                "divisions": div_out,
                "districts": sorted(dist_out, key=lambda r: r["name"]),
                "upazilas": sorted(upa_out, key=lambda r: r["name"]),
                "localities": loc_out,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(
        f"{OUT}: {len(div_out)} divisions, {len(dist_out)} districts, "
        f"{len(upa_out)} upazilas, {len(loc_out)} localities"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
