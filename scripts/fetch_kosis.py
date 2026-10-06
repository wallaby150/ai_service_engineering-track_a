"""KOSIS 원본을 data/raw/kosis/ 에 내려받는다 (한국 상세, v0.3).

인증키는 .env의 KOSIS_API_KEY (https://kosis.kr/openapi/ 에서 발급). 원본은 커밋하지 않는다.
요청 URL에 키가 들어가므로 URL을 로그나 파일에 남기지 않는다.

    python scripts/fetch_kosis.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.settings import load_dotenv  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "kosis"
URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 이름 → (통계표, 항목, 수록주기, 분류 파라미터, 설명). 정의는 docs/probability-model.md
TABLES = {
    "births": ("INH_1B81A01", "T2+T3+", "Y", {"objL1": "ALL"}, "인구동향조사 시도·성별 출생아 수"),
    "employment": ("DT_1ES3B01J", "T7+", "H", {"objL1": "ALL", "objL2": "ALL"}, "지역별고용조사 시도·성별 고용률(%)"),
    "occupation": (
        "DT_1PC2021", "T00+", "F", {"objL1": "ALL", "objL2": "ALL", "objL3": "ALL"},
        "인구총조사 시도·성·직업(대분류)별 취업인구(15세 이상)",
    ),
}


def fetch(tbl: str, itm: str, prd: str, objs: dict, key: str) -> list:
    params = {"method": "getList", "apiKey": key, "orgId": "101", "tblId": tbl, "itmId": itm,
              "format": "json", "jsonVD": "Y", "prdSe": prd, "newEstPrdCnt": "1", **objs}
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{URL}?{urllib.parse.urlencode(params)}", timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("err"):
                raise RuntimeError(f"KOSIS 오류 {data.get('err')}: {data.get('errMsg')}")
            return data
        except Exception as e:  # 키가 담긴 URL은 메시지에 싣지 않는다
            last = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{tbl} 받기 실패 ({last})")


def main() -> None:
    load_dotenv()
    key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not key:
        sys.exit(".env에 KOSIS_API_KEY가 없다 (https://kosis.kr/openapi/ 에서 발급)")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tables": {}}
    for name, (tbl, itm, prd, objs, desc) in TABLES.items():
        rows = fetch(tbl, itm, prd, objs, key)
        (RAW_DIR / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        periods = sorted({r.get("PRD_DE") for r in rows})
        meta["tables"][name] = {"tbl_id": tbl, "description": desc, "period": periods, "rows": len(rows)}
        print(f"[fetch] {name:<11} {tbl:<12} {len(rows):>5}행  기간 {periods}  ({desc})")
    (RAW_DIR / "_fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"[done ] {RAW_DIR.relative_to(ROOT)} · {meta['fetched_at']}")


if __name__ == "__main__":
    main()
