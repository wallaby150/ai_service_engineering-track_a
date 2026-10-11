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
    out = _load("solver.md").substitute(screen="s", facts="f", evidence="e", peers="p", feedback="")
    assert "$" not in out.replace("$3.00", "")  # 남은 자리표시자가 없다(달러 기호는 $$로만 쓴다)
