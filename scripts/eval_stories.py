"""AI 서사(v0.5)를 템플릿 서사(v0.2)와 같은 인생 위에서 견준다.

숫자로 재는 것: 첫 원고 통과율, 템플릿으로 떨어진 비율, 근거 없는 숫자 건수, 비용, 지연.
사람이 읽는 것: 두 서사를 나란히 둔 reports/story_eval.md.

    python scripts/eval_stories.py --n 10      # 실제 모델을 부른다 (.env의 키 필요, 10건이면 약 $0.02)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.settings import build_story_narrator, load_dotenv, story_model  # noqa: E402
from core.engine import Engine  # noqa: E402
from core.narrator_scripted import ScriptedNarrator  # noqa: E402
from core.stats import load_snapshot  # noqa: E402

REPORT = ROOT / "reports" / "story_eval.md"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="평가할 인생 수")
    parser.add_argument("--seed", type=int, default=1000, help="첫 시드 (재현용)")
    parser.add_argument("--pause", type=float, default=8.0, help="인생 사이 쉬는 초 — 무료 티어의 분당 요청 한도(429)를 피한다")
    args = parser.parse_args()

    load_dotenv()
    engine = Engine(load_snapshot())
    template = ScriptedNarrator()
    narrator = build_story_narrator(engine.snapshot, template)
    if narrator is None:
        sys.exit("NARRATOR_MODEL과 제공자 키가 .env에 없다")

    rows, sections = [], []
    for i, seed in enumerate(range(args.seed, args.seed + args.n)):
        if i:
            time.sleep(args.pause)
        life = engine.sample(seed)
        start = time.perf_counter()
        report = narrator.story(life)
        seconds = time.perf_counter() - start
        n = report.narrative
        rows.append({
            "seed": seed,
            "who": f"{life.country.name_ko} · {life.value('sex')} · {life.value('survival')}",
            "narrator": n.narrator,
            "attempts": report.attempts,
            "dropped": sum(len(d) for d in report.dropped),
            "first_pass": report.attempts == 1 and n.narrator == "llm",
            "overlap": report.overlap[-1] if report.overlap else None,
            "new_evidence": len(report.new_evidence[-1]) if report.new_evidence else 0,
            "cost": report.cost_usd,
            "seconds": seconds,
            "note": n.note or "",
        })
        t = template.narrate(life)
        sections.append(
            f"### 시드 {seed} — {rows[-1]['who']}\n\n"
            f"**템플릿 서사 (화면에 늘 보임)**\n\n" + "\n\n".join(t.paragraphs) + "\n\n"
            f"**AI 해석{'' if n.narrator == 'llm' else ' — 만들지 못함'}** — {n.title}"
            f"{' · ' + n.note if n.note else ''}\n\n" + "\n\n".join(n.paragraphs) + "\n"
            + "".join(f"\n- 버린 문장({why}): {sentence}" for d in report.dropped for sentence, why in d)
            + ("\n" if any(report.dropped) else "")
        )
        print(f"[{seed}] {n.narrator:<8} 작성 {report.attempts}회 · 버린 문장 {rows[-1]['dropped']} · "
              f"${report.cost_usd:.4f} · {seconds:.1f}s")

    k = len(rows)
    llm_rows = [r for r in rows if r["narrator"] == "llm"]
    summary = [
        f"# 서사 평가 — {story_model()} · {k}건 (시드 {args.seed}~{args.seed + k - 1})",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| AI 서사로 나간 비율 | {len(llm_rows)}/{k} |",
        f"| 첫 원고에 검증 통과 | {sum(r['first_pass'] for r in rows)}/{k} |",
        f"| 템플릿으로 떨어진 건 | {k - len(llm_rows)} |",
        f"| 검사에 걸려 버린 문장 (전체 원고) | {sum(r['dropped'] for r in rows)} |",
        f"| 화면(템플릿) 글과 겹친 비율 (AI 해석, 평균) | "
        + (f"{sum(r['overlap'] for r in llm_rows) / len(llm_rows):.0%} |" if llm_rows else "— |"),
        f"| 화면에 없던 근거 (AI 해석, 평균 개수) | "
        + (f"{sum(r['new_evidence'] for r in llm_rows) / len(llm_rows):.1f} |" if llm_rows else "— |"),
        f"| 건당 평균 비용 | ${sum(r['cost'] for r in rows) / k:.4f} |",
        f"| 건당 평균 지연 | {sum(r['seconds'] for r in rows) / k:.1f}초 |",
        "",
        "AI는 템플릿을 다시 쓰지 않고 그 아래 '해석'을 덧붙인다. 코드가 세 가지를 검증한다:",
        "숫자는 근거 id로만 썼는가(직접 친 숫자·없는 id·쓰지 않는 말이 있는 문장은 버린다),",
        "남은 글이 화면 글과 35% 넘게 겹치지 않는가, 화면에 없는 근거를 둘 이상 썼는가.",
        "읽히는가·뜻이 맞는가는 아래 원문을 사람이 읽고 판정한다.",
        "",
        "## 나란히 읽기",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(summary) + "\n".join(sections), encoding="utf-8")
    print("\n".join(summary[:12]))
    print(f"→ {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
