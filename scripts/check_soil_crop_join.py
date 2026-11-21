import re
from pathlib import Path
import pandas as pd
import os; SOIL_CSV = Path(os.environ.get("AGRI_SOIL_CSV", "data/raw/soil/soil_health_india.csv"))
CROP_CSV = sorted(Path("data/raw/crop_production").glob("*.csv"))[0]
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

lines = []
def log(text=""):
    print(text)
    lines.append(str(text))

def norm(name):
    """lowercase and keep only letters/digits, so 'Ranga Reddy' == 'rangareddy'"""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())

# ---- Soil: read ONLY 4 columns, in chunks, keep unique districts ----
print("Reading soil file in chunks (this can take a few minutes)...")
parts = []
cols = ["state_code", "state_name", "district_code", "district_name"]
for chunk in pd.read_csv(SOIL_CSV, usecols=cols, chunksize=1_000_000):
    parts.append(chunk.drop_duplicates())
soil = pd.concat(parts).drop_duplicates().reset_index(drop=True)

# ---- Crop: small file, read normally ----
crop = pd.read_csv(CROP_CSV, usecols=["year", "state_code", "state_name",
                                      "district_code", "district_name"])

log(f"Soil: {len(soil):,} unique (state, district) rows, "
    f"{soil['district_code'].nunique()} district codes, "
    f"{soil['state_code'].nunique()} state codes")
log(f"Crop: {crop['district_code'].nunique()} district codes, "
    f"{crop['state_code'].nunique()} state codes")

# Does a district code ever belong to 2 different states within one dataset?
for label, d in [("Soil", soil), ("Crop", crop)]:
    n = d.groupby("district_code")["state_code"].nunique()
    log(f"{label}: district codes used by more than one state code: {(n > 1).sum()}")

# ---- 1. Match on district code ----
soil_codes = set(soil["district_code"])
crop_codes_all = set(crop["district_code"])
latest = crop[crop["year"] == "2022-2023"]
crop_codes_latest = set(latest["district_code"])

log("\n=== MATCH BY district_code ===")
log(f"Soil districts found in crop data (any year):  "
    f"{len(soil_codes & crop_codes_all)} of {len(soil_codes)}")
log(f"Soil districts found in crop data (2022-2023): "
    f"{len(soil_codes & crop_codes_latest)} of {len(soil_codes)}")
log(f"Crop districts (any year) with no soil data:   "
    f"{len(crop_codes_all - soil_codes)} of {len(crop_codes_all)}")

# ---- 2. Do the NAMES agree for matching codes? ----
crop_names = (crop.drop_duplicates(["district_code", "district_name"])
                  .assign(n=lambda d: d["district_name"].map(norm))
                  .groupby("district_code")["n"].apply(set))
rows = []
for _, r in soil.drop_duplicates("district_code").iterrows():
    code = r["district_code"]
    if code in crop_names.index:
        if norm(r["district_name"]) not in crop_names[code]:
            rows.append({"state": r["state_name"], "district_code": code,
                         "soil_name": r["district_name"],
                         "crop_names": " | ".join(sorted(
                             crop.loc[crop["district_code"] == code, "district_name"].unique()))})
mism = pd.DataFrame(rows)
log(f"\nCodes that match but NAMES differ: {len(mism)}")
if len(mism):
    log(mism.head(40).to_string(index=False))
mism.to_csv(AUDIT_DIR / "join_name_mismatches.csv", index=False)

# ---- 3. Soil districts with no crop match ----
miss = soil[~soil["district_code"].isin(crop_codes_all)].drop_duplicates("district_code")
log(f"\nSoil districts with NO code in crop data: {len(miss)}")
if len(miss):
    log(miss.sort_values(["state_name", "district_name"]).to_string(index=False))
miss.to_csv(AUDIT_DIR / "join_soil_codes_missing_in_crop.csv", index=False)

# ---- 4. Soil districts that have a code but no 2022-2023 crop data ----
nolatest = soil[soil["district_code"].isin(crop_codes_all - crop_codes_latest)]
nolatest = nolatest.drop_duplicates("district_code")
log(f"\nSoil districts whose code exists in crop data but NOT in 2022-2023: {len(nolatest)}")
if len(nolatest):
    log(nolatest.sort_values(["state_name", "district_name"]).head(40).to_string(index=False))

# ---- 5. Telangana ----
log("\n=== TELANGANA ===")
tg_soil = soil[soil["state_name"].str.contains("Telangana", case=False, na=False)] \
            .drop_duplicates("district_code")
tg_crop = crop[crop["state_name"].str.contains("Telangana", case=False, na=False)]
tg_latest = set(tg_crop.loc[tg_crop["year"] == "2022-2023", "district_code"])
log(f"Telangana districts in soil data: {len(tg_soil)}")
log(f"  ... of which in crop data 2022-2023: {len(set(tg_soil['district_code']) & tg_latest)}")
log("Soil Telangana districts NOT in crop 2022-2023:")
log(", ".join(sorted(tg_soil.loc[~tg_soil["district_code"].isin(tg_latest), "district_name"])) or "(none)")

(AUDIT_DIR / "join_check_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nDone. Saved data\\audits\\join_check_summary.txt")