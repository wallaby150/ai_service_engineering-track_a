"""테스트용 작은 스냅샷. 실제 데이터가 바뀌어도 엔진 테스트는 흔들리지 않는다."""

from __future__ import annotations

import pytest

from core.engine import Engine
from core.stats import snapshot_from_dict

FAKE = {
    "sources": {"births": "test"},
    "countries": [
        {   # 출생아가 가장 많고 모든 통계가 있다
            "iso3": "AAA", "name_ko": "가나라", "births": 600,
            "sex_ratio": {"value": 1.0, "year": 2024},
            "survival": {
                "male": {"imr": 100.0, "u5mr": 150.0, "year": 2024},
                "female": {"imr": 50.0, "u5mr": 80.0, "year": 2024},
            },
            "economy": {"pct_below_3_00": 10.0, "pct_below_4_20": 30.0, "pct_below_8_30": 60.0, "year": 2022},
            "life_expectancy": {"male": 60.0, "female": 65.0, "year": 2024},
        },
        {   # 경제 통계가 없다 — 0이 아니라 None
            "iso3": "BBB", "name_ko": "나나라", "births": 300,
            "sex_ratio": {"value": 1.1, "year": 2024},
            "survival": {
                "male": {"imr": 5.0, "u5mr": 6.0, "year": 2024},
                "female": {"imr": 4.0, "u5mr": 5.0, "year": 2024},
            },
            "economy": None,
            "life_expectancy": {"male": 80.0, "female": 85.0, "year": 2024},
        },
        {   # 성비가 없다 — 1.05 가정
            "iso3": "CCC", "name_ko": "다나라", "births": 100,
            "sex_ratio": None,
            "survival": {
                "male": {"imr": 20.0, "u5mr": 30.0, "year": 2024},
                "female": {"imr": 20.0, "u5mr": 30.0, "year": 2024},
            },
            "economy": {"pct_below_3_00": 0.0, "pct_below_4_20": 0.0, "pct_below_8_30": 5.0, "year": 2021},
            "life_expectancy": {"male": None, "female": None, "year": None},
        },
    ],
}


@pytest.fixture
def snapshot():
    return snapshot_from_dict(FAKE)


@pytest.fixture
def engine(snapshot):
    return Engine(snapshot)
