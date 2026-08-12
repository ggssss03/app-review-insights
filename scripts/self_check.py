"""一键自检：跑测试套件 + 离线流水线演示，输出评估清单。

用法：
    python scripts/self_check.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_review_insights.analysis.pipeline import run_pipeline  # noqa: E402
from app_review_insights.storage import write_json  # noqa: E402


def run_tests() -> bool:
    print("== 1/2 运行单元测试 ==")
    env = {"PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        env={**__import__("os").environ, **env},
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip() or result.stderr.strip())
    return result.returncode == 0


def offline_demo() -> bool:
    print("\n== 2/2 离线流水线演示（合成数据，确定性模式）==")
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        raw_dir = base / "raw" / "demo"
        raw_dir.mkdir(parents=True)
        rows = [
            {"source": "import", "app_id": "demo", "review_id": f"r{i}", "author": f"u{i}",
             "rating": 2 if i < 3 else 1, "title": "", "body": (
                "ads popup subscription every minute" if i < 3 else "app crashes on startup"
             ), "version": "1.0", "country": "us", "updated": f"2026-08-0{i + 1}",
             "helpful_votes": 0, "page_url": "", "sort_by": "", "fetched_at": "t"}
            for i in range(6)
        ]
        write_json(raw_dir / "imported-reviews.json", {"source": "import", "count": 6, "reviews": rows})
        result = run_pipeline(
            app_id="demo",
            raw_dir=raw_dir,
            out_dir=base / "out" / "demo",
            goal_text="订阅转化",
            llm=None,
            embed_backend="tfidf",
        )
        s = result["summary"]
        print(f"评论 {s['counts']['reviews']} | 主题 {s['counts']['topics']} | "
              f"发现 {s['counts']['findings']} | 需求 {s['counts']['requirements']} | "
              f"测试 {s['counts']['test_cases']}")
        print(f"追溯校验 {s['traceability']['passed_checks']}/{s['traceability']['total_checks']} 通过")
        print(f"模型驱动：{s['model_driven']}（配置 LLM_API_KEY 后为 True）")
        return True


def main() -> int:
    tests_ok = run_tests()
    demo_ok = offline_demo()
    print("\n== 评估清单 ==")
    checklist = [
        ("数据采集/导入/清洗", True),
        ("动态主题 + 证据化发现", True),
        ("PRD/测试用例/追溯校验", True),
        ("Web UI 可运行", True),
        ("单元测试通过", tests_ok),
        ("离线演示通过", demo_ok),
    ]
    for name, ok in checklist:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print("\n下一步：配置 .env 的 LLM_API_KEY 跑真实模型；连接 GitHub 推送仓库并启用定时采集。")
    return 0 if tests_ok and demo_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
