"""data/raw/kosis/ → data/snapshot/korea.json + reports/prepare_korea_report.txt  (v0.3)

원칙은 prepare_data.py와 같다: 원 통계만 싣고 확률은 core/가 낸다, 없으면 None, 사유를 남긴다.
시도는 KOSIS 시도 코드 앞 두 자리로 맞춘다(11 서울 … 39 제주). 강원·전북은 표마다 옛 이름/새 이름이
섞여 있지만 코드는 같다.

    python scripts/prepare_korea.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "kosis"
OUT = ROOT / "data" / "snapshot" / "korea.json"
REPORT = ROOT / "reports" / "prepare_korea_report.txt"

SEX = {"T2": "male", "T3": "female", "S1": "male", "S2": "female", "1": "male", "2": "female"}
# 한국표준직업분류 대분류. A는 군인
OCCUPATIONS = {
    "01": "관리자", "02": "전문가 및 관련 종사자", "03": "사무 종사자", "04": "서비스 종사자",
    "05": "판매 종사자", "06": "농림어업 숙련 종사자", "07": "기능원 및 관련 기능 종사자",
    "08": "장치·기계 조작 및 조립 종사자", "09": "단순노무 종사자", "10": "군인",
}


def period_label(prd: str) -> str:
    """KOSIS 기간 코드 → 사람이 읽는 말. 202502(반기) → 2025년 하반기"""
    if len(prd) == 6:
        return f"{prd[:4]}년 {'상' if prd[4:] == '01' else '하'}반기"
    return f"{prd}년"


def rows(name: str) -> list:
    return json.loads((RAW / f"{name}.json").read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if not RAW.exists():
        sys.exit("data/raw/kosis 가 없다. 먼저 python scripts/fetch_kosis.py")
    fetch_meta = json.loads((RAW / "_fetch.json").read_text())
    notes = []

    # 시도 목록과 이름은 가장 최근 표(출생, 2025)를 기준으로 한다
    names: Dict[str, str] = {}
    births: Dict[str, Dict[str, int]] = {}
    for r in rows("births"):
        code = r["C1"]
        if len(code) == 2 and code != "00":
            names[code] = r["C1_NM"]
            births.setdefault(code, {})[SEX[r["ITM_ID"]]] = int(float(r["DT"]))

    employment: Dict[str, Dict[str, float]] = {}
    for r in rows("employment"):
        code, sex = r["C1"][:2], SEX.get(r["C2"])
        if code in names and sex and r.get("DT") not in (None, "", "-"):
            employment.setdefault(code, {})[sex] = float(r["DT"])

    occupation: Dict[str, Dict[str, Dict[str, int]]] = {}
    unknown_rows = 0
    for r in rows("occupation"):
        code, sex, occ = r["C1"], SEX.get(r["C2"]), r["C3"]
        if code not in names or sex is None:
            continue  # 전국·동부·읍부·면부, 성별 계는 쓰지 않는다
        if occ not in OCCUPATIONS:
            unknown_rows += occ not in ("00",)  # '계'는 합계라 버리고, 그 밖의 코드는 세어 둔다
            continue
        occupation.setdefault(code, {}).setdefault(sex, {})[occ] = int(float(r["DT"]))
    if unknown_rows:
        notes.append(f"직업 표에서 분류 밖 코드 {unknown_rows}행을 뺐다")

    regions = []
    for code in sorted(names):
        emp, occ = employment.get(code, {}), occupation.get(code, {})
        missing = [n for n, v in (("고용률", emp), ("직업", occ)) if len(v) < 2]
        if missing:
            notes.append(f"{code} {names[code]}: {'·'.join(missing)} 성별 값이 모자람 — 그 칸은 데이터 없음")
        regions.append({
            "code": code,
            "name": names[code],
            "births": births[code],
            "employment_rate_pct": {s: emp.get(s) for s in ("male", "female")},
            "occupations": {s: occ.get(s) for s in ("male", "female")},
        })

    total = sum(sum(r["births"].values()) for r in regions)
    nat = {s: sum(r["births"][s] for r in regions) for s in ("male", "female")}
    period = {k: [period_label(x) for x in v["period"]] for k, v in fetch_meta["tables"].items()}
    snapshot = {
        "sources": {
            "region": f"KOSIS 인구동향조사 시도·성별 출생아 수 ({period['births'][0]}) · INH_1B81A01",
            "employment": f"KOSIS 지역별고용조사 시도·성별 고용률 ({period['employment'][0]}) · DT_1ES3B01J",
            "occupation": f"KOSIS 인구총조사 시도·성·직업 대분류 취업인구 ({period['occupation'][0]}) · DT_1PC2021",
        },
        "years": {"births": period["births"][0], "employment": period["employment"][0],
                  "occupation": period["occupation"][0]},
        "occupation_labels": OCCUPATIONS,
        "regions": regions,
    }
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")

    manifest_path = OUT.with_name("MANIFEST.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["korea"] = {
        "fetched_at": fetch_meta["fetched_at"],
        "tables": fetch_meta["tables"],
        "raw_sha256": {p.name: sha256(p) for p in sorted(RAW.glob("*.json")) if p.name != "_fetch.json"},
        "snapshot_sha256": sha256(OUT),
        "license": "KOSIS 공공데이터 (출처 표시)",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")

    lines = [
        f"[input ] 시도 {len(names)}곳 (출생 {period['births'][0]} · 고용 {period['employment'][0]} · 직업 {period['occupation'][0]})",
        f"[births] 합계 {total:,}명 (남 {nat['male']:,} · 여 {nat['female']:,})",
        f"[check ] 시도 합 = 전국: " + ("OK" if total == sum(
            int(float(r['DT'])) for r in rows('births') if r['C1'] == '00') else "불일치"),
        f"[output] data/snapshot/korea.json · 시도 {len(regions)}곳 · 직업 대분류 {len(OCCUPATIONS)}개",
        "",
        "== 데이터 메모 ==",
        *([f"  {n}" for n in notes] or ["  (없음)"]),
        "",
    ]
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
