from pathlib import Path
import pandas as pd

RAW = sorted(Path("data/raw/rainfall_daily").glob("*.csv"))[0]
PROFILE = Path("data/processed/district_crop_profile.csv")
OUT_DIR = Path("data/processed")
AUDIT_DIR = Path("data/audits")
OUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

LAST_DATE = pd.Timestamp("2023-12-31")      # 2024 is mostly empty in this file
WINDOW_START, WINDOW_END = 2018, 2023
MIN_MONSOON_DAYS = 116                      # 95% of the 122 days in June-September
MIN_ANNUAL_DAYS = 347                       # 95% of 365
RAINY_DAY_MM = 2.5

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

parts, names = [], []
for chunk in pd.read_csv(RAW, chunksize=500_000, low_memory=False):
    chunk.columns = [c.strip().lower().replace(" ", "_") for c in chunk.columns]
    names.append(chunk[["state_name", "district_code", "district_name"]].drop_duplicates())
    sub = chunk[["date", "district_code", "actual"]].copy()
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub["district_code"] = pd.to_numeric(sub["district_code"], errors="coerce")
    sub["actual"] = pd.to_numeric(sub["actual"], errors="coerce")
    sub = sub[sub["date"] <= LAST_DATE]
    parts.append(sub)
    print(f"  ...read {sum(len(p) for p in parts):,} rows")

df = pd.concat(parts, ignore_index=True).dropna(subset=["date", "district_code"])
df["district_code"] = df["district_code"].astype(int)

nm = pd.concat(names).drop_duplicates()
nm["district_code"] = pd.to_numeric(nm["district_code"], errors="coerce")
nm = nm.dropna(subset=["district_code"])
nm["district_code"] = nm["district_code"].astype(int)
name_one = nm.drop_duplicates("district_code")

# ---- Exclusions ----
dup_codes = set(df.loc[df.duplicated(["district_code", "date"], keep=False), "district_code"])
real = df.groupby("district_code")["actual"].count()
blank_codes = set(real[real == 0].index)
excluded = dup_codes | blank_codes
log(f"Rows after dropping dates later than {LAST_DATE.date()}: {len(df):,}")
log(f"Excluded districts with duplicate rows: {sorted(dup_codes)}")
log(f"Excluded districts with no real rainfall values: {sorted(blank_codes)}")
ex = name_one[name_one["district_code"].isin(excluded)]
log(ex[["state_name", "district_code", "district_name"]].to_string(index=False))

df = df[~df["district_code"].isin(excluded)].copy()
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.month

# ---- District-year table ----
mon = df[df["month"].between(6, 9)]
m = (mon.groupby(["district_code", "year"])
        .agg(monsoon_mm=("actual", "sum"),
             monsoon_days=("actual", "count"),
             monsoon_rainy_days=("actual", lambda s: int((s >= RAINY_DAY_MM).sum())))
        .reset_index())
a = (df.groupby(["district_code", "year"])
       .agg(annual_mm=("actual", "sum"), annual_days=("actual", "count"))
       .reset_index())
dy = a.merge(m, on=["district_code", "year"], how="left")
dy["monsoon_complete"] = dy["monsoon_days"] >= MIN_MONSOON_DAYS
dy["annual_complete"] = dy["annual_days"] >= MIN_ANNUAL_DAYS
dy = dy.merge(name_one, on="district_code", how="left")
dy = dy[["state_name", "district_code", "district_name", "year", "monsoon_mm", "monsoon_days",
         "monsoon_rainy_days", "monsoon_complete", "annual_mm", "annual_days", "annual_complete"]]
dy.round(1).to_csv(OUT_DIR / "rainfall_district_year.csv", index=False)

# ---- District profile ----
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
longterm = summarize(2009, 2023, "2009_2023")[["monsoon_mean_mm_2009_2023", "monsoon_years_used_2009_2023"]]
fa = dy[dy["year"].between(WINDOW_START, WINDOW_END) & dy["annual_complete"]]
ann = fa.groupby("district_code").agg(annual_mean_mm_2018_2023=("annual_mm", "mean"),
                                      annual_years_used_2018_2023=("year", "nunique"))
prof_r = recent.join(longterm, how="outer").join(ann, how="outer").reset_index()
prof_r = prof_r.merge(name_one, on="district_code", how="left")

# ---- Boundary caution: states where current districts are missing from the rainfall file ----
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
prof_r