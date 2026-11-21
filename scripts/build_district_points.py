import re
import sys
from pathlib import Path
import pandas as pd
from pyproj import Transformer

RAW_PTS = Path("data/processed/district_boundary_points_raw.csv")
PROFILE = Path("data/processed/district_crop_profile.csv")
OUT = Path("data/processed/district_points.csv")
AUDIT = Path("data/audits/district_points_audit.txt")

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

pts = pd.read_csv(RAW_PTS)
pts["dtcode"] = pd.to_numeric(pts["dtcode"], errors="coerce")
log(f"Rows with a non-numeric dtcode (dropped): {int(pts['dtcode'].isna().sum())}")
pts = pts.dropna(subset=["dtcode"]).copy()
pts["dtcode"] = pts["dtcode"].astype(int)
pts["district"] = pts["district"].astype(str).str.strip()

# The columns named rep_lat / rep_lon actually hold map metres (y and x)
TOWNS = {
    "Hyderabad": (17.385, 78.487),
    "Adilabad": (19.66, 78.53),
    "Khammam": (17.25, 80.15),
    "Mahabubnagar": (16.74, 77.98),
    "Nizamabad": (18.67, 78.09),
    "Warangal": (17.97, 79.60),
}
CRS_LIST = [
    "EPSG:7755",
    "+proj=lcc +lat_1=12.472955 +lat_2=35.172806 +lat_0=24 +lon_0=80 "
    "+x_0=4000000 +y_0=4000000 +datum=WGS84 +units=m +no_defs",
]

chosen = None
for crs in CRS_LIST:
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(pts["rep_lon"].values, pts["rep_lat"].values)
    t = pts.assign(lat=lat, lon=lon)
    ok = bool((t["lat"].between(6, 38.5) & t["lon"].between(68, 98)).all())
    log(f"\nTrying {crs[:14]}: all points inside India = {ok}")
    for name, (la, lo) in TOWNS.items():
        r = t[(t["state_name"] == "Telangana") & (t["district"].str.lower() == name.lower())]
        if len(r) != 1:
            log(f"  {name}: expected 1 row, found {len(r)}")
            ok = False
            continue
        dlat = abs(r["lat"].iloc[0] - la)
        dlon = abs(r["lon"].iloc[0] - lo)
        good = max(dlat, dlon) <= 0.9
        ok = ok and good
        log(f"  {name}: ({r['lat'].iloc[0]:.2f}, {r['lon'].iloc[0]:.2f}) "
            f"expected near ({la}, {lo}) -> {'OK' if good else 'FAR'}")
    if ok:
        chosen = (tr, t)
        log("=> This projection passed all checks")
        break

if chosen is None:
    log("\nNo projection passed the checks. Nothing was saved. Send me this output.")
    AUDIT.write_text("\n".join(lines), encoding="utf-8")
    sys.exit(1)

tr, res = chosen
clon, clat = tr.transform(res["centroid_lon"].values, res["centroid_lat"].values)
res["centroid_lat"] = clat
res["centroid_lon"] = clon
res["approx_area_km2"] = (res["shape_area"] / 1e6).round(0)

crop = pd.read_csv(PROFILE)
cd = crop.drop_duplicates("district_code")[["state_name", "district_code", "district_name"]]
res["in_crop_profile"] = res["dtcode"].isin(set(cd["district_code"]))

miss = cd[~cd["district_code"].isin(set(res["dtcode"]))]
log(f"\nCrop-profile districts with NO polygon in the map: {len(miss)} of {len(cd)}")
log(miss.groupby("state_name").size().sort_values(ascending=False).to_string())
log(miss.sort_values(["state_name", "district_name"]).to_string(index=False))

dups = res[res.duplicated("dtcode", keep=False)]
log(f"\nCodes used by more than one polygon: {dups['dtcode'].nunique()}")
log(dups[["state_name", "dtcode", "district"]].to_string(index=False))

m = res.merge(cd, left_on="dtcode", right_on="district_code", suffixes=("_map", "_crop"))
m["same_name"] = m["district"].map(norm) == m["district_name"].map(norm)
m["same_state"] = m["state_name_map"].map(norm) == m["state_name_crop"].map(norm)
log(f"\nMatched by code: {len(m)}.  Names differ: {int((~m['same_name']).sum())}.  "
    f"States differ: {int((~m['same_state']).sum())}")
log("States that differ:")
log(m.loc[~m["same_state"], ["state_name_map", "state_name_crop", "dtcode",
                             "district", "district_name"]].to_string(index=False))
log("Names that differ (first 40):")
log(m.loc[~m["same_name"], ["state_name_map", "dtcode", "district",
                            "district_name"]].head(40).to_string(index=False))

tg = res[res["state_name"] == "Telangana"].sort_values("dtcode")
log("\nTelangana points:")
log(tg[["dtcode", "district", "lat", "lon", "approx_area_km2",
        "in_crop_profile"]].round(3).to_string(index=False))

keep = ["state_name", "stcode", "dtcode", "district", "lat", "lon", "centroid_lat",
        "centroid_lon", "approx_area_km2", "src_agency", "in_crop_profile"]
res[keep].round(5).to_csv(OUT, index=False)
AUDIT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved {OUT}")