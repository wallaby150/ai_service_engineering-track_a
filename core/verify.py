"""서사에 나온 숫자가 근거(사실 목록·조회 결과)에 있는지 코드로 대조한다.

판정은 문장을 읽지 않고 숫자만 본다. 그래서 결정적이다(7주차 인용 검증과 같은 자리).
근거에 없는 숫자는 지어낸 것으로 본다. 반올림·만 단위 표기 정도는 허용한다.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Set

NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")

# 문장에 늘 나오는 숫자: '다섯 살'의 5, '1,000명당', '100명 중', 빈곤선 $3.00·$4.20·$8.30
CONSTANTS = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0, 1000.0, 4.2, 8.3}


def numbers_in(text: str) -> List[float]:
    return [float(m.replace(",", "")) for m in NUMBER.findall(text)]


def _walk(obj: object) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)


def allowed_numbers(*sources: object) -> Set[float]:
    """근거 값과, 사람이 쓰는 표기 변형(반올림, 만 단위, 1,000명 중 남은 수)."""
    allowed = set(CONSTANTS)
    for x in (v for s in sources for v in _walk(s)):
        for digits in (0, 1, 2):
            allowed.add(round(x, digits))
        if x < 1000:
            allowed.add(round(1000 - x, 1))  # "1,000명 중 997.5명"
        if x >= 10_000:
            allowed.update({round(x / 10_000), round(x / 10_000, 1)})  # "약 426만 명"
    return allowed


def unsupported_numbers(text: str, allowed: Set[float]) -> List[float]:
    return [n for n in numbers_in(text) if n not in allowed and round(n, 1) not in allowed]


def missing_required(text: str, required: Iterable[float]) -> List[float]:
    """반드시 들어가야 하는 숫자 중 본문에 없는 것. 반올림한 표기도 인정한다."""
    found = set(numbers_in(text))
    return [r for r in required if not ({r, round(r), round(r, 1)} & found)]
