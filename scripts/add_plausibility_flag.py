from pathlib import Path
import numpy as np
import pandas as pd

PATH = Path("data/processed/crop_production_clean.csv")
AUDIT_DIR = Path("data/audits")

df = pd.read_csv(PATH, low_memory=False)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

usable_before = int(df["usable"].sum())

# ---- New rule: area far above what this crop ever has in ANY district ----
not_total = ~df["flag_total_season"]
p99_area = df[not_total & (df["area"] > 0)].groupby("crop_name")["area"].quantile(0.99)
df["crop_p99_area"] = df["crop_name"].map(p99_area)
df["flag_area_implausible"] = not_total & (df["area"] > 10 * df["crop_p99_area"])

new_only = df["flag_area_implausible"] & ~df["flag_area_outlier"]

log(f"Rows flagged by the new rule: {df['flag_area_implausible'].sum():,}")
log(f"  ... of which NOT caught by the district-history rule: {new_only.sum():,}")

log("\nNewly caught rows by state and year (top 10):")
log(df[new_only].groupby(["state_name", "year"]).size()
      .sort_values(ascending=False).head(10).to_string())

cols = ["year", "state_name", "district_name", "crop_name", "season", "area", "crop_p99_area"]
log("\nTop 12 newly caught rows by area:")
log(df[new_only].sort_values("area", ascending=False).head(12)[cols].to_string(index=False))

# ---- Recompute 'usable' ----
flag_cols = ["flag_total_season", "flag_no_production", "flag_unit_unresolved",
             "flag_yield_outlier", "flag_area_outlier", "flag_area_implausible"]
df["usable"] = ~df[flag_cols].any(axis=1)

log(f"\nUsable rows: before {usable_before:,}  ->  after {int(df['usable'].sum()):,}")
log(f"Usable rows with area above 1,000,000 ha (should be 0): "
    f"{int((df['usable'] & (df['area'] > 1_000_000)).sum())}")

# ---- Telangana review (our target state) ----
tg = df[df["state_name"].str.contains("Telangana", case=False, na=False)
        & (df["start_year"] >= 2016)]
log("\n=== Telangana 2016-17 onward: rows and flags per year ===")
summary = tg.groupby("year").agg(
    rows=("usable", "size"),
    usable=("usable", "sum"),
    no_production=("flag_no_production", "sum"),
    yield_outlier=("flag_yield_outlier", "sum"),
    area_outlier=("flag_area_outlier", "sum"),
    area_implausible=("flag_area_implausible", "sum"),
)
log(summary.to_string())

tg_bad = tg[(tg["flag_area_outlier"] | tg["flag_yield_outlier"] | tg["flag_area_implausible"])
            & ~tg["flag_total_season"]]
log(f"\nTelangana rows flagged for area or yield: {len(tg_bad)}")
cols2 = ["year", "district_name", "crop_name", "season", "area",
         "district_crop_median_area", "yield_tonnes_per_ha", "crop_p99_yield"]
log("Top 15 by area:")
log(tg_bad.sort_values("area", ascending=False).head(15)[cols2].round(2).to_string(index=False))

df.to_csv(PATH, index=False)
(AUDIT_DIR / "crop_plausibility_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"\nUpdated {PATH}")