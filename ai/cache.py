"""버전 기준 캐시 (13주차: 키 = 데이터 · 프롬프트 · 모델).

시간(TTL)으로는 버리지 않는다. 통계를 다시 받거나 프롬프트·모델을 바꾸면 지문이 바뀌어 예전 값은 저절로 안 쓰인다.
AI 서사와 조건 해석이 같이 쓴다. 핸들러가 워커 스레드에서 돌아서 잠금을 건다.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Generic, Hashable, Optional, TypeVar

from core.stats import Snapshot

V = TypeVar("V")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def data_version(snapshot: Snapshot) -> str:
    """스냅샷 내용의 지문. 통계를 다시 만들면 바뀐다."""
    return digest(repr(snapshot))


class VersionedCache(Generic[V]):
    """가장 오래 안 쓴 것부터 버리는 크기 제한 캐시. 키에 버전을 넣는 것은 부르는 쪽의 일이다."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._items: "OrderedDict[Hashable, V]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Optional[V]:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: Hashable, value: V) -> None:
        if self.size <= 0:
            return
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
