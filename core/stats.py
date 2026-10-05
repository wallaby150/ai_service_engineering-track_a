"""스냅샷(data/snapshot/countries.json)을 읽어 불변 객체로 바꾼다.

여기서는 통계를 옮겨 담기만 한다. 확률은 core/model.py가 계산한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot" / "countries.json"


@dataclass(frozen=True)
class Survival:
    """출생아 1,000명당 영아(1세 전)·5세 미만 사망 수."""

    imr: float
    u5mr: float
    year: int
    assumed_from_total: bool = False


@dataclass(frozen=True)
class Economy:
    """1인당 하루 소비가 각 선(2021 PPP) 아래인 인구 비율(%). 누적 값이다."""

    pct_below_3_00: float
    pct_below_4_20: float
    pct_below_8_30: float
    year: int


@dataclass(frozen=True)
class Country:
    iso3: str
    name_ko: str
    name_en: str
    region: str
    income_level: str
    births: int
    sex_ratio: Optional[float]
    survival: Dict[str, Optional[Survival]]
    economy: Optional[Economy]
    life_expectancy: Dict[str, Optional[float]]
    years: Dict[str, Optional[int]]


@dataclass(frozen=True)
class Snapshot:
    countries: Tuple[Country, ...]
    sources: Dict[str, str]

    @property
    def total_births(self) -> int:
        return sum(c.births for c in self.countries)

    def get(self, iso3: str) -> Optional[Country]:
        for c in self.countries:
            if c.iso3 == iso3:
                return c
        return None


def _survival(raw: Optional[dict]) -> Optional[Survival]:
    if raw is None:
        return None
    return Survival(raw["imr"], raw["u5mr"], raw["year"], raw.get("assumed_from_total", False))


def _country(raw: dict) -> Country:
    eco = raw.get("economy")
    sr = raw.get("sex_ratio")
    le = raw.get("life_expectancy") or {}
    return Country(
        iso3=raw["iso3"],
        name_ko=raw["name_ko"],
        name_en=raw.get("name_en", raw["name_ko"]),
        region=raw.get("region", ""),
        income_level=raw.get("income_level", ""),
        births=int(raw["births"]),
        sex_ratio=sr["value"] if sr else None,
        survival={sex: _survival(raw["survival"].get(sex)) for sex in ("male", "female")},
        economy=Economy(eco["pct_below_3_00"], eco["pct_below_4_20"], eco["pct_below_8_30"], eco["year"])
        if eco
        else None,
        life_expectancy={"male": le.get("male"), "female": le.get("female")},
        years={
            "births": raw.get("births_basis", {}).get("cbr_year"),
            "sex_ratio": sr["year"] if sr else None,
            "life_expectancy": le.get("year"),
        },
    )


def snapshot_from_dict(data: dict) -> Snapshot:
    countries = tuple(_country(c) for c in data["countries"] if int(c["births"]) > 0)
    return Snapshot(countries=countries, sources=dict(data.get("sources", {})))


def load_snapshot(path: Optional[Path] = None) -> Snapshot:
    return snapshot_from_dict(json.loads((path or DEFAULT_SNAPSHOT).read_text(encoding="utf-8")))


def load_manifest(path: Optional[Path] = None) -> dict:
    """스냅샷을 언제, 어디서, 어떤 해시로 만들었는지. 없으면 빈 dict."""
    p = path or DEFAULT_SNAPSHOT.with_name("MANIFEST.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
