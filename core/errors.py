"""코어가 내는 예외. 코어는 HTTP를 모른다 — 몇 번 상태로 바꿀지는 문(api/)이 정한다."""

from __future__ import annotations

from typing import Iterable


class CoreError(Exception):
    """코어에서 난 모든 예외의 부모."""


class UnknownValue(CoreError):
    """허용되지 않는 값. 메시지에 무엇이 틀렸고 무엇이 되는지를 함께 싣는다."""

    def __init__(self, field: str, value: object, allowed: Iterable[str]) -> None:
        allowed = list(allowed)
        preview = ", ".join(allowed[:12]) + (" …" if len(allowed) > 12 else "")
        super().__init__(f"{field}={value!r} 는 지원하지 않는다. 가능한 값: {preview}")
        self.field = field
        self.value = value
        self.allowed = allowed
