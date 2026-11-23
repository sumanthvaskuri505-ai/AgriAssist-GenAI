"""District context for AgriAssist.

Loads the Telangana district cards and turns one district's card into a short
text block for the advisory prompt. Standard library only. If the data file is
missing, every function returns an empty result so the rest of the app works.
"""
import json
from pathlib import Path

CARD_FILE = (Path(__file__).resolve().parent.parent
             / "app_data" / "district_context" / "telangana_district_context.json")

MIN_SAMPLES = 100
_cards = None


def _load():
    global _cards
    if _cards is None:
        try:
            with open(CARD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cards = {int(c["district_code"]): c for c in data}
        except Exception:
            _cards = {}
    return _cards


def _get(code):
    try:
        return _load().get(int(code))
    except (TypeError, ValueError):
        return None


def _num(x, spec):
    return format(x, spec) if isinstance(x, (int, float)) else "n/a"


def list_districts():
    items = [{"code": code, "name": c["district"]} for code, c in _load().items()]
    return sorted(items, key=lambda item: item["name"])


def get_label(code):
    c = _get(code)
    return f"{c['district']}, {c['state']}" if c else ""


def build_context_text(code, top_crops=5):
    c = _get(code)
    if not c:
        return ""

    lines = [f"District: {c['district']}, {c['state']} "
             f"(code {c['district_code']}, about {_num(c.get('approx_area_km2'), ',.0f')} km2)"]

    # ---- Soil ----
    soil = c.get("soil") or {}
    nutrients = soil.get("nutrients") or []
    lines.append("")
    if nutrients:
        lines.append(
            f"SOIL - Soil Health Card records, {soil.get('year')}. Figures are the share of "
            "tested soil samples in each class, NOT measured nutrient amounts. Samples were "
            "farmer-requested, not a random sample of all land.")
        for n in nutrients:
            samples = n.get("samples") or 0
            if samples < MIN_SAMPLES or n.get("low_sample_flag"):
                lines.append(f"- {n['nutrient']}: NO RELIABLE DATA ({samples} samples). "
                             "Do not draw conclusions.")
                continue
            levels = [(k, v) for k, v in (n.get("levels_pct") or {}).items() if v is not None]
            levels.sort(key=lambda kv: kv[1], reverse=True)
            text = ", ".join(f"{k} {v:.0f}%" for k, v in levels)
            lines.append(f"- {n['nutrient']}: {text} ({samples:,} samples)")
    else:
        lines.append("SOIL - No Soil Health Card records are available for this district.")

    # ---- Crops ----
    crops = c.get("crops") or {}
    seasons = crops.get("seasons") or {}
    if seasons:
        lines.append("")
        lines.append(
            f"CROPS - reported district statistics (Directorate of Economics and Statistics), "
            f"{crops.get('window')}. Area shares are among the crops recorded in the dataset; "
            "fruits and vegetables are mostly missing from recent years. These figures show "
            "what has been grown, not what will suit a particular field.")
        order = sorted(seasons, key=lambda s: (s not in ("Kharif", "Rabi"), s))
        for season in order:
            items = (seasons[season] or [])[:top_crops]
            if not items:
                continue
            lines.append(f"{season} season, largest crops by area:")
            for x in items:
                y = x.get("weighted_yield_t_per_ha")
                yn = x.get("weighted_yield_nuts_per_ha")
                if y is not None:
                    lo, hi = x.get("min_yield_t_per_ha"), x.get("max_yield_t_per_ha")
                    rng = (f", yearly range {_num(lo, '.2f')}-{_num(hi, '.2f')}"
                           if lo is not None and hi is not None else "")
                    ytxt = f"yield {y:.2f} t/ha{rng}"
                elif yn is not None:
                    ytxt = f"yield {yn:,.0f} nuts/ha"
                else:
                    ytxt = "yield not available"
                lines.append(
                    f"- {x.get('crop_name')}: about {_num(x.get('mean_area_ha'), ',.0f')} ha per year "
                    f"({_num(x.get('pct_of_district_season_area'), '.0f')}% of recorded {season} area), "
                    f"{ytxt}, {x.get('years_with_area')} years of data")
    else:
        lines.append("")
        lines.append("CROPS - No crop statistics are available for this district in the 2018-2023 window.")

    # ---- Weather ----
    w = c.get("weather") or {}
    v = w.get("values") or {}
    if v:
        lines.append("")
        lines.append(f"WEATHER - NASA POWER modelled estimates, {w.get('period')} "
                     "(not station measurements; grid cells are about 50 km wide):")
        lines.append(f"- Monsoon (June-September) rainfall about {_num(v.get('monsoon_mm_mean'), '.0f')} mm "
                     f"per year; annual rainfall about {_num(v.get('annual_mm_mean'), '.0f')} mm")
        lines.append(f"- Mean air temperature {_num(v.get('t2m_mean_c'), '.1f')} C; average daily maximum "
                     f"in March-May {_num(v.get('tmax_mar_may_c'), '.1f')} C; average daily minimum in "
                     f"December-February {_num(v.get('tmin_dec_feb_c'), '.1f')} C")
        lines.append(f"- Relative humidity in June-September about {_num(v.get('rh_jun_sep_pct'), '.0f')}%")
        shared = w.get("shares_grid_cell_with") or []
        if shared:
            lines.append(f"- Identical values are used for {', '.join(shared)} because they fall "
                         "in the same grid cell.")

    return "\n".join(lines)