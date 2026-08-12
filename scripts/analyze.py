"""运行完整分析流水线（S0 范围 -> S8 汇总），输出 data/processed/<app_id>/analysis/。

用法示例：
    python scripts/analyze.py 839285684 --goal "订阅转化与付费墙体验"
    python scripts/analyze.py 839285684 --no-llm
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_review_insights.analysis.pipeline import run_pipeline  # noqa: E402
from app_review_insights.config import llm_available, llm_settings, load_dotenv  # noqa: E402
from app_review_insights.llm import LLMClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="App Store 评论分析流水线")
    parser.add_argument("app_id", help="应用 id（对应 data/raw/<app_id>）")
    parser.add_argument("--goal", default="", help="分析目标/约束，例如：订阅转化、可用性、低分评论")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--embed-backend", default="auto", choices=["auto", "tfidf", "sentence-transformers"])
    parser.add_argument("--no-llm", action="store_true", help="跳过模型调用（确定性模式）")
    parser.add_argument("--force", action="store_true", help="忽略阶段缓存重新计算")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    llm = None
    if not args.no_llm:
        if llm_available():
            settings = llm_settings()
            llm = LLMClient(**settings)
            print(f"LLM: {settings['provider']} / {settings['model']}")
        else:
            print("[提示] 未配置 LLM_API_KEY，将以确定性模式运行；模型驱动步骤会被标注或跳过。", file=sys.stderr)

    result = run_pipeline(
        app_id=args.app_id,
        raw_dir=pathlib.Path(args.raw_dir) / args.app_id,
        out_dir=pathlib.Path(args.out_dir) / args.app_id,
        goal_text=args.goal,
        llm=llm,
        embed_backend=args.embed_backend,
        force=args.force,
    )
    for event in result["events"]:
        print(f"[{event['stage']}] {event['status']}: {event['detail']}")
    summary = result["summary"]
    print("\n结果摘要：")
    print(f"  评论 {summary['counts']['reviews']} | 主题 {summary['counts']['topics']} | "
          f"发现 {summary['counts']['findings']} | 需求 {summary['counts']['requirements']} | "
          f"测试 {summary['counts']['test_cases']}")
    print(f"  追溯校验：{summary['traceability']['passed_checks']}/{summary['traceability']['total_checks']} 通过")
    print(f"  模型驱动：{summary['model_driven']}")
    print(f"  交付物目录：{pathlib.Path(args.out_dir) / args.app_id / 'analysis'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
