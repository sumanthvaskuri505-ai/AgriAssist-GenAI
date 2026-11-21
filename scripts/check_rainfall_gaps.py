import re
import sys
from pathlib import Path
import pandas as pd

RAW = sorted(Path("data/raw/rainfall_daily").glob("*.csv"))[0]
PROFILE = Path("data/processed/district_crop_profile.csv")
AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

lines = []
def log(t=""):
    print(t)
    lines.append(str(t))

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

parts, names = [], []
for chunk in pd.read_csv(RAW, chunksize=500_000, low_memory=False):
    chunk.columns = [c.strip().lower().replace(" ", "_") for c in chunk.columns]
    names.append(chunk[["state_name", "district_code", "district_name"]].drop_duplicates())
    sub = chunk[["date", "district_code", "actual"]].copy()
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub["district_code"] = pd.to_numeric(sub["district_code"], errors="coerce")
    sub["actual"] = pd.to_numeric(sub["actual"], errors="coerce").astype("float32")
    parts.append(sub)
    print(f"  ...read {sum(len(p) for p in parts):,} rows")

df = pd.concat(parts, ignore_index=True).dropna(subset=["date", "district_code"])
df["district_code"] = df["district_code"].astype(int)
df["year"] = df["date"].dt.year

nm = pd.concat(names).drop_duplicates()
nm["district_code"] = pd.to_numeric(nm["district_code"], errors="coerce")
nm = nm.dropna(subset=["district_code"])
nm["district_code"] = nm["district_code"].astype(int)
name_one = nm.drop_duplicates("district_code").set_index("district_code")

# ---- 1. Codes with more than one name or state ----
multi = nm.groupby("district_code").agg(n_names=("district_name", "nunique"),
                                        n_states=("state_name", "nunique"))
multi = multi[(multi["n_names"] > 1) | (multi["n_states"] > 1)]
log(f"=== 1. District codes with more than one name or state: {len(multi)} ===")
if len(multi):
    log(multi.join(name_one).to_string())

# ---- 2. Districts with no real rainfall value at all ----
nn = df.groupby("district_code")["actual"].agg(rows="size", real_values="count")
blank = nn[nn["real_values"] == 0].join(name_one)
log(f"\n=== 2. Districts with NO real rainfall values in the whole file: {len(blank)} ===")
log(blank[["state_name", "district_name", "rows"]].to_string())

# ---- 3. Districts with many blank days in 2020-2023 ----
x = df[df["year"].between(2020, 2023) & ~df["district_code"].isin(blank.index)]
bl = (x.groupby(["district_code", "year"])["actual"]
        .apply(lambda s: int(s.isna().sum())).rename("blank_days").reset_index())
big_gap = bl[bl["blank_days"] > 30].merge(name_one.reset_index(), on="district_code", how="left")
log(f"\n=== 3. District-years in 2020-2023 with more than 30 blank days: {len(big_gap)} ===")
log(big_gap.sort_values("blank_days", ascending=False)
           [["year", "state_name", "district_name", "blank_days"]].head(20).to_string(index=False))

# ---- 4. How empty is 2024? ----
y = df[df["year"] == 2024]
m = y.groupby(y["date"].dt.month)["actual"].agg(rows="size", real="count")
m["pct_real"] = (100 * m["real"] / m["rows"]).round(1)
log("\n=== 4. 2024 by month: share of rows with a real value ===")
log(m.to_string())

# ---- 5. Duplicates ----
dd = df[df.duplicated(["district_code", "date"], keep=False)]
g = dd.groupby(["district_code", "date"])["actual"].agg(copies="size", distinct_values="nunique")
log(f"\n=== 5. Duplicate (district, date) groups: {len(g):,} ===")
log(f"Groups whose copies have DIFFERENT rainfall values: {int((g['distinct_values'] > 1).sum()):,}")
by_d = (dd.groupby("district_code").size().rename("dup_rows").to_frame().join(name_one))
log("Districts with the most duplicate rows:")
log(by_d.sort_values("dup_rows", ascending=False).head(12)[["state_name", "district_name", "dup_rows"]].to_string())
conf = g[g["distinct_values"] > 1].reset_index().head(3)
for r in conf.itertuples():
    log(f"\nExample conflicting duplicate: district_code={r.district_code}, date={r.date.date()}")
    log(df[(df["district_code"] == r.district_code) & (df["date"] == r.date)].to_string(index=False))

# ---- 6. Extreme daily values ----
big = df[df["actual"] > 300].merge(name_one.reset_index(), on="district_code", how="left")
log(f"\n=== 6. Daily values above 300: {len(big)} ===")
log(big.sort_values("actual", ascending=False)
       [["date", "state_name", "district_name", "actual"]].head(15).to_string(index=False))

# ---- 7. Telangana mapping ----
log("\n=== 7. Telangana ===")
prof = pd.read_csv(PROFILE)
tgp = (prof[prof["state_name"].str.contains("Telangana", case=False, na=False)]
       .drop_duplicates("district_code")[["district_code", "district_name"]])
have = set(df.loc[df["actual"].notna() & (df["year"] >= 2018), "district_code"])

tgw = nm[nm["state_name"].str.contains("Telangana", case=False, na=False)]
tgw = tgw.merge(nn.reset_index(), on="district_code", how="left")
tgw["in_crop_profile"] = tgw["district_code"].isin(set(tgp["district_code"]))
log(f"Districts labelled Telangana in the rainfall file: {len(tgw)}")
log(tgw[["district_code", "district_name", "rows", "real_values", "in_crop_profile"]]
    .to_string(index=False))

missing = tgp[~tgp["district_code"].isin(have)]
log(f"\nTelangana crop-profile districts WITHOUT usable rainfall (2018+): {len(missing)}")
wnorm = {norm(r.district_name): (r.district_code, r.state_name) for r in nm.itertuples()}
rows = []
for r in missing.itertuples():
    hit = wnorm.get(norm(r.district_name))
    rows.append({"crop_code": r.district_code, "district": r.district_name,
                 "same_name_in_rain_file": hit is not None,
                 "rain_code": hit[0] if hit else "",
                 "rain_state": hit[1] if hit else ""})
log(pd.DataFrame(rows).to_string(index=False))

(AUDIT_DIR / "rainfall_gap_check.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nSaved data\\audits\\rainfall_gap_check.txt")