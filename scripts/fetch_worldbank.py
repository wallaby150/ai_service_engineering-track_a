"""World Bank 원본을 data/raw/worldbank/ 에 내려받는다.

원본은 커밋하지 않는다(.gitignore). 대신 이 스크립트가 받는 방법을 기록한다.
API 키가 필요 없고, 지표마다 국가별 '가장 최근의 비어 있지 않은 값'(mrnev=1)을 받는다.

    python scripts/fetch_worldbank.py
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "worldbank"
BASE = "https://api.worldbank.org/v2"

# 지표 코드 → 이 프로젝트에서 쓰는 이름. 정의는 docs/probability-model.md
INDICATORS = {
    "SP.DYN.CBRT.IN": "crude_birth_rate",
    "SP.POP.TOTL": "population",
    "SP.POP.BRTH.MF": "sex_ratio_at_birth",
    "SP.DYN.IMRT.IN": "imr_total",
    "SP.DYN.IMRT.MA.IN": "imr_male",
    "SP.DYN.IMRT.FE.IN": "imr_female",
    "SH.DYN.MORT": "u5mr_total",
    "SH.DYN.MORT.MA": "u5mr_male",
    "SH.DYN.MORT.FE": "u5mr_female",
    "SP.DYN.LE00.MA.IN": "life_exp_male",
    "SP.DYN.LE00.FE.IN": "life_exp_female",
    "SI.POV.DDAY": "poverty_3_00",
    "SI.POV.LMIC": "poverty_4_20",
    "SI.POV.UMIC": "poverty_8_30",
}


def get_json(url: str, retries: int = 3) -> list:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except Exception as e:  # 네트워크 일시 장애는 잠깐 기다렸다 다시
            last_error = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"요청 실패: {url} ({last_error})")


def fetch_countries() -> list:
    data = get_json(f"{BASE}/country?format=json&per_page=400")
    return data[1]


def fetch_indicator(code: str) -> list:
    url = f"{BASE}/country/all/indicator/{code}?format=json&mrnev=1&per_page=1000"
    data = get_json(url)
    header, rows = data[0], data[1] or []
    if header.get("pages", 1) > 1:
        raise RuntimeError(f"{code}: 한 페이지에 다 오지 않았다 ({header})")
    return rows


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    countries = fetch_countries()
    (RAW_DIR / "countries.json").write_text(json.dumps(countries, ensure_ascii=False, indent=1))
    print(f"[fetch] countries        {len(countries):>4}건")

    for code, name in INDICATORS.items():
        rows = fetch_indicator(code)
        (RAW_DIR / f"{code}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"[fetch] {code:<18} {len(rows):>4}건  ({name})")

    meta = {"fetched_at": fetched_at, "base_url": BASE, "indicators": INDICATORS}
    (RAW_DIR / "_fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"[done ] {RAW_DIR.relative_to(ROOT)} · {fetched_at}")


if __name__ == "__main__":
    main()
