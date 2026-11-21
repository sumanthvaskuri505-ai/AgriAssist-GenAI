import sys
from pathlib import Path
import pandas as pd

import os; SOIL = Path(os.environ.get("AGRI_SOIL_CSV", "data/raw/soil/soil_health_india.csv"))
OUT = Path("data/processed/soil_district_summary.csv")
AUDIT = Path("data/audits/soil_district_summary_audit.txt")
LOW_N = 100

if not SOIL.exists():
    sys.exit(f"Soil file not found: {SOIL}")

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

cols = ["year", "state_name", "state_code", "district_name", "district_code",
        "nutrient_name", "nutrient_level", "value"]
key = ["year", "state_code", "district_code", "nutrient_name", "nutrient_level"]

agg_parts, name_parts, total = [], [], 0
for chunk in pd.read_csv(SOIL, usecols=cols, chunksize=1_000_000, low_memory=False):
    total += len(chunk)
    chunk["value"] = pd.to_numeric(chunk["value"], errors="coerce")
    name_parts.append(chunk[["state_code", "state_name", "district_code",
                             "district_name"]].drop_duplicates())
    g = chunk.groupby(key, dropna=False).agg(samples=("value", "sum"),
                                             records=("value", "size")).reset_index()
    agg_parts.append(g)
    print(f"  ...read {total:,} rows")

agg = (pd.concat(agg_parts)
         .groupby(key, dropna=False, as_index=False)[["samples", "records"]].sum())
names = pd.concat(name_parts).drop_duplicates("district_code")

log(f"Rows read: {total:,}")
log(f"Districts: {agg['district_code'].nunique()}   Years: {sorted(agg['year'].astype(str).unique())}")

# ---- Levels per nutrient (all India) ----
lv = agg.groupby(["nutrient_name", "nutrient_level"], dropna=False)["samples"].sum().reset_index()
lv["pct_within_nutrient"] = (100 * lv["samples"] / lv.groupby("nutrient_name")["samples"]
                             .transform("sum")).round(1)
log("\n=== Levels found for each nutrient (all India) ===")
log(lv.to_string(index=False))

log("\n=== Total 'value' per nutrient (should be similar if value counts samples) ===")
log(agg.groupby("nutrient_name")["samples"].sum().astype("int64").to_string())

# ---- Percentages within each district-year-nutrient ----
tot = agg.groupby(["year", "district_code", "nutrient_name"], dropna=False)["samples"].transform("sum")
agg["n_total"] = tot
agg["pct_of_nutrient_samples"] = (100 * agg["samples"] / tot).where(tot > 0).round(1)
agg["low_sample_flag"] = tot < LOW_N
agg = agg.merge(names[["district_code", "state_name", "district_name"]],
                on="district_code", how="left")
first = ["year", "state_name", "state_code", "district_code", "district_name",
         "nutrient_name", "nutrient_level", "samples", "records", "n_total",
         "pct_of_nutrient_samples", "low_sample_flag"]
agg = agg[first].sort_values(["state_name", "district_name", "year", "nutrient_name", "nutrient_level"])
agg.to_csv(OUT, index=False)
log(f"\nSummary rows: {len(agg):,}   flagged low-sample rows: {int(agg['low_sample_flag'].sum()):,}")

# ---- Telangana coverage ----
tg = agg[agg["state_name"].astype(str).str.contains("Telangana", case=False, na=False)]
log("\n=== Telangana coverage ===")
for yr, d in tg.groupby("year"):
    per = d.drop_duplicates(["district_code", "nutrient_name"])
    log(f"{yr}: districts with data = {d['district_code'].nunique()}, "
        f"median records per district-nutrient = {per['n_total'].median():.0f}, "
        f"minimum = {per['n_total'].min():.0f}")

# ---- Preview: Nizamabad (code 516) ----
nz = agg[agg["district_code"] == 516]
for yr, d in nz.groupby("year"):
    log(f"\n=== Nizamabad {yr}: share of samples by level ===")
    log(d[["nutrient_name", "nutrient_level", "samples", "pct_of_nutrient_samples",
           "low_sample_flag"]].to_string(index=False))

AUDIT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved {OUT}")