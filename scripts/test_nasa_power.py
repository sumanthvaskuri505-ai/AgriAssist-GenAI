import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd

POINTS = Path("data/processed/district_points.csv")
RAIN_YEAR = Path("data/processed/rainfall_district_year.csv")
OUT_DIR = Path("data/raw/nasa_power_test")
AUDIT = Path("data/audits/nasa_power_test.txt")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DISTRICT_CODE = 516          # Nizamabad
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

pts = pd.read_csv(POINTS)
row = pts[pts["dtcode"] == DISTRICT_CODE]
if len(row) != 1:
    log(f"Expected 1 point for code {DISTRICT_CODE}, found {len(row)}")
    finish(1)
row = row.iloc[0]
lat, lon = float(row["lat"]), float(row["lon"])
log(f"District: {row['district']} ({row['state_name']}), code {DISTRICT_CODE}, "
    f"point = ({lat:.4f}, {lon:.4f}), area about {row['approx_area_km2']} km2")

query = {"parameters": PARAMS, "community": "AG", "longitude": f"{lon:.4f}",
         "latitude": f"{lat:.4f}", "start": START, "end": END, "format": "JSON"}
url = BASE + "?" + urllib.parse.urlencode(query)
log("Request URL: " + url)

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AgriAssist data test)"})
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
        log(f"HTTP status: {resp.status}   bytes: {len(body):,}")
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")[:1500]
    log(f"HTTP error {e.code}: {detail}")
    finish(1)
except Exception as e:
    log(f"Request failed: {e}")
    finish(1)

(OUT_DIR / f"power_{DISTRICT_CODE}.json").write_text(body, encoding="utf-8")
js = json.loads(body)
log(f"\nTop-level keys: {list(js.keys())}")
header = js.get("header", {})
log(f"Header: {json.dumps(header)[:700]}")
if js.get("messages"):
    log(f"Messages: {js['messages']}")
meta = js.get("parameters", {})
log("\nParameter metadata (units):")
for k, v in meta.items():
    log(f"  {k}: {v}")

par = js.get("properties", {}).get("parameter", {})
missing_names = [p for p in PARAMS.split(",") if p not in par]
log(f"\nParameters returned: {list(par.keys())}")
if missing_names:
    log(f"NOT RETURNED: {missing_names}")
    finish(1)

fill = header.get("fill_value", -999)
df = pd.DataFrame(par)
df.index = pd.to_datetime(df.index, format="%Y%m%d")
df = df.replace(fill, float("nan"))
df.to_csv(OUT_DIR / f"power_{DISTRICT_CODE}_daily.csv")

log(f"\nDays: {len(df)}   from {df.index.min().date()} to {df.index.max().date()}   fill value: {fill}")
log("Missing days per parameter:")
log(df.isna().sum().to_string())
log("\nSummary:")
log(df.describe().round(2).to_string())

# ---- Yearly comparison ----
jj = df["PRECTOTCORR"][df.index.month.isin([6, 7, 8, 9])]
g = jj.groupby(jj.index.year).agg(power_monsoon=("sum"), power_days=("count"))
g.index.name = "year"
g = g.reset_index()

ry = pd.read_csv(RAIN_YEAR)
ry = ry[ry["district_code"] == DISTRICT_CODE][["year", "monsoon_mm", "monsoon_days", "monsoon_complete"]]
cmp_ = g.merge(ry, on="year", how="left")
cmp_["power_minus_file"] = (cmp_["power_monsoon"] - cmp_["monsoon_mm"]).round(1)
cmp_["power_over_file"] = (cmp_["power_monsoon"] / cmp_["monsoon_mm"]).round(2)
log("\n=== June-September rainfall by year: POWER vs the district rainfall file ===")
log("(POWER units are in the metadata above; the file's units are assumed to be mm)")
log(cmp_.round(1).to_string(index=False))

jjall = df[df.index.month.isin([6, 7, 8, 9])]
yearly = pd.DataFrame({
    "T2M_mean": df["T2M"].groupby(df.index.year).mean(),
    "T2M_MAX_mean": df["T2M_MAX"].groupby(df.index.year).mean(),
    "T2M_MIN_mean": df["T2M_MIN"].groupby(df.index.year).mean(),
    "RH2M_JJAS_mean": jjall["RH2M"].groupby(jjall.index.year).mean(),
}).round(1)
log("\n=== Yearly temperature and humidity ===")
log(yearly.to_string())

finish(0)