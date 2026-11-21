from pathlib import Path
import pandas as pd

RAW = sorted(Path("data/raw/crop_production").glob("*.csv"))[0]
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(RAW, low_memory=False)
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
df["season"] = df["season"].astype(str).str.strip()

lines = []
def log(text=""):
    print(text)
    lines.append(str(text))

SHOW = ["year", "state_name", "district_name", "crop_name",
        "season", "area", "production", "yield"]

# ---------------------------------------------------------------
log("=== CHECK 1: Is season 'Total' the sum of the other seasons? ===")
key = ["year", "district_code", "crop_name"]
is_total = df["season"].eq("Total")
tot = df[is_total].groupby(key)["production"].sum(min_count=1).rename("total_prod")
oth = df[~is_total].groupby(key)["production"].sum(min_count=1).rename("other_prod")

both = pd.concat([tot, oth], axis=1, join="inner").dropna()
both = both[both["other_prod"] > 0]
both["ratio"] = both["total_prod"] / both["other_prod"]
only_total = tot.index.difference(oth.index)

log(f"Groups (year, district, crop) that have a Total row: {len(tot):,}")
log(f"  ... of which also have other seasons: {len(both):,}")
log(f"  ... of which have ONLY a Total row:   {len(only_total):,}")
if len(both):
    close = ((both["ratio"] - 1).abs() < 0.02).mean() * 100
    log(f"Median Total / sum-of-other-seasons ratio: {both['ratio'].median():.3f}")
    log(f"Share of groups where Total is within 2% of the sum: {close:.1f}%")

# ---------------------------------------------------------------
log("\n=== CHECK 2: Duplicate rows ===")
key2 = ["year", "district_code", "crop_name", "season"]
dup_key = df.duplicated(subset=key2, keep=False)
cols_no_id = [c for c in df.columns if c != "id"]
dup_exact = df.duplicated(subset=cols_no_id, keep=False)
log(f"Rows sharing (year, district, crop name, season) with another row: {dup_key.sum():,}")
log(f"Rows that are exact copies of another row (ignoring id): {dup_exact.sum():,}")
log("Crops with the most duplicated rows:")
log(df.loc[dup_key, "crop_name"].value_counts().head(10).to_string())
(df[dup_key].sort_values(key2)[["id"] + SHOW]
   .head(300).to_csv(AUDIT_DIR / "crop_duplicates_sample.csv", index=False))

# ---------------------------------------------------------------
log("\n=== CHECK 3: Missing and zero production ===")
miss = df["production"].isna()
zero = df["production"].eq(0)
log(f"Production missing: {miss.sum():,}  (of these, yield == 0: {(df.loc[miss, 'yield'] == 0).sum():,})")
log(f"Production zero:    {zero.sum():,}  (of these, yield == 0: {(df.loc[zero, 'yield'] == 0).sum():,})")
log(f"Yield zero but production > 0: {((df['yield'] == 0) & (df['production'] > 0)).sum():,}")
log("States with the most missing production:")
log(df.loc[miss, "state_name"].value_counts().head(8).to_string())
log("Years with the most missing production:")
log(df.loc[miss, "year"].value_counts().head(8).to_string())

# ---------------------------------------------------------------
log("\n=== CHECK 4: Impossible values (units may be wrong for some crops) ===")
valid = df[df["production"].notna() & (df["area"] > 0) & (~df["season"].eq("Total"))]
by_crop = valid.groupby("crop_name").agg(
    rows=("yield", "size"),
    median_yield=("yield", "median"),
    p99_yield=("yield", lambda s: s.quantile(0.99)),
    max_yield=("yield", "max"),
    max_production=("production", "max"),
).round(3)
by_crop = by_crop.sort_values("max_yield", ascending=False)
by_crop.to_csv(AUDIT_DIR / "crop_yield_by_crop.csv")
log("Crops with the highest maximum yield (tonnes/hectare):")
log(by_crop.head(15).to_string())
log("\nTop 10 rows by area:")
log(df.sort_values("area", ascending=False)[SHOW].head(10).to_string(index=False))
log("\nTop 10 rows by production:")
log(df.sort_values("production", ascending=False)[SHOW].head(10).to_string(index=False))

# ---------------------------------------------------------------
log("\n=== CHECK 5: Crop names vs crop codes ===")
names_per_code = df.dropna(subset=["crop_code"]).groupby("crop_code")["crop_name"].nunique()
for code in names_per_code[names_per_code > 1].index:
    names = sorted(df.loc[df["crop_code"] == code, "crop_name"].unique())
    log(f"code {code:g} is used by: {names}")
log("\nCrop names with a missing crop_code:")
log(df.loc[df["crop_code"].isna(), "crop_name"].value_counts().to_string())

# ---------------------------------------------------------------
log("\n=== CHECK 6: Districts and Telangana ===")
nm = df.groupby("district_name")["district_code"].nunique()
log("District names that have more than one district code:")
for name in nm[nm > 1].index:
    sub = df.loc[df["district_name"] == name, ["state_name", "district_code"]].drop_duplicates()
    log(f"  {name}: {sub.values.tolist()}")

tg = df[df["state_name"].str.contains("Telangana", case=False, na=False)]
log("\nNumber of Telangana districts per year:")
log(tg.groupby("year")["district_code"].nunique().to_string())

tg_codes = set(tg["district_code"].unique())
other = df[~df["state_name"].str.contains("Telangana", case=False, na=False)
           & df["district_code"].isin(tg_codes)]
log(f"\nRows with a Telangana district code but a different state name: {len(other):,}")
if len(other):
    log(other.groupby(["state_name", "year"]).size().head(30).to_string())

(AUDIT_DIR / "crop_deep_check.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nDone. Saved data\\audits\\crop_deep_check.txt")