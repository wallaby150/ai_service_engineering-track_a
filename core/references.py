"""숫자는 참조로 (13주차 라이브 빌드 3: "그림은 선언으로, 숫자는 참조로").

해석가(LLM)는 숫자를 직접 쓰지 않는다. 코드가 근거마다 id와 '뜻'을 붙인 목록을 주고, 해석가는
"{R3}"처럼 가리키기만 한다. 값과 단위는 코드가 채운다. 그래서
- 지어낸 숫자가 들어올 자리가 없고,
- 숫자의 뜻(어느 나라의, 무엇의 값인지)이 목록에 붙어 있어 엉뚱한 뜻으로 쓰기 어렵다.

검사는 문장 하나 단위로 한다. 없는 참조, 직접 친 숫자, 금지어가 있는 문장만 버리고 나머지는 살린다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TOKEN = re.compile(r"\{(R\d+)\}")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
LITERAL_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# 참조 없이 써도 되는 숫자: '100명 중', '1,000명 중'의 기준 수와 빈곤선 표기($3.00 · $4.20 · $8.30)
FREE_NUMBERS = {100.0, 1000.0, 3.0, 4.2, 8.3}
# 숫자가 든 지표 이름 — 값이 아니라 말이다
TERMS = ("5세 미만",)
RANK_PREFIX = "높은 쪽에서 "
DEATH_FORBID = ("살아남", "생존")
FLIPPED = ("낮은 쪽에서", "아래에서", "뒤에서")
PEER_LABEL = re.compile(r"\s?\(S\d+\)")  # 목록에서 사람을 가리키는 표지 — 글에는 남기지 않는다
# 해석에 쓰지 않는 말: 훈계, 운·불운으로 평가하기, 가볍게 넘기기 (13주차 '훈계 금지어'의 이 서비스 판)
BANNED = ("아쉽게도", "안타깝게도", "다행히", "다행스럽게", "운이 좋", "운이 나쁘", "불행히", "축복", "감사해야",
          "해야 합니다", "하세요", "열심히")

METRIC_TEXT = {
    "u5mr": ("5세 미만 사망률(1,000명당, 남녀 평균)", "명", 1),
    "life_expectancy": ("기대수명(남녀 평균)", "세", 1),
    "poverty_3_00": ("하루 $3.00 미만 극빈 인구 비율", "%", 1),
}
# 세계 비교 값을 쓰는 문장에 있어야 하는 지표 이름(어느 하나)
METRIC_WORDS = {
    "u5mr": ("5세 미만", "다섯 살", "사망률"),
    "life_expectancy": ("기대수명", "수명"),
    "poverty_3_00": ("극빈", "빈곤", "$3.00"),
}
CHILD = {"남자": "남자아이", "여자": "여자아이"}
ADULT = {"남자": "남성", "여자": "여성"}


@dataclass(frozen=True)
class Ref:
    id: str
    meaning: str  # 이 값이 무엇인지 — 해석가는 이 뜻으로만 써야 한다
    value: float
    unit: str
    digits: int
    novel: bool  # 화면(템플릿)에 없는 근거인가 — 조회 결과와 세계 어딘가의 다른 사람들
    prefix: str = ""  # 값 앞에 코드가 늘 붙이는 말 — 순위의 방향("높은 쪽에서")을 해석가가 뒤집지 못하게
    suffix: str = ""  # 값 뒤에 늘 붙는 말 — 순위의 모집단("(196개국 중)")
    # 이 값을 쓰는 문장에 있어야 하는 말. 묶음마다 하나 이상(지표 이름, 나라 이름, '세계 평균') — 뜻 없이 숫자만 두지 않게
    mention: Tuple[Tuple[str, ...], ...] = ()
    forbid: Tuple[str, ...] = ()  # 이 값과 한 문장에 있으면 뜻이 뒤집히는 말(사망 수 옆의 '살아남')

    def text(self) -> str:
        """화면에 들어갈 표기. 천 단위 쉼표, 정해진 소수 자리, 단위까지."""
        v = round(self.value, self.digits)
        body = f"{v:,.{self.digits}f}" if self.digits else f"{int(round(v)):,}"
        if "." in body:
            body = body.rstrip("0").rstrip(".")
        return f"{self.prefix}{body}{self.unit}{self.suffix}"


@dataclass
class Rendered:
    paragraphs: List[str]
    used: List[str]  # 살아남은 문장이 쓴 참조 id
    dropped: List[Tuple[str, str]] = field(default_factory=list)  # (문장, 버린 이유)


class _Catalog:
    def __init__(self) -> None:
        self.refs: List[Ref] = []

    def add(self, meaning: str, value: object, unit: str, digits: int, novel: bool, prefix: str = "",
            suffix: str = "", mention: Tuple[Tuple[str, ...], ...] = ()) -> None:
        forbid = DEATH_FORBID if "숨지는" in meaning or "사망률" in meaning else ()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return  # 통계가 없는 값(None)은 목록에 올리지 않는다
        self.refs.append(Ref(f"R{len(self.refs) + 1}", meaning, float(value), unit, digits, novel, prefix, suffix, mention,
                             forbid))


def build_catalog(facts: Dict[str, object], lookups: Sequence[Tuple[str, Optional[str], Dict[str, object]]],
                  peers: Sequence[Dict[str, object]]) -> List[Ref]:
    """근거 목록. facts는 화면에 이미 있는 값(novel=False), lookups·peers는 화면에 없는 값(novel=True)."""
    cat = _Catalog()
    country, sex = str(facts.get("country", "")), str(facts.get("sex", ""))
    child, adult = CHILD.get(sex, "아이"), ADULT.get(sex, "사람")

    # 화면에 이미 있는 값 — 맥락용. 해석이 기대는 근거로는 세지 않는다
    cat.add(f"{country}에서 한 해 태어나는 아이 수", facts.get("births_per_year"), "명", 0, False)
    cat.add(f"세계 신생아 가운데 {country}에서 태어나는 비율", facts.get("country_share_pct"), "%", 2, False)
    cat.add(f"다시 태어나면 몇 번에 1번꼴로 {country}에서 태어나는지", facts.get("country_one_in"), "번", 0, False)
    cat.add(f"{country}에서 {child} 1,000명 중 첫돌 전에 숨지는 수", facts.get("imr_per_1000"), "명", 1, False)
    cat.add(f"{country}에서 {child} 1,000명 중 다섯 살 전에 숨지는 수", facts.get("u5mr_per_1000"), "명", 1, False)
    cat.add(f"{country} {adult}의 기대수명", facts.get("life_expectancy"), "세", 1, False)
    if facts.get("province"):
        cat.add(f"대한민국 {child} 가운데 {facts['province']}에서 태어나는 비율", facts.get("province_share_pct"), "%", 1, False)
        cat.add(f"{facts['province']}에 사는 {adult} 가운데 일하는 사람의 비율", facts.get("employment_rate_pct"), "%", 1, False)

    for tool, metric, result in lookups:
        if not isinstance(result, dict) or "error" in result:
            continue
        if tool == "country_profile":  # 태어난 나라 자체의 값. 다른 성별의 기대수명만 화면에 없다
            other = {"남자": ("female", "여성"), "여자": ("male", "남성")}.get(sex)
            if other:
                cat.add(f"{country}의 {other[1]} 기대수명", result.get(f"life_expectancy_{other[0]}"), "세", 1, True)
            cat.add(f"{country} 인구 가운데 하루 $3.00 미만으로 사는 비율", result.get("pct_below_3_00"), "%", 1, False)
            cat.add(f"{country} 인구 가운데 하루 $8.30 미만으로 사는 비율", result.get("pct_below_8_30"), "%", 1, False)
        elif tool == "world_comparison" and metric in METRIC_TEXT:
            name, unit, digits = METRIC_TEXT[metric]
            words = (METRIC_WORDS[metric],)
            cat.add(f"{country}의 {name}", result.get("country_value"), unit, digits, True, mention=words)
            cat.add(f"세계 평균 {name}(출생아 가중)", result.get("world_average"), unit, digits, True,
                    mention=words + (("세계 평균",),))
            ratio = result.get("ratio_to_world")
            if isinstance(ratio, (int, float)) and round(ratio, 1) > 0:  # 값이 0인 나라의 '0배'는 뜻이 없다
                cat.add(f"{country}의 {name}이 세계 평균의 몇 배인지", ratio, "배", 1, True, mention=words)
            n = result.get("countries_with_data")
            cat.add(f"{country}의 {name} 순위(값이 높은 쪽에서 센 자리, 방향과 나라 수까지 채워짐)",
                    result.get("rank_high_to_low"), "번째", 0, True, prefix=RANK_PREFIX,
                    suffix=f"({n:,}개국 중)" if isinstance(n, int) else "", mention=words)
        elif tool == "region_peers":
            for p in result.get("peers", []):  # type: ignore[union-attr]
                if p.get("country") == country:
                    continue
                who, at = f"이웃한 {p.get('country')}(나라 평균)", ((str(p.get("country")),),)
                cat.add(f"{who}의 5세 미만 사망률(1,000명당)", p.get("u5mr_per_1000"), "명", 1, True, mention=at)
                cat.add(f"{who}의 기대수명(남녀 평균)", p.get("life_expectancy"), "세", 1, True, mention=at)
                cat.add(f"{who}의 하루 $3.00 미만 극빈 인구 비율", p.get("pct_below_3_00"), "%", 1, True, mention=at)

    for i, p in enumerate(peers, 1):
        p_child = CHILD.get(str(p.get("sex")), "아이")
        who, at = f"세계 어딘가의 다른 사람 — {p.get('country')}에서 태어난 {p_child}(S{i})의 나라", ((str(p.get("country")),),)
        cat.add(f"{who}에서 {p_child} 1,000명 중 다섯 살 전에 숨지는 수", p.get("u5mr_per_1000"), "명", 1, True, mention=at)
        cat.add(f"{who}의 {ADULT.get(str(p.get('sex')), '사람')} 기대수명", p.get("life_expectancy"), "세", 1, True,
                mention=at)
    return cat.refs


def peer_lines(peers: Sequence[Dict[str, object]]) -> List[str]:
    """세계 어딘가의 다른 사람들의 뽑힌 값(글). 숫자가 아닌 사실이라 그대로 써도 된다."""
    keys = ("sex", "survival", "economy", "province", "occupation")
    return [f"S{i}: {p.get('country')} · " + " · ".join(str(p[k]) for k in keys if p.get(k)) for i, p in enumerate(peers, 1)]


def catalog_lines(refs: Iterable[Ref]) -> List[str]:
    return [f"{r.id} = {r.text()} — {r.meaning}{'' if r.novel else ' (화면에 이미 있음)'}" for r in refs]


def _sentences(paragraph: str) -> List[str]:
    return [s for s in SENTENCE_END.split(paragraph.strip()) if s.strip()]


def check_sentence(sentence: str, refs: Dict[str, Ref]) -> Optional[str]:
    """문장 하나를 검사한다. 문제가 있으면 이유, 없으면 None."""
    ids = TOKEN.findall(sentence)
    missing = [i for i in ids if i not in refs]
    if missing:
        return f"없는 참조 {', '.join(missing)}"
    bare = TOKEN.sub("", sentence)
    if "{" in bare or "}" in bare:
        return "깨진 참조"
    for term in TERMS:
        bare = bare.replace(term, "")
    typed = [float(m.replace(",", "")) for m in LITERAL_NUMBER.findall(bare)]
    typed = [n for n in typed if n not in FREE_NUMBERS]
    if typed:
        return "숫자를 직접 씀: " + ", ".join(f"{n:g}" for n in typed)
    for m in TOKEN.finditer(sentence):
        ref = refs[m.group(1)]
        if ref.prefix == RANK_PREFIX and any(sentence[:m.start()].rstrip().endswith(f) for f in FLIPPED):
            return "순위 방향을 바꿈"
        hit = next((w for w in ref.forbid if w in sentence), None)
        if hit:
            return f"뜻을 뒤집음: {ref.id}(사망 수)와 '{hit}'"
        lacking = next((g for g in ref.mention if not any(w in sentence for w in g)), None)
        if lacking:
            return f"뜻을 밝히지 않음: {ref.id}에 '{lacking[0]}' 같은 말이 없음"
    banned = [w for w in BANNED if w in sentence]
    if banned:
        return "쓰지 않는 말: " + ", ".join(banned)
    return None


# 받침 있는 말 뒤 / 없는 말 뒤. 해석가는 값을 모른 채 조사를 붙이므로 코드가 맞춘다
PARTICLES = (("이", "가"), ("은", "는"), ("을", "를"), ("과", "와"), ("으로", "로"))
PARTICLE_AFTER = re.compile(r"(으로|로|이|가|은|는|을|를|과|와)(?![가-힣])")
UNIT_READING = {"%": "퍼센트"}


def _has_batchim(text: str) -> bool:
    last = UNIT_READING.get(text[-1:], text[-1:])[-1:]
    if "가" <= last <= "힣":
        return (ord(last) - 0xAC00) % 28 != 0
    return last in "013678"  # 영·일·삼·육·칠·팔


def _particle(word: str, rest: str) -> str:
    m = PARTICLE_AFTER.match(rest)
    if not m:
        return rest
    pair = next(p for p in PARTICLES if m.group(1) in p)
    use = pair[0 if _has_batchim(word) else 1]
    if pair[1] == "로" and word[-1:] in "178":  # ㄹ 받침(일·칠·팔) 뒤에는 '로'
        use = "로"
    return use + rest[m.end():]


def _fill(sentence: str, by_id: Dict[str, Ref]) -> str:
    """참조를 '값+단위'로 채운다. 해석가가 단위를 한 번 더 붙였으면({R3}배) 겹친 단위를 지우고,
    바로 뒤의 조사는 채운 말의 받침에 맞춘다(6명가 → 6명이)."""
    out, pos = [], 0
    for m in TOKEN.finditer(sentence):
        ref = by_id[m.group(1)]
        before = sentence[pos:m.start()]
        if ref.prefix and before.endswith(ref.prefix):
            before = before[: -len(ref.prefix)]  # 해석가가 방향을 이미 썼으면 한 번만
        out.append(before)
        word = ref.text()
        pos = m.end()
        if ref.unit and sentence.startswith(ref.unit, pos):
            pos += len(ref.unit)
        nxt = TOKEN.search(sentence, pos)
        end = nxt.start() if nxt else len(sentence)
        out.append(word + _particle(word, sentence[pos:end]))
        pos = end
    out.append(sentence[pos:])
    return PEER_LABEL.sub("", "".join(out))


def render(paragraphs: Sequence[str], refs: Sequence[Ref]) -> Rendered:
    """참조를 값으로 채우고, 문제가 있는 문장만 버린다."""
    by_id = {r.id: r for r in refs}
    out = Rendered(paragraphs=[], used=[])
    for para in paragraphs:
        kept = []
        for sentence in _sentences(para):
            reason = check_sentence(sentence, by_id)
            if reason:
                out.dropped.append((sentence, reason))
                continue
            for rid in TOKEN.findall(sentence):
                if rid not in out.used:
                    out.used.append(rid)
            kept.append(_fill(sentence, by_id))
        if kept:
            out.paragraphs.append(" ".join(kept))
    return out


def novel_used(rendered: Rendered, refs: Sequence[Ref], peer_names: Iterable[str]) -> List[str]:
    """살아남은 글이 기댄 '화면에 없는 근거': 새 참조 id와, 이름으로 언급한 다른 사람들의 나라."""
    novel_ids = {r.id for r in refs if r.novel}
    text = " ".join(rendered.paragraphs)
    hits: List[str] = [rid for rid in rendered.used if rid in novel_ids]
    hits += sorted({n for n in peer_names if n and n in text})
    return hits
