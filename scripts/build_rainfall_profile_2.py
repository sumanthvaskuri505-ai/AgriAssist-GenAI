from pathlib import Path
import pandas as pd

DY_PATH = Path("data/processed/rainfall_district_year.csv")
PROFILE = Path("data/processed/district_crop_profile.csv")
OUT_DIR = Path("data/processed")
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_START, WINDOW_END = 2018, 2023

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

print("Step A: reading the district-year table...")
dy = pd.read_csv(DY_PATH)
log(f"Rows: {len(dy):,}   Columns: {list(dy.columns)}")
for c in ["monsoon_complete", "annual_complete"]:
    dy[c] = dy[c].astype(str).str.lower().eq("true")
name_one = dy[["state_name", "district_code", "district_name"]].drop_duplicates("district_code")

print("Step B: summarising monsoon rainfall...")
def summarize(y0, y1, tag):
    f = dy[dy["year"].between(y0, y1) & dy["monsoon_complete"]]
    return f.groupby("district_code").agg(**{
        f"monsoon_mean_mm_{tag}": ("monsoon_mm", "mean"),
        f"monsoon_min_mm_{tag}": ("monsoon_mm", "min"),
        f"monsoon_max_mm_{tag}": ("monsoon_mm", "max"),
        f"monsoon_rainy_days_mean_{tag}": ("monsoon_rainy_days", "mean"),
        f"monsoon_years_used_{tag}": ("year", "nunique"),
    })

recent = summarize(WINDOW_START, WINDOW_END, "2018_2023")
longterm = summarize(2009, 2023, "2009_2023")[
    ["monsoon_mean_mm_2009_2023", "monsoon_years_used_2009_2023"]]

print("Step C: summarising annual rainfall...")
fa = dy[dy["year"].between(WINDOW_START, WINDOW_END) & dy["annual_complete"]]
ann = fa.groupby("district_code").agg(annual_mean_mm_2018_2023=("annual_mm", "mean"),
                                      annual_years_used_2018_2023=("year", "nunique"))

print("Step D: joining tables...")
prof_r = recent.join(longterm, how="outer").join(ann, how="outer").reset_index()
prof_r = prof_r.merge(name_one, on="district_code", how="left")

print("Step E: comparing with the crop profile...")
crop = pd.read_csv(PROFILE)
crop_d = crop.drop_duplicates("district_code")[["state_name", "district_code"]]
have = set(prof_r["district_code"])
missing_by_state = crop_d[~crop_d["district_code"].isin(have)].groupby("state_name").size()
prof_r["state_districts_missing_from_rain_file"] = (
    prof_r["state_name"].map(missing_by_state).fillna(0).astype(int))
prof_r["boundary_caution"] = prof_r["state_districts_missing_from_rain_file"] > 0
prof_r["in_crop_profile"] = prof_r["district_code"].isin(set(crop_d["district_code"]))

first = ["state_name", "district_code", "district_name", "in_crop_profile", "boundary_caution",
         "state_districts_missing_from_rain_file"]
prof_r = prof_r[first + [c for c in prof_r.columns if c not in first]].round(1)
prof_r = prof_r.sort_values(["state_name", "district_name"])

print("Step F: saving...")
prof_r.to_csv(OUT_DIR / "rainfall_district_profile.csv", index=False)

readme_lines = [
    "RAINFALL DATA - SOURCE AND PROCESSING NOTES",
    "",
    "Source: India Data Portal, Daily Rainfall Data - District Level.",
    "Licence shown on the resource page: Open Data Commons Attribution License.",
    "Credit the source in the app and in any publication.",
    "",
    "Processing (the raw CSV is never modified):",
    "- Dates after 2023-12-31 are dropped (2024 is mostly empty in the file).",
    "- Districts with no real rainfall values (6) are excluded.",
    "- Districts with duplicate district-date rows with differing values are excluded (Leh Ladakh).",
    "- Monsoon total = June-September sum; a year counts only if at least 116 of 122 days have data.",
    "- Rainy day = 2.5 mm or more in a day.",
    "- The file seems to use older district boundaries in some states (for example Telangana has",
    "  only its original 10 districts). boundary_caution marks states where current districts",
    "  are missing from the file.",
    "- Values are reported or gridded rainfall from several agencies, not measurements made by this project.",
]
(OUT_DIR / "README_rainfall_data.txt").write_text("\n".join(readme_lines), encoding="utf-8")

log(f"\nDistrict-year rows: {len(dy):,}   Complete monsoon years: {int(dy['monsoon_complete'].sum()):,}")
log(f"Districts in the rainfall profile: {len(prof_r)}")
log(f"Crop-profile districts: {len(crop_d)}   with a rainfall profile: "
    f"{int(crop_d['district_code'].isin(have).sum())}")
log(f"Rows with boundary_caution: {int(prof_r['boundary_caution'].sum())} of {len(prof_r)}")
log("\nCrop-profile districts without rainfall, by state:")
log(missing_by_state.sort_values(ascending=False).to_string())

tg = prof_r[prof_r["state_name"].str.contains("Telangana", case=False, na=False)]
cols = ["district_name", "monsoon_mean_mm_2018_2023", "monsoon_min_mm_2018_2023",
        "monsoon_max_mm_2018_2023", "monsoon_rainy_days_mean_2018_2023",
        "monsoon_years_used_2018_2023", "boundary_caution"]
log("\n=== Telangana rainfall profile ===")
log(tg[cols].to_string(index=False))

(AUDIT_DIR / "rainfall_profile_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nSaved rainfall_district_profile.csv, README_rainfall_data.txt, rainfall_profile_summary.txt")