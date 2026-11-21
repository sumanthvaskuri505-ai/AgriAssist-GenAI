import json
import re
import sys
from collections import Counter
from pathlib import Path
import pandas as pd

try:
    from shapely.geometry import shape
except ImportError:
    sys.exit("shapely is not installed. Run:  pip install shapely  and try again.")

RAW_DIR = Path("data/raw/district_boundary")
PROFILE = Path("data/processed/district_crop_profile.csv")
OUT_DIR = Path("data/processed")
AUDIT_DIR = Path("data/audits")
OUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

files = sorted(list(RAW_DIR.rglob("*.geojson")) + list(RAW_DIR.rglob("*.json")))
if not files:
    sys.exit(f"No .geojson or .json file found inside {RAW_DIR}. Did you extract the ZIP there?")
path = files[0]
log(f"Reading: {path}  ({path.stat().st_size / 1024**2:.1f} MiB)")

with open(path, "r", encoding="utf-8") as f:
    gj = json.load(f)
feats = gj.get("features", [])
log(f"Features: {len(feats)}")
log("Geometry types: " + str(dict(Counter((f.get("geometry") or {}).get("type") for f in feats))))

props = pd.DataFrame([f.get("properties") or {} for f in feats])
log(f"\nProperty fields: {list(props.columns)}")
log(props.head(3).to_string())

# ---- Representative point and centroid for every district ----
rows, bad, invalid = [], 0, 0
for f in feats:
    try:
        g = shape(f["geometry"])
        if not g.is_valid:
            invalid += 1
            g = g.buffer(0)
        rp, c = g.representative_point(), g.centroid
        rows.append((rp.y, rp.x, c.y, c.x))
    except Exception:
        rows.append((None, None, None, None))
        bad += 1
pts = pd.DataFrame(rows, columns=["rep_lat", "rep_lon", "centroid_lat", "centroid_lon"])
res = pd.concat([props.reset_index(drop=True), pts], axis=1)
log(f"\nGeometries that could not be read: {bad}   Invalid geometries repaired: {invalid}")
outside = ~(res["rep_lat"].between(6, 38.5) & res["rep_lon"].between(68, 98))
log(f"Points outside India's rough bounding box (lat 6-38.5, lon 68-98): {int(outside.sum())}")

# ---- Which field matches the district codes in the crop profile? ----
crop = pd.read_csv(PROFILE)
crop_d = crop.drop_duplicates("district_code")[["state_name", "district_code", "district_name"]]
crop_codes = set(crop_d["district_code"].astype(int))

cand = []
for col in props.columns:
    v = pd.to_numeric(props[col], errors="coerce")
    if v.notna().mean() < 0.9:
        continue
    vals = set(v.dropna().astype(int))
    cand.append((len(vals & crop_codes), col, len(vals)))
cand.sort(reverse=True)
log("\nNumeric fields by overlap with crop-profile district codes (overlap, field, unique values):")
for ov, col, n in cand[:6]:
    log(f"  {col}: overlap={ov}, unique={n}")

crop_names = set(crop_d["district_name"].map(norm))
ncand = []
for col in props.columns:
    if props[col].dtype != object:
        continue
    vals = set(props[col].dropna().map(norm))
    ncand.append((len(vals & crop_names), col, len(vals)))
ncand.sort(reverse=True)
log("\nText fields by overlap with crop-profile district NAMES (overlap, field, unique values):")
for ov, col, n in ncand[:6]:
    log(f"  {col}: overlap={ov}, unique={n}")

best_code = cand[0][1] if cand and cand[0][0] >= 100 else None
log(f"\nBest code field: {best_code}")

# ---- Telangana ----
text_cols = [c for c in props.columns if props[c].dtype == object]
mask = pd.Series(False, index=props.index)
for c in text_cols:
    mask |= props[c].astype(str).str.contains("telangana", case=False, na=False)
tg = res[mask]
log(f"\nFeatures mentioning Telangana in any text field: {len(tg)}")
if len(tg):
    log(tg.head(40).round(3).to_string(index=False))

if best_code:
    bcodes = set(pd.to_numeric(res[best_code], errors="coerce").dropna().astype(int))
    miss = crop_d[~crop_d["district_code"].isin(bcodes)]
    log(f"\nCrop-profile districts whose code is NOT in the boundary file: {len(miss)} of {len(crop_d)}")
    log(miss.groupby("state_name").size().sort_values(ascending=False).to_string())
    log("\nTelangana crop-profile districts missing from the boundary file:")
    log(miss[miss["state_name"].str.contains("Telangana", case=False, na=False)]
        [["district_code", "district_name"]].to_string(index=False))

res.to_csv(OUT_DIR / "district_boundary_points_raw.csv", index=False)
(AUDIT_DIR / "district_boundary_audit.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nSaved data\\processed\\district_boundary_points_raw.csv and data\\audits\\district_boundary_audit.txt")