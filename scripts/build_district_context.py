import json
from pathlib import Path
import pandas as pd

SOIL = Path("data/processed/soil_district_summary.csv")
CROP = Path("data/processed/district_crop_profile.csv")
WEATHER = Path("data/processed/weather_power_telangana_profile.csv")
POINTS = Path("data/processed/district_points.csv")
OUT_DIR = Path("data/processed/context")
AUDIT = Path("data/audits/district_context_audit.txt")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SHOW_CODE = 516      # Nizamabad
TOP_N = 8

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

soil = pd.read_csv(SOIL, low_memory=False)
crop = pd.read_csv(CROP)
wx = pd.read_csv(WEATHER)
pts = pd.read_csv(POINTS)
pts = pts[pts["state_name"] == "Telangana"].sort_values("dtcode")

def recs(df):
    return json.loads(df.to_json(orient="records"))

vcols = ["monsoon_mm_mean", "annual_mm_mean", "t2m_mean_c",
         "tmax_mar_may_c", "tmin_dec_feb_c", "rh_jun_sep_pct"]
wx["grid_key"] = wx[vcols].astype(str).agg("|".join, axis=1)
groups = wx.groupby("grid_key")["district"].apply(list)

NOTES = [
    "Soil: Soil Health Card records; values are counts of records per class "
    "(share of samples), not measured nutrient concentrations. Farmer-requested "
    "samples, not a random sample.",
    "Crops: DES district statistics, 2018-19 to 2022-23; reported government "
    "statistics. Yields are production-weighted. Coconut is in nuts, not tonnes.",
    "Weather: NASA POWER modelled grid data (about 50 km cells), 2018-2023; "
    "not station measurements. Neighbouring districts can share one grid cell.",
    "No suitability score, fertiliser quantity or recommendation is included.",
]

cards, rows, problems = {}, [], []
for p in pts.itertuples():
    code = int(p.dtcode)
    card = {"district": p.district, "state": p.state_name, "district_code": code,
            "point": {"lat": round(float(p.lat), 4), "lon": round(float(p.lon), 4)},
            "approx_area_km2": float(p.approx_area_km2)}

    # ---- soil ----
    s = soil[soil["district_code"] == code]
    soil_year, soil_block = None, []
    if len(s):
        soil_year = sorted(s["year"].astype(str).unique())[-1]
        s = s[s["year"].astype(str) == soil_year]
        for nut, g in s.groupby("nutrient_name"):
            g = g.sort_values("pct_of_nutrient_samples", ascending=False)
            n_total = float(g["n_total"].iloc[0])
            levels = {}
            for r in g.itertuples():
                v = r.pct_of_nutrient_samples
                levels[r.nutrient_level] = None if pd.isna(v) else float(v)
            soil_block.append({
                "nutrient": nut,
                "samples": int(n_total),
                "low_sample_flag": bool(g["low_sample_flag"].iloc[0]),
                "levels_pct": levels,
                "most_common_level": g["nutrient_level"].iloc[0] if n_total > 0 else None,
            })
            if n_total < 100:
                problems.append((p.district, nut, int(n_total)))
    card["soil"] = {"year": soil_year, "nutrients": soil_block}

    # ---- crops ----
    c = crop[crop["district_code"] == code]
    keep = ["crop_name", "crop_type", "years_with_area", "mean_area_ha",
            "pct_of_district_season_area", "years_with_yield",
            "weighted_yield_t_per_ha", "weighted_yield_nuts_per_ha",
            "min_yield_t_per_ha", "max_yield_t_per_ha", "data_coverage",
            "years_flagged_for_review"]
    keep = [k for k in keep if k in c.columns]
    seasons = {}
    for season, g in c.groupby("season"):
        g = g.sort_values("mean_area_ha", ascending=False).head(TOP_N)
        seasons[season] = recs(g[keep])
    card["crops"] = {"window": "2018-19 to 2022-23", "seasons": seasons}

    # ---- weather ----
    w = wx[wx["dtcode"] == code]
    shared = []
    if len(w):
        r = w.iloc[0]
        shared = [d for d in groups[r["grid_key"]] if d != p.district]
        card["weather"] = {"source": "NASA POWER (modelled)", "period": "2018-2023",
                           "values": {k: float(r[k]) for k in vcols},
                           "shares_grid_cell_with": shared}
    else:
        card["weather"] = None

    card["notes"] = NOTES
    cards[code] = card
    with open(OUT_DIR / f"district_{code}.json", "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)

    zero = sum(1 for n in soil_block if n["samples"] == 0)
    rows.append({
        "district": p.district, "code": code,
        "soil_nutrients": len(soil_block), "soil_zero": zero,
        "soil_low_flag": sum(1 for n in soil_block if n["low_sample_flag"]),
        "soil_min_n": min([n["samples"] for n in soil_block]) if soil_block else None,
        "crop_rows": len(c), "seasons": ",".join(sorted(seasons.keys())),
        "weather": bool(len(w)), "grid_shared": bool(shared),
    })

with open(OUT_DIR / "telangana_district_context.json", "w", encoding="utf-8") as f:
    json.dump(list(cards.values()), f, ensure_ascii=False)

cov = pd.DataFrame(rows)
log(f"Districts with a context card: {len(cov)}")
log("\n=== Coverage per district ===")
log(cov.to_string(index=False))
log(f"\nDistricts with no soil data: {cov.loc[cov['soil_nutrients'] == 0, 'district'].tolist()}")
log(f"Districts with no crop rows: {cov.loc[cov['crop_rows'] == 0, 'district'].tolist()}")
log(f"Districts with no weather: {cov.loc[~cov['weather'], 'district'].tolist()}")
log(f"\nDistrict-nutrients with fewer than 100 soil samples: {len(problems)}")
for d, n, k in problems[:30]:
    log(f"  {d}: {n} = {k}")

# ---- readable card ----
card = cards[SHOW_CODE]
log(f"\n================ {card['district']} ({card['state']}), code {card['district_code']} ================")
log(f"Point: {card['point']}   Approx area: {card['approx_area_km2']} km2")
log(f"\nSoil ({card['soil']['year']}) - most common class and its share:")
for n in card["soil"]["nutrients"]:
    lv = n["levels_pct"].get(n["most_common_level"]) if n["most_common_level"] else None
    log(f"  {n['nutrient']}: {n['most_common_level']} ({lv}%), samples={n['samples']}, "
        f"low_sample_flag={n['low_sample_flag']}")
log("\nTop crops by area:")
for season, lst in card["crops"]["seasons"].items():
    log(f"  {season}:")
    for x in lst[:5]:
        log(f"    {x['crop_name']}: mean area {x['mean_area_ha']} ha "
            f"({x['pct_of_district_season_area']}% of season area), "
            f"yield {x.get('weighted_yield_t_per_ha')} t/ha, years={x['years_with_area']}, "
            f"coverage={x['data_coverage']}")
log("\nWeather:")
log(f"  {card['weather']['values']}")
log(f"  Shares a grid cell with: {card['weather']['shares_grid_cell_with']}")

AUDIT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved cards in {OUT_DIR}")