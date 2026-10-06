from __future__ import annotations

from typing import List

from pydantic import BaseModel

from ai.llm import _inline_refs
from ai.narrator_llm import Plan, Story


class Inner(BaseModel):
    title: str


class Outer(BaseModel):
    title: str
    items: List[Inner]


def test_field_named_title_survives_flattening():
    s = _inline_refs(Story.model_json_schema())
    assert set(s["required"]) <= set(s["properties"])  # Gemini가 거부했던 그 조건
    assert "title" in s["properties"]


def test_refs_are_inlined_and_metadata_dropped():
    s = _inline_refs(Outer.model_json_schema())
    assert "$defs" not in s and "title" not in s
    assert s["properties"]["items"]["items"]["properties"]["title"]["type"] == "string"
    p = _inline_refs(Plan.model_json_schema())
    assert "$ref" not in str(p)


def test_prompts_substitute_cleanly():
    from ai.narrator_llm import _load

    _load("planner.md").substitute(tools="t", facts="f")
    out = _load("solver.md").substitute(facts="f", evidence="e", feedback="")
    assert "$3.00" in out  # $$ 이스케이프가 달러 기호로 돌아온다
