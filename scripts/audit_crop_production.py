import sys
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw/crop_production")
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

csv_files = sorted(RAW_DIR.glob("*.csv"))
if not csv_files:
    sys.exit(f"No CSV found in {RAW_DIR}. Check where you saved the file.")
csv_path = csv_files[0]
print("Reading:", csv_path)

df = pd.read_csv(csv_path, low_memory=False)
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

lines = []
def log(text=""):
    print(text)
    lines.append(str(text))

log(f"File: {csv_path.name}")
log(f"Rows: {len(df):,}   Columns: {df.shape[1]}")
log(f"Column names: {list(df.columns)}")

log("\n--- Data types ---")
log(df.dtypes.to_string())

log("\n--- Missing values per column ---")
log(df.isna().sum().to_string())

log("\n--- Rows per year ---")
log(df["year"].astype(str).value_counts().sort_index().to_string())

log(f"\nUnique states: {df['state_name'].nunique()}")
log(f"Unique districts (by code): {df['district_code'].nunique()}")
log(f"Unique districts (by name): {df['district_name'].nunique()}")
log(f"Unique crop names: {df['crop_name'].nunique()}")
log(f"Unique crop codes: {df['crop_code'].nunique()}")

log("\n--- Seasons ---")
log(df["season"].value_counts(dropna=False).to_string())

log("\n--- Units (units may differ by crop) ---")
for col in ["area_unit", "production_unit", "yield_unit"]:
    log(f"\n{col}:")
    log(df[col].value_counts(dropna=False).to_string())

log("\n--- Crop type ---")
log(df["crop_type"].value_counts(dropna=False).to_string())

log("\n--- Numeric sanity checks ---")
for col in ["area", "production", "yield"]:
    s = pd.to_numeric(df[col], errors="coerce")
    log(f"{col}: missing={s.isna().sum():,}  zero={(s == 0).sum():,}  "
        f"negative={(s < 0).sum():,}  min={s.min()}  max={s.max()}")

# Does the stored yield roughly equal production / area? (only where units are Tonnes and Hectare)
mask = (
    (df["area_unit"] == "Hectare")
    & (df["production_unit"] == "Tonnes")
    & (df["area"] > 0)
)
calc = df.loc[mask, "production"] / df.loc[mask, "area"]
diff = (calc - df.loc[mask, "yield"]).abs()
log(f"\nYield consistency (Tonnes/Hectare rows only): {mask.sum():,} rows checked, "
    f"{(diff > 0.05).sum():,} differ by more than 0.05")

dups = df.duplicated(subset=["year", "district_code", "crop_code", "season"]).sum()
log(f"\nDuplicate rows on (year, district_code, crop_code, season): {dups:,}")

log("\n--- Telangana check (our target state) ---")
tg = df[df["state_name"].str.contains("Telangana", case=False, na=False)]
log(f"Telangana rows: {len(tg):,}")
if len(tg):
    log(f"Telangana districts: {tg['district_name'].nunique()}")
    log(f"Telangana years: {sorted(tg['year'].astype(str).unique())}")
    log("Telangana district names:")
    log(", ".join(sorted(tg["district_name"].dropna().unique())))

df.groupby("state_name")["district_code"].nunique().rename("districts") \
  .to_csv(AUDIT_DIR / "crop_state_district_counts.csv")
df.groupby(["crop_code", "crop_name"]).size().rename("rows") \
  .to_csv(AUDIT_DIR / "crop_name_code_counts.csv")
df.groupby(["crop_name", "area_unit", "production_unit", "yield_unit"]).size() \
  .rename("rows").to_csv(AUDIT_DIR / "crop_units_by_crop.csv")

(AUDIT_DIR / "crop_audit_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nDone. Files saved in", AUDIT_DIR)