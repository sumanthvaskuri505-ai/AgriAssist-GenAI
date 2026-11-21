import sys
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw/rainfall_daily")
PROFILE = Path("data/processed/district_crop_profile.csv")
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

csvs = sorted(RAW_DIR.glob("*.csv"))
if not csvs:
    sys.exit(f"No CSV found in {RAW_DIR}")
path = csvs[0]

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

log(f"Reading: {path}  ({path.stat().st_size / 1024**2:.1f} MiB)")

# ---- Header first: we inspect columns before assuming anything ----
head = pd.read_csv(path, nrows=3)
head.columns = [c.strip().lower().replace(" ", "_") for c in head.columns]
log(f"Columns: {list(head.columns)}")
for c in ["date", "district_code", "actual"]:
    if c not in head.columns:
        sys.exit(f"Expected a column named '{c}' but it is missing. "
                 "Send me the column list above and I will adjust the script.")

# ---- Read in chunks, keeping only the few columns we need ----
parts, names = [], []
total_rows = 0
for chunk in pd.read_csv(path, chunksize=500_000, low_memory=False):
    chunk.columns = [c.strip().lower().replace(" ", "_") for c in chunk.columns]
    total_rows += len(chunk)
    if {"state_name", "district_name"} <= set(chunk.columns):
        names.append(chunk[["state_name", "district_code", "district_name"]].drop_duplicates())
    keep = [c for c in ["date", "district_code", "actual", "normal"] if c in chunk.columns]
    sub = chunk[keep].copy()
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub["district_code"] = pd.to_numeric(sub["district_code"], errors="coerce")
    for c in ["actual", "normal"]:
        if c in sub.columns:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").astype("float32")
    parts.append(sub)
    print(f"  ...read {total_rows:,} rows so far")

df = pd.concat(parts, ignore_index=True)
nm = pd.concat(names).drop_duplicates() if names else None

log(f"\nTotal rows: {total_rows:,}")
log(f"Unparseable dates: {int(df['date'].isna().sum()):,}")
log(f"Missing or non-numeric district_code: {int(df['district_code'].isna().sum()):,}")
log(f"Missing actual rainfall: {int(df['actual'].isna().sum()):,}  "
    f"({df['actual'].isna().mean() * 100:.1f}%)")

d = df.dropna(subset=["date", "district_code"]).copy()
d["district_code"] = d["district_code"].astype(int)
log(f"Date range: {d['date'].min().date()} to {d['date'].max().date()}")

dups = int(d.duplicated(["district_code", "date"]).sum())
log(f"Duplicate (district_code, date) rows: {dups:,}")
if dups:
    d = d.drop_duplicates(["district_code", "date"])
    log("  (duplicates dropped before the calculations below)")

d["year"] = d["date"].dt.year
d["month"] = d["date"].dt.month

log("\n--- Rows and districts per year ---")
per_year = d.groupby("year").agg(rows=("date", "size"),
                                 districts=("district_code", "nunique"),
                                 missing_actual=("actual", lambda s: int(s.isna().sum())))
log(per_year.to_string())

log("\n--- 'actual' rainfall: distribution (units not assumed; check these look like mm) ---")
a = d["actual"].dropna()
log(a.describe(percentiles=[0.5, 0.9, 0.99, 0.999]).round(2).to_string())
log(f"Negative values: {int((a < 0).sum()):,}")
log(f"Zero values: {int((a == 0).sum()):,}  ({(a == 0).mean() * 100:.1f}%)")
log(f"Above 300: {int((a > 300).sum()):,}   Above 500: {int((a > 500).sum()):,}")

cov = d.groupby("district_code").agg(rows=("date", "size"),
                                     first_date=("date", "min"),
                                     last_date=("date", "max"))
if nm is not None:
    cov = cov.join(nm.drop_duplicates("district_code").set_index("district_code"))
cov.to_csv(AUDIT_DIR / "rain_district_coverage.csv")
log(f"\nDistricts with any rainfall rows: {len(cov)}")

# ---- Join check against the crop profile ----
if PROFILE.exists():
    prof = pd.read_csv(PROFILE)
    pcodes = set(prof["district_code"].astype(int))
    has_data = d[d["actual"].notna() & (d["year"] >= 2018)]
    rcodes = set(has_data["district_code"])
    log(f"\nCrop-profile districts: {len(pcodes)}")
    log(f"  ... with real (non-blank) rainfall values in 2018 or later: {len(pcodes & rcodes)}")
    miss = prof[~prof["district_code"].isin(rcodes)].drop_duplicates("district_code")
    log(f"  ... WITHOUT such rainfall data: {len(miss)}")
    log(miss.groupby("state_name").size().sort_values(ascending=False).to_string())
    tg_codes = set(prof.loc[prof["state_name"].str.contains("Telangana", case=False, na=False),
                            "district_code"].astype(int))
else:
    tg_codes = set()
    log("\n(Crop profile not found; skipping the join check.)")

# ---- Telangana: June-September totals per year ----
log("\n=== Telangana: June-September rainfall by year ===")
log(f"Telangana districts (from crop profile) with rainfall rows: "
    f"{len(tg_codes & set(d['district_code']))} of {len(tg_codes)}")
j = d[d["month"].between(6, 9) & d["district_code"].isin(tg_codes)]
tot = j.groupby(["district_code", "year"]).agg(jjas_mm=("actual", "sum"),
                                               days=("actual", "count")).reset_index()
summary = tot.groupby("year").agg(districts=("district_code", "nunique"),
                                  mean_jjas=("jjas_mm", "mean"),
                                  min_jjas=("jjas_mm", "min"),
                                  max_jjas=("jjas_mm", "max"),
                                  min_days=("days", "min")).round(1)
log(summary.to_string())
log("(A full June-September has 122 days; a smaller 'min_days' means gaps.)")

(AUDIT_DIR / "rainfall_daily_audit.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nSaved data\\audits\\rainfall_daily_audit.txt")