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
            "violations": sum(len(v) for v in report.violations),
            "first_pass": report.attempts == 1 and n.narrator == "llm",
            "cost": report.cost_usd,
            "seconds": seconds,
            "note": n.note or "",
        })
        t = template.narrate(life)
        sections.append(
            f"### 시드 {seed} — {rows[-1]['who']}\n\n"
            f"**v0.2 템플릿**\n\n" + "\n\n".join(t.paragraphs) + "\n\n"
            f"**v0.5 {'AI' if n.narrator == 'llm' else '템플릿(폴백)'}** — {n.title}"
            f"{' · ' + n.note if n.note else ''}\n\n" + "\n\n".join(n.paragraphs) + "\n"
        )
        print(f"[{seed}] {n.narrator:<8} 작성 {report.attempts}회 · 위반 {rows[-1]['violations']} · "
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
        f"| 잡아낸 근거 없는·빠진 숫자 (전체 원고) | {sum(r['violations'] for r in rows)} |",
        f"| 건당 평균 비용 | ${sum(r['cost'] for r in rows) / k:.4f} |",
        f"| 건당 평균 지연 | {sum(r['seconds'] for r in rows) / k:.1f}초 |",
        "",
        "검증은 코드가 한다: 화면에 나간 AI 서사의 숫자는 전부 사실 목록·조회 결과에 있는 값이다.",
        "품질(읽히는가, 맥락을 더했는가)은 아래 나란히 놓인 원문을 사람이 읽고 판정한다.",
        "",
        "## 나란히 읽기",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(summary) + "\n".join(sections), encoding="utf-8")
    print("\n".join(summary[:11]))
    print(f"→ {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
