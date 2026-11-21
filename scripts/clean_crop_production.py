from pathlib import Path
import pandas as pd

RAW = sorted(Path("data/raw/crop_production").glob("*.csv"))[0]
OUT_DIR = Path("data/processed")
AUDIT_DIR = Path("data/audits")
OUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(RAW, low_memory=False)
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
for c in ["state_name", "district_name", "crop_name", "crop_type", "season", "year"]:
    df[c] = df[c].astype(str).str.strip()

# "2022-2023" -> 2022  (easier to sort and filter)
df["start_year"] = df["year"].str[:4].astype(int)

# ---- FLAG 1: season 'Total' is the sum of the other seasons -> would double count
df["flag_total_season"] = df["season"].eq("Total")

# ---- FLAG 2: production missing or zero (yield 0 means 'nothing recorded')
df["flag_no_production"] = df["production"].isna() | df["production"].eq(0)

# ---- FLAG 3: crops whose unit looks wrong (NOT confirmed yet; codebook will tell)
name_lower = df["crop_name"].str.lower()
df["flag_unit_suspect"] = name_lower.str.contains("coconut|cotton|jute|mesta")

# ---- FLAG 4: yield far above what is normal for that crop
base = ~df["flag_total_season"] & ~df["flag_no_production"]
p99 = df[base].groupby("crop_name")["yield"].quantile(0.99)
df["crop_p99_yield"] = df["crop_name"].map(p99)
df["flag_yield_outlier"] = (
    base & (df["crop_p99_yield"] > 0) & (df["yield"] > 3 * df["crop_p99_yield"])
)

# ---- FLAG 5: area far above that district-crop-season's own history
not_total = ~df["flag_total_season"]
grp = df[not_total].groupby(["district_code", "crop_name", "season"])["area"]
df["_median_area"] = grp.transform("median")
df["_obs"] = grp.transform("count")
df["flag_area_outlier"] = (
    not_total & (df["_obs"] >= 4) & (df["area"] > 20 * df["_median_area"])
)
df = df.drop(columns=["_median_area", "_obs"])

# ---- Overall: usable for analysis only if NO flag is set
flag_cols = ["flag_total_season", "flag_no_production", "flag_unit_suspect",
             "flag_yield_outlier", "flag_area_outlier"]
df["usable"] = ~df[flag_cols].any(axis=1)

out_path = OUT_DIR / "crop_production_flagged.csv"
df.to_csv(out_path, index=False)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

log(f"Rows: {len(df):,}")
for c in flag_cols:
    log(f"{c}: {df[c].sum():,}")
log(f"usable rows: {df['usable'].sum():,}  ({df['usable'].mean()*100:.1f}%)")

log("\nFlagged yield outliers, by crop (top 10):")
log(df.loc[df["flag_yield_outlier"], "crop_name"].value_counts().head(10).to_string())
log("\nFlagged area outliers, by state and year (top 10):")
log(df.loc[df["flag_area_outlier"]].groupby(["state_name", "year"]).size()
      .sort_values(ascending=False).head(10).to_string())

tg = df[df["state_name"].str.contains("Telangana", case=False, na=False)]
log("\nTelangana usable rows per year:")
log(tg.groupby("year")["usable"].agg(total="size", usable="sum").to_string())

(AUDIT_DIR / "crop_clean_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved {out_path}")