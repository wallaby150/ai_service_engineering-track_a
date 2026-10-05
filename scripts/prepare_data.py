"""data/raw/worldbank/ → data/snapshot/countries.json + MANIFEST.json + reports/prepare_report.txt

원칙 (docs/probability-model.md):
- 값이 없으면 0이 아니라 None. 빠지는 국가는 사유를 붙여 리포트에 남긴다
- 확률은 여기서 계산하지 않는다. 스냅샷에는 원 통계만 싣고, 확률은 core/가 낸다
- 입력 = 출력 + 제외 가 맞지 않으면 실패한다

    python scripts/prepare_data.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

from babel import Locale

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "worldbank"
SNAPSHOT_DIR = ROOT / "data" / "snapshot"
REPORT_PATH = ROOT / "reports" / "prepare_report.txt"

# CLDR 한국어 이름이 어색하거나 없는 곳만 손으로 고친다
NAME_OVERRIDES = {
    "CD": "콩고민주공화국",
    "CG": "콩고공화국",
    "JG": "채널 제도",
    "KP": "북한",
    "KR": "대한민국",
}

SOURCE_LABELS = {
    "births": "World Bank WDI SP.DYN.CBRT.IN × SP.POP.TOTL",
    "sex_ratio": "World Bank WDI SP.POP.BRTH.MF",
    "survival": "UN IGME via World Bank WDI SP.DYN.IMRT.* / SH.DYN.MORT.*",
    "economy": "World Bank PIP SI.POV.DDAY / SI.POV.LMIC / SI.POV.UMIC (2021 PPP)",
    "life_expectancy": "World Bank WDI SP.DYN.LE00.MA.IN / SP.DYN.LE00.FE.IN",
}


def load(code: str) -> dict:
    """지표 하나 → {iso3: (value, year)} . 값이 None인 행은 버린다."""
    rows = json.loads((RAW_DIR / f"{code}.json").read_text())
    out = {}
    for r in rows:
        iso3 = r.get("countryiso3code")
        if iso3 and r.get("value") is not None:
            out[iso3] = (float(r["value"]), int(r["date"]))
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def korean_name(iso2: str, english: str, locale: Locale) -> tuple:
    if iso2 in NAME_OVERRIDES:
        return NAME_OVERRIDES[iso2], False
    name = locale.territories.get(iso2)
    if name:
        return name, False
    return english, True  # 한국어 이름이 없다 — 리포트에 남긴다


def survival_for(iso3: str, sex: str, ind: dict, notes: list) -> Optional[dict]:
    imr = ind[f"imr_{sex}"].get(iso3)
    u5 = ind[f"u5mr_{sex}"].get(iso3)
    assumed = False
    if imr is None or u5 is None:
        imr, u5 = ind["imr_total"].get(iso3), ind["u5mr_total"].get(iso3)
        assumed = True
    if imr is None or u5 is None:
        return None
    if u5[0] < imr[0]:
        notes.append(f"{iso3} {sex}: 5세 미만 사망률({u5[0]}) < 영아사망률({imr[0]}) — 생존 데이터 없음 처리")
        return None
    return {"imr": imr[0], "u5mr": u5[0], "year": max(imr[1], u5[1]), "assumed_from_total": assumed}


def economy_for(iso3: str, ind: dict, notes: list) -> Optional[dict]:
    vals = [ind[k].get(iso3) for k in ("poverty_3_00", "poverty_4_20", "poverty_8_30")]
    if any(v is None for v in vals):
        return None
    p300, p420, p830 = (v[0] for v in vals)
    years = {v[1] for v in vals}
    if not (0 <= p300 <= p420 <= p830 <= 100):
        notes.append(f"{iso3}: 빈곤율이 누적 순서가 아님 ({p300}, {p420}, {p830}) — 경제 데이터 없음 처리")
        return None
    if len(years) > 1:
        notes.append(f"{iso3}: 빈곤율 세 값의 연도가 다름 {sorted(years)}")
    return {"pct_below_3_00": p300, "pct_below_4_20": p420, "pct_below_8_30": p830, "year": max(years)}


def main() -> None:
    if not RAW_DIR.exists():
        sys.exit("data/raw/worldbank 가 없다. 먼저 python scripts/fetch_worldbank.py")

    fetch_meta = json.loads((RAW_DIR / "_fetch.json").read_text())
    names = fetch_meta["indicators"]
    ind = {name: load(code) for code, name in names.items()}
    countries = json.loads((RAW_DIR / "countries.json").read_text())
    locale = Locale("ko")

    aggregates = [c for c in countries if c["region"]["value"].strip() == "Aggregates"]
    economies = [c for c in countries if c["region"]["value"].strip() != "Aggregates"]

    kept, excluded, notes, english_names = [], [], [], []
    for c in economies:
        iso3, iso2 = c["id"], c["iso2Code"]
        cbr, pop = ind["crude_birth_rate"].get(iso3), ind["population"].get(iso3)
        if cbr is None or pop is None:
            missing = [n for n, v in (("조출생률", cbr), ("총인구", pop)) if v is None]
            excluded.append((iso3, c["name"], f"{'·'.join(missing)} 없음 — 출생아 수를 셀 수 없다"))
            continue

        name_ko, fell_back = korean_name(iso2, c["name"], locale)
        if fell_back:
            english_names.append(f"{iso3} {c['name']}")

        sr = ind["sex_ratio_at_birth"].get(iso3)
        le_m, le_f = ind["life_exp_male"].get(iso3), ind["life_exp_female"].get(iso3)
        kept.append({
            "iso3": iso3,
            "iso2": iso2,
            "name_ko": name_ko,
            "name_en": c["name"],
            "region": c["region"]["value"].strip(),
            "income_level": c["incomeLevel"]["value"],
            "births": round(cbr[0] * pop[0] / 1000),
            "births_basis": {"crude_birth_rate": cbr[0], "cbr_year": cbr[1],
                             "population": int(pop[0]), "population_year": pop[1]},
            "sex_ratio": {"value": sr[0], "year": sr[1]} if sr else None,
            "survival": {
                "male": survival_for(iso3, "male", ind, notes),
                "female": survival_for(iso3, "female", ind, notes),
            },
            "economy": economy_for(iso3, ind, notes),
            "life_expectancy": {
                "male": le_m[0] if le_m else None,
                "female": le_f[0] if le_f else None,
                "year": max(v[1] for v in (le_m, le_f) if v) if (le_m or le_f) else None,
            },
        })

    if len(economies) != len(kept) + len(excluded):
        sys.exit(f"검산 실패: {len(economies)} != {len(kept)} + {len(excluded)}")

    kept.sort(key=lambda r: -r["births"])
    total_births = sum(r["births"] for r in kept)

    def share(pred) -> float:
        return sum(r["births"] for r in kept if pred(r)) / total_births

    coverage = {
        "sex_ratio": share(lambda r: r["sex_ratio"] is not None),
        "survival": share(lambda r: r["survival"]["male"] and r["survival"]["female"]),
        "economy": share(lambda r: r["economy"] is not None),
    }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {"sources": SOURCE_LABELS, "total_births": total_births, "countries": kept}
    snap_path = SNAPSHOT_DIR / "countries.json"
    snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")

    manifest = {
        "fetched_at": fetch_meta["fetched_at"],
        "base_url": fetch_meta["base_url"],
        "indicators": names,
        "raw_sha256": {p.name: sha256(p) for p in sorted(RAW_DIR.glob("*.json")) if p.name != "_fetch.json"},
        "snapshot_sha256": sha256(snap_path),
        "counts": {"economies": len(economies), "kept": len(kept), "excluded": len(excluded),
                   "aggregates_skipped": len(aggregates)},
        "birth_coverage": {k: round(v, 4) for k, v in coverage.items()},
        "license": "World Bank data: CC BY 4.0",
    }
    (SNAPSHOT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")

    lines = [
        f"[input ] 국가·지역 {len(countries)}건 (집계 그룹 {len(aggregates)}건은 건너뜀) → 경제권 {len(economies)}건",
        f"[output] {len(kept)}건 → data/snapshot/countries.json",
        f"[skip  ] {len(excluded)}건 (아래 목록)",
        f"[check ] {len(economies)} = {len(kept)} + {len(excluded)} → OK",
        f"[births] 합계 {total_births:,}명/년",
        "[cover ] 출생아 기준 통계가 있는 비율 — "
        + " · ".join(f"{k} {v:.1%}" for k, v in coverage.items()),
        f"[assume] 성비 없음 {sum(1 for r in kept if r['sex_ratio'] is None)}개국 → 1.05 가정",
        f"[assume] 생존을 성별 대신 전체 값으로 {sum(1 for r in kept for s in ('male', 'female') if r['survival'][s] and r['survival'][s]['assumed_from_total'])}건",
        "",
        "== 제외된 경제권 ==",
        *([f"  {iso3}  {name}  — {why}" for iso3, name, why in excluded] or ["  (없음)"]),
        "",
        "== 한국어 이름이 없어 영어로 둔 곳 ==",
        *([f"  {n}" for n in english_names] or ["  (없음)"]),
        "",
        "== 데이터 메모 ==",
        *([f"  {n}" for n in notes] or ["  (없음)"]),
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()
