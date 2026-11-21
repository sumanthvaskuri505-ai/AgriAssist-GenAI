from pathlib import Path
import numpy as np
import pandas as pd

IN_PATH = Path("data/processed/crop_production_clean.csv")
OUT_PATH = Path("data/processed/district_crop_profile.csv")
AUDIT_DIR = Path("data/audits")

# ---- Settings you can change ----
WINDOW_START = 2018     # 2018 = agricultural year 2018-2019
WINDOW_END = 2022       # 2022 = agricultural year 2022-2023 (latest in the data)
SHOW_DISTRICT = "Nizamabad"

df = pd.read_csv(IN_PATH, low_memory=False)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

# ---- Part 1: the 6 usable rows with area above 1,000,000 ha ----
big = df[df["usable"] & (df["area"] > 1_000_000)]
log("=== Usable rows with area above 1,000,000 ha (please review) ===")
log(big[["year", "state_name", "district_name", "crop_name", "season", "area",
         "production_tonnes", "yield_tonnes_per_ha"]].to_string(index=False))

# ---- Part 2: restrict to the window ----
w = df[(df["start_year"] >= WINDOW_START) & (df["start_year"] <= WINDOW_END)].copy()
log(f"\nWindow: {WINDOW_START}-{WINDOW_START+1} to {WINDOW_END}-{WINDOW_END+1}, "
    f"{len(w):,} rows")

# District boundary check: does a state's number of districts change inside the window?
cnt = (w[~w["flag_total_season"]].groupby(["state_name", "year"])["district_code"]
         .nunique().groupby("state_name").agg(["min", "max"]))
changed = cnt[cnt["min"] != cnt["max"]]
log("\nStates whose district count CHANGES inside the window (profiles need care):")
log(changed.to_string() if len(changed) else "(none)")

# ---- Part 3: choose which rows count ----
# Area counts unless: Total-season row, or impossible area.
# (area_outlier is only a REVIEW flag, so it does not exclude the row)
area_ok = ~w["flag_total_season"] & ~w["flag_area_implausible"]
# Yield counts only if area is fine AND production recorded AND unit known AND no yield outlier.
yield_ok = (area_ok & ~w["flag_no_production"]
            & ~w["flag_unit_unresolved"] & ~w["flag_yield_outlier"])

key = ["state_code", "state_name", "district_code", "crop_name", "crop_type", "season"]

# ---- Part 4: area statistics ----
a = (w[area_ok].groupby(key)
       .agg(years_with_area=("start_year", "nunique"),
            mean_area_ha=("area", "mean"),
            years_flagged_for_review=("flag_area_outlier", "sum"))
       .reset_index())

# ---- Part 5: yield statistics (production-weighted) ----
ys = (w[yield_ok].groupby(key)
        .agg(years_with_yield=("start_year", "nunique"),
             area_sum=("area", "sum"),
             prod_t=("production_tonnes", "sum"),
             prod_n=("production_nuts", "sum"),
             min_yield_t_per_ha=("yield_tonnes_per_ha", "min"),
             max_yield_t_per_ha=("yield_tonnes_per_ha", "max"))
        .reset_index())
ys["weighted_yield_t_per_ha"] = np.where(ys["prod_t"] > 0, ys["prod_t"] / ys["area_sum"], np.nan)
ys["weighted_yield_nuts_per_ha"] = np.where(ys["prod_n"] > 0, ys["prod_n"] / ys["area_sum"], np.nan)
ys = ys.drop(columns=["area_sum", "prod_t", "prod_n"])

profile = a.merge(ys, on=key, how="left")

# Latest district name for each district code
latest_name = (w.sort_values("start_year").groupby("district_code")["district_name"].last())
profile["district_name"] = profile["district_code"].map(latest_name)

# Share of the district's area in that season
tot = profile.groupby(["district_code", "season"])["mean_area_ha"].transform("sum")
profile["pct_of_district_season_area"] = 100 * profile["mean_area_ha"] / tot

# Coverage label: ONLY how many years of data exist (not a suitability score)
profile["data_coverage"] = pd.cut(profile["years_with_area"], bins=[0, 1, 3, 20],
                                  labels=["low (1 yr)", "medium (2-3 yrs)", "high (4+ yrs)"]).astype(str)

num_cols = ["mean_area_ha", "pct_of_district_season_area", "min_yield_t_per_ha",
            "max_yield_t_per_ha", "weighted_yield_t_per_ha", "weighted_yield_nuts_per_ha"]
profile[num_cols] = profile[num_cols].round(3)

first = ["state_name", "state_code", "district_name", "district_code",
         "crop_name", "crop_type", "season"]
profile = profile[first + [c for c in profile.columns if c not in first]]
profile = profile.sort_values(["state_name", "district_name", "season", "mean_area_ha"],
                              ascending=[True, True, True, False])
profile.to_csv(OUT_PATH, index=False)

# ---- Part 6: summary ----
log(f"\nProfile rows: {len(profile):,}")
log(f"States: {profile['state_name'].nunique()}   Districts: {profile['district_code'].nunique()}   "
    f"Crops: {profile['crop_name'].nunique()}")
log("Rows by data coverage:")
log(profile["data_coverage"].value_counts().to_string())

tg = profile[profile["state_name"].str.contains("Telangana", case=False, na=False)]
log(f"\nTelangana: {tg['district_code'].nunique()} districts, {len(tg):,} profile rows")

d = tg[tg["district_name"].eq(SHOW_DISTRICT)]
show = ["crop_name", "years_with_area", "mean_area_ha", "pct_of_district_season_area",
        "weighted_yield_t_per_ha", "min_yield_t_per_ha", "max_yield_t_per_ha", "data_coverage"]
for season in ["Kharif", "Rabi"]:
    log(f"\n=== {SHOW_DISTRICT}: top 8 crops by area, {season} ===")
    log(d[d["season"].eq(season)].head(8)[show].to_string(index=False))

(AUDIT_DIR / "district_profile_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved {OUT_PATH}")