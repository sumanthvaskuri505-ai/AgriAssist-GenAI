import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
import pandas as pd

POINTS = Path("data/processed/district_points.csv")
RAIN_YEAR = Path("data/processed/rainfall_district_year.csv")
RAW_DIR = Path("data/raw/nasa_power")
OUT_DIR = Path("data/processed")
AUDIT = Path("data/audits/nasa_power_telangana.txt")
RAW_DIR.mkdir(parents=True, exist_ok=True)

START, END = "20180101", "20231231"
PARAMS = "T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR"
BASE = "https://power.larc.nasa.gov/api/temporal/daily/point"

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))
def finish(code=0):
    AUDIT.write_text("\n".join(lines), encoding="utf-8")
    sys.exit(code)

def fetch(code, lat, lon):
    cache = RAW_DIR / f"power_{code}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    query = {"parameters": PARAMS, "community": "AG", "longitude": f"{lon:.4f}",
             "latitude": f"{lat:.4f}", "start": START, "end": END, "format": "JSON"}
    url = BASE + "?" + urllib.parse.urlencode(query)
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (AgriAssist data pull)"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = resp.read().decode("utf-8")
            js = json.loads(body)
            cache.write_text(body, encoding="utf-8")
            time.sleep(1)
            return js
        except Exception as e:
            log(f"  attempt {attempt} failed for code {code}: {e}")
            time.sleep(5)
    return None

pts = pd.read_csv(POINTS)
tg = pts[pts["state_name"] == "Telangana"].sort_values("dtcode")
log(f"Telangana points: {len(tg)}")

names = PARAMS.split(",")
frames, failed, api_version = [], [], None
for r in tg.itertuples():
    js = fetch(int(r.dtcode), float(r.lat), float(r.lon))
    if js is None:
        failed.append(r.district)
        continue
    par = js.get("properties", {}).get("parameter", {})
    if not all(p in par for p in names):
        failed.append(r.district)
        log(f"  {r.district}: parameters missing in response")
        continue
    if api_version is None:
        api_version = js.get("header", {}).get("api", {}).get("version")
    fill = js.get("header", {}).get("fill_value", -999)
    d = pd.DataFrame(par)
    d.index = pd.to_datetime(d.index, format="%Y%m%d")
    d = d.replace(fill, float("nan"))
    d.index.name = "date"
    d = d.reset_index()
    d.insert(0, "dtcode", int(r.dtcode))
    d.insert(1, "district", r.district)
    frames.append(d)
    print(f"  {r.district}: ok")

if not frames:
    log("Nothing downloaded.")
    finish(1)

w = pd.concat(frames, ignore_index=True)
w.to_csv(OUT_DIR / "weather_power_telangana_daily.csv", index=False)
log(f"\nDistricts pulled: {w['dtcode'].nunique()} of {len(tg)}.  Failed: {failed}")
log(f"Rows: {len(w):,}")
log("Missing values per parameter:")
log(w[names].isna().sum().to_string())

w["year"] = w["date"].dt.year
w["month"] = w["date"].dt.month
mon = w[w["month"].between(6, 9)]

s_mon = mon.groupby(["dtcode", "year"])["PRECTOTCORR"].sum().rename("monsoon_mm").reset_index()
parts = [
    s_mon.groupby("dtcode")["monsoon_mm"].mean().rename("monsoon_mm_mean"),
    w.groupby(["dtcode", "year"])["PRECTOTCORR"].sum().groupby(level="dtcode")
     .mean().rename("annual_mm_mean"),
    w.groupby("dtcode")["T2M"].mean().rename("t2m_mean_c"),
    w[w["month"].between(3, 5)].groupby("dtcode")["T2M_MAX"].mean().rename("tmax_mar_may_c"),
    w[w["month"].isin([12, 1, 2])].groupby("dtcode")["T2M_MIN"].mean().rename("tmin_dec_feb_c"),
    mon.groupby("dtcode")["RH2M"].mean().rename("rh_jun_sep_pct"),
]
summ = pd.concat(parts, axis=1).round(1).reset_index()
summ = summ.merge(tg[["dtcode", "district", "lat", "lon"]], on="dtcode")
summ = summ[["dtcode", "district", "lat", "lon", "monsoon_mm_mean", "annual_mm_mean",
             "t2m_mean_c", "tmax_mar_may_c", "tmin_dec_feb_c", "rh_jun_sep_pct"]]
summ.to_csv(OUT_DIR / "weather_power_telangana_profile.csv", index=False)
log("\n=== Telangana weather profile, 2018-2023 (NASA POWER) ===")
log(summ.drop(columns=["lat", "lon"]).to_string(index=False))

ry = pd.read_csv(RAIN_YEAR)
ry["monsoon_complete"] = ry["monsoon_complete"].astype(str).str.lower().eq("true")
ry = ry.rename(columns={"district_code": "dtcode", "monsoon_mm": "file_mm"})
cmp_ = s_mon.merge(ry[["dtcode", "year", "file_mm", "monsoon_complete"]],
                   on=["dtcode", "year"], how="inner")
cmp_ = cmp_[cmp_["monsoon_complete"]].copy()
cmp_["ratio"] = cmp_["monsoon_mm"] / cmp_["file_mm"]
per = cmp_.groupby("dtcode").agg(years=("year", "nunique"),
                                 power_mean=("monsoon_mm", "mean"),
                                 file_mean=("file_mm", "mean"),
                                 ratio_mean=("ratio", "mean"),
                                 ratio_min=("ratio", "min"),
                                 ratio_max=("ratio", "max")).reset_index()
per = per.merge(tg[["dtcode", "district"]], on="dtcode").round(2)
log("\n=== POWER vs the district rainfall file (complete years only) ===")
log(per[["district", "years", "power_mean", "file_mean", "ratio_mean",
         "ratio_min", "ratio_max"]].to_string(index=False))
log(f"\nDistrict-years compared: {len(cmp_)}.  POWER lower than the file in "
    f"{int((cmp_['ratio'] < 1).sum())} of them.")
log(f"Ratio POWER/file: median {cmp_['ratio'].median():.2f}, "
    f"min {cmp_['ratio'].min():.2f}, max {cmp_['ratio'].max():.2f}")

readme = [
    "WEATHER DATA - SOURCE AND PROCESSING NOTES",
    "",
    "Source: NASA POWER Project, Daily API (point endpoint), community AG.",
    f"API version: {api_version}.  Date accessed: {date.today().isoformat()}.",
    "Data sources reported in the response header: MERRA2 and POWER.",
    "Parameters: T2M, T2M_MAX, T2M_MIN (degrees C), RH2M (percent),",
    "PRECTOTCORR (mm/day, labelled Precipitation Corrected).",
    "Period: 2018-01-01 to 2023-12-31.",
    "Licence: NASA states there are no restrictions on use and asks users to cite POWER;",
    "the project page lists CC BY 4.0.",
    "Requested acknowledgement: These data were obtained from the NASA Langley Research",
    "Center POWER Project funded through the NASA Earth Science Directorate Applied",
    "Science Program.",
    "",
    "Processing notes:",
    "- One request per district, at a point inside the district polygon (district_points.csv).",
    "- The point comes from the Survey of India district boundary on the National Water",
    "  Data Portal (licence listed there as Other (Open)).",
    "- POWER values are modelled gridded data (about 50 km cells), not station measurements.",
    "- In a test, POWER monsoon rainfall read lower than the India district rainfall file.",
    "  Do not mix the two sources in one comparison.",
]
(OUT_DIR / "README_weather_data.txt").write_text("\n".join(readme), encoding="utf-8")
log("\nSaved weather_power_telangana_daily.csv, weather_power_telangana_profile.csv, README_weather_data.txt")
finish(0)