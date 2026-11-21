from pathlib import Path
import numpy as np
import pandas as pd

IN_PATH = Path("data/processed/crop_production_flagged.csv")
OUT_PATH = Path("data/processed/crop_production_clean.csv")
AUDIT_DIR = Path("data/audits")

df = pd.read_csv(IN_PATH, low_memory=False)
name = df["crop_name"].str.strip().str.lower()

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

# ---- 1. Real units (from official DES-format reports) ----
df["reported_unit"] = "Tonnes"
df.loc[name.eq("coconut"), "reported_unit"] = "Nuts"
df.loc[name.eq("cotton(lint)"), "reported_unit"] = "Bales (170 kg)"
df.loc[name.isin(["jute", "mesta", "jute & mesta"]), "reported_unit"] = "Bales (180 kg)"
df.loc[name.eq("kapas"), "reported_unit"] = "Unknown"

log("Crop names touching these units (so we can see exactly what was matched):")
mask_names = name.str.contains("coconut|cotton|kapas|jute|mesta")
log(df.loc[mask_names].groupby(["crop_name", "reported_unit"]).size().to_string())

# ---- 2. Convert bales to tonnes; leave nuts and unknown as missing tonnes ----
kg_per_bale = df["reported_unit"].map({"Bales (170 kg)": 170, "Bales (180 kg)": 180})
is_bale = kg_per_bale.notna()
df["production_tonnes"] = df["production"]
df.loc[is_bale, "production_tonnes"] = df.loc[is_bale, "production"] * kg_per_bale[is_bale] / 1000
df.loc[df["reported_unit"].isin(["Nuts", "Unknown"]), "production_tonnes"] = np.nan
df["production_nuts"] = np.where(df["reported_unit"].eq("Nuts"), df["production"], np.nan)

df["yield_tonnes_per_ha"] = np.where(df["area"] > 0, df["production_tonnes"] / df["area"], np.nan)
df["yield_nuts_per_ha"] = np.where(df["area"] > 0, df["production_nuts"] / df["area"], np.nan)

# ---- 3. New flag: unit unresolved; recompute 'usable' ----
df["flag_unit_unresolved"] = df["reported_unit"].eq("Unknown")
flag_cols = ["flag_total_season", "flag_no_production", "flag_unit_unresolved",
             "flag_yield_outlier", "flag_area_outlier"]
df["usable"] = ~df[flag_cols].any(axis=1)

# For area-outlier review: the district-crop-season's own median area
nt = ~df["flag_total_season"]
df["district_crop_median_area"] = (
    df[nt].groupby(["district_code", "crop_name", "season"])["area"].transform("median")
)

df.to_csv(OUT_PATH, index=False)

log(f"\nRows: {len(df):,}")
log("Rows per reported unit:")
log(df["reported_unit"].value_counts().to_string())
log(f"Usable rows (new definition): {df['usable'].sum():,}  ({df['usable'].mean()*100:.1f}%)")
log(f"Usable rows with a tonnes value: {(df['usable'] & df['production_tonnes'].notna()).sum():,}")

# ---- 4. Did we catch the extreme West Bengal 1997-98 rows? ----
log("\n=== 10 largest areas in the whole file, and their flags ===")
show = ["year", "state_name", "district_name", "crop_name", "season",
        "area", "flag_area_outlier", "usable"]
log(df.sort_values("area", ascending=False).head(10)[show].to_string(index=False))

# ---- 5. Spot-check clusters of area outliers ----
cols = ["year", "state_name", "district_name", "crop_name", "season",
        "area", "district_crop_median_area"]
for st, yr in [("Madhya Pradesh", "2016-2017"), ("Jharkhand", "2022-2023"),
               ("Uttar Pradesh", "1997-1998")]:
    s = df[df["flag_area_outlier"] & df["state_name"].eq(st) & df["year"].eq(yr)]
    log(f"\n=== Flagged area outliers: {st} {yr} ({len(s)} rows). Top 6 by area ===")
    log(s.sort_values("area", ascending=False).head(6)[cols].to_string(index=False))

# ---- 6. Telangana sanity check, latest year, usable rows only ----
tg = df[df["state_name"].str.contains("Telangana", case=False, na=False)
        & df["year"].eq("2022-2023") & df["usable"]]
g = tg.groupby(["crop_name", "season"]).agg(
    districts=("district_code", "nunique"),
    area_ha=("area", "sum"),
    prod_tonnes=("production_tonnes", "sum"),
    prod_nuts=("production_nuts", "sum"),
).reset_index()
g["yield_t_per_ha"] = np.where(g["prod_tonnes"] > 0, g["prod_tonnes"] / g["area_ha"], np.nan)
g = g.sort_values("area_ha", ascending=False).head(15).round(2)
log("\n=== Telangana 2022-23, top 15 crop-seasons by area (usable rows) ===")
log(g.to_string(index=False))

(AUDIT_DIR / "crop_clean_v2_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved {OUT_PATH}")