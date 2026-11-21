from pathlib import Path
import pandas as pd

CLEAN = Path("data/processed/crop_production_clean.csv")
PROFILE = Path("data/processed/district_crop_profile.csv")
README = Path("data/processed/README_crop_data.txt")
AUDIT_DIR = Path("data/audits")

WINDOW_START, WINDOW_END = 2018, 2022     # must match build_district_crop_profile.py
N_YEARS = WINDOW_END - WINDOW_START + 1

clean = pd.read_csv(CLEAN, low_memory=False)
profile = pd.read_csv(PROFILE)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

w = clean[(clean["start_year"] >= WINDOW_START)
          & (clean["start_year"] <= WINDOW_END)
          & ~clean["flag_total_season"]]

# ---- 1. Boundary warnings ----
for c in ["district_years_in_window", "district_partial_window",
          "state_boundary_changed_in_window"]:
    if c in profile.columns:
        profile = profile.drop(columns=[c])

yrs = (w.groupby("district_code")["start_year"].nunique()
         .rename("district_years_in_window").reset_index())
profile = profile.merge(yrs, on="district_code", how="left")
profile["district_partial_window"] = profile["district_years_in_window"] < N_YEARS

cnt = (w.groupby(["state_name", "year"])["district_code"].nunique()
         .groupby("state_name").agg(["min", "max"]))
changed_states = set(cnt[cnt["min"] != cnt["max"]].index)
profile["state_boundary_changed_in_window"] = profile["state_name"].isin(changed_states)

log(f"States with changing district counts in the window: {len(changed_states)}")
log(f"Profile rows in those states: {int(profile['state_boundary_changed_in_window'].sum()):,} "
    f"of {len(profile):,}")
part = (profile.drop_duplicates("district_code")
               .loc[lambda d: d["district_partial_window"]]
               .groupby("state_name").size().sort_values(ascending=False))
log(f"\nDistricts with data in fewer than {N_YEARS} window years, by state:")
log(part.to_string() if len(part) else "(none)")

tg = profile[profile["state_name"].str.contains("Telangana", case=False, na=False)]
log(f"\nTelangana: districts={tg['district_code'].nunique()}, "
    f"partial-window rows={int(tg['district_partial_window'].sum())}, "
    f"boundary-changed rows={int(tg['state_boundary_changed_in_window'].sum())}  (both should be 0)")

profile.to_csv(PROFILE, index=False)

# ---- 2. Which crops are in the full data but not in the profile? ----
nt = clean[~clean["flag_total_season"]]
allc = nt.groupby("crop_name").agg(rows_all_years=("year", "size"),
                                   first_year=("start_year", "min"),
                                   last_year=("start_year", "max"))
inwin = w.groupby("crop_name").size().rename("rows_in_window")
dropped = allc[~allc.index.isin(set(profile["crop_name"]))].join(inwin)
dropped["rows_in_window"] = dropped["rows_in_window"].fillna(0).astype(int)
dropped = dropped.sort_values(["rows_in_window", "rows_all_years"], ascending=False)
log(f"\nCrops in the full data but NOT in the profile: {len(dropped)} of {len(allc)}")
log(dropped.head(40).to_string())
log(f"\nCrops that HAVE rows in the window but are missing from the profile: "
    f"{int((dropped['rows_in_window'] > 0).sum())}")

# ---- 3. README with source credit and processing notes ----
readme_lines = [
    "CROP DATA - SOURCE AND PROCESSING NOTES",
    "",
    "Source: India Data Portal, Crop Wise Area Production Yield (years 1997-2023).",
    "Data originates from the Directorate of Economics and Statistics, Ministry of",
    "Agriculture and Farmers Welfare, Government of India.",
    "Licence shown on the dataset page: Open Data Commons Attribution License.",
    "Credit the source in the app and in any publication.",
    "",
    "Processing (the raw CSV is never modified):",
    "- Rows with season Total are flagged (they are the sum of the other seasons).",
    "- Production missing or zero is flagged (yield 0 means nothing recorded).",
    "- Coconut is in nuts; Cotton(Lint) is in bales of 170 kg; Jute, Mesta and",
    "  Jute & Mesta are in bales of 180 kg (per official DES-format reports).",
    "  Bales are converted to tonnes. Coconut stays in nuts. Kapas is unresolved.",
    "- Implausible areas and extreme yields are flagged. Area far above the",
    "  districts own history is a REVIEW flag and does not exclude a row.",
    "- Profile window: agricultural years 2018-19 to 2022-23.",
    "- States whose district count changed inside the window are marked",
    "  (state_boundary_changed_in_window); their profiles mix boundaries.",
    "- All figures are reported government statistics. They are not measurements",
    "  made by this project, and no suitability score or prediction is included.",
]
README.write_text("\n".join(readme_lines), encoding="utf-8")

(AUDIT_DIR / "finalize_profile_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"\nUpdated {PROFILE}")
print(f"Wrote {README}")