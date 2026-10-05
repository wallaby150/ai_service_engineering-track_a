"""키 없이 도는 서사 대역. 사실 목록(core/facts.py)을 정해진 문장에 끼워 넣는다.

v0.5의 LLM 서사가 무엇을 더 잘하는지 비교할 기준선이기도 하다.
"""

from __future__ import annotations

from typing import List, Optional

from core.engine import Life
from core.facts import facts_of
from core.narrator import Narrative

CHILD = {"남자": "남자아이", "여자": "여자아이"}
ADULT = {"남자": "남성", "여자": "여성"}


def _num(x: Optional[float], digits: int = 1) -> str:
    if x is None:
        return "?"
    text = f"{x:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _share_sentence(pct: float) -> str:
    if pct >= 1:
        return f"세계에서 태어나는 아이 100명 중 약 {_num(pct)}명이 이 나라에서 태어납니다"
    return f"세계에서 태어나는 아이 1,000명 중 약 {_num(pct * 10)}명이 이 나라에서 태어납니다"


class ScriptedNarrator:
    name = "scripted"

    def narrate(self, life: Life) -> Narrative:
        f = facts_of(life)
        used: List[str] = ["country", "sex", "country_share_pct", "births_per_year"]
        child = CHILD.get(str(f["sex"]), "아이")
        paragraphs = [
            f"{f['country']}에서 {child}로 태어났습니다. {_share_sentence(float(f['country_share_pct'] or 0))}"
            f"(한 해 약 {_num(f['births_per_year'], 0)}명)."
        ]

        outcome = life.value("survival")
        if outcome is None:
            paragraphs.append("이 나라의 영아·아동 사망 통계는 없어, 어린 시절의 생존은 알 수 없습니다.")
        elif outcome == "survived_5":
            used += ["survival", "u5mr_per_1000", "survivors_per_1000"]
            text = (
                f"이 나라에서 {child} 1,000명이 태어나면 {_num(f['u5mr_per_1000'])}명은 다섯 번째 생일을 맞지 못합니다. "
                f"당신은 다섯 살을 맞은 {_num(f['survivors_per_1000'])}명 가운데 한 명입니다."
            )
            if f["life_expectancy"] is not None:
                used.append("life_expectancy")
                text += f" 이 나라 {ADULT.get(str(f['sex']), '사람')}의 기대수명은 {_num(f['life_expectancy'])}세입니다."
            paragraphs.append(text)
        elif outcome == "infant_death":
            used += ["survival", "imr_per_1000"]
            paragraphs.append(
                f"이 나라에서 {child} 1,000명이 태어나면 {_num(f['imr_per_1000'])}명은 첫돌을 맞지 못합니다. "
                f"이 삶은 그 {_num(f['imr_per_1000'])}명 가운데 하나였습니다."
            )
        else:
            used += ["survival", "u5mr_per_1000"]
            paragraphs.append(
                f"이 나라에서 {child} 1,000명이 태어나면 {_num(f['u5mr_per_1000'])}명은 다섯 번째 생일을 맞지 못합니다. "
                "이 삶은 첫돌은 넘겼지만 다섯 살을 맞지 못한 아이들 가운데 하나였습니다."
            )

        if f["economy"] is None:
            paragraphs.append("이 나라의 가구 소비(빈곤율) 통계는 없어, 태어난 가정의 경제 수준은 알 수 없습니다.")
        else:
            used += ["economy", "economy_band_pct"]
            text = (
                f"태어난 가정의 소비 수준은 {f['economy']}입니다. "
                f"이 나라 사람 100명 중 약 {_num(f['economy_band_pct'])}명이 같은 구간에 있습니다."
            )
            if life.value("economy") == "below_3_00":
                text += " 하루 $3.00은 세계은행이 정한 극빈선입니다."
            paragraphs.append(text)

        closing = []
        if life.complete and f["joint_one_in"]:
            used.append("joint_one_in")
            closing.append(f"이 조합 그대로 태어날 확률은 약 {_num(f['joint_one_in'], 0)}분의 1입니다.")
        if outcome in ("infant_death", "child_death"):
            closing.append("통계 속 숫자 하나하나가 한 사람의 삶입니다.")
        if closing:
            paragraphs.append(" ".join(closing))

        return Narrative(
            title=f"{f['country']}의 {child}",
            paragraphs=tuple(paragraphs),
            facts_used=tuple(used),
            narrator=self.name,
        )
