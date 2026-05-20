"""
论文评审系统 - 主程序入口
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.paper_parser import PaperParser
from src.completeness_checker import CompletenessChecker
from src.ai_evaluator import AIEvaluator
from src.aigc_detector import AIGCDetector
from src.plagiarism_checker import PlagiarismChecker
from src.report_generator import ReportGenerator


def load_env():
    """加载 .env 文件并返回配置字典"""
    load_dotenv()
    return {
        "base_url": os.getenv("API_BASE_URL", ""),
        "api_key": os.getenv("API_KEY", ""),
        "model": os.getenv("API_MODEL", ""),
        "requirements_doc": os.getenv("REQUIREMENTS_DOC", ""),
        "output_dir": os.getenv("OUTPUT_DIR", "./outputs"),
        "papers_dir": os.getenv("PAPERS_DIR", ""),  # 论文文件夹路径
    }


def load_requirements_config(requirements_path: str) -> dict:
    """加载 requirements.yaml（评分标准）"""
    with open(requirements_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="论文评审系统")
    parser.add_argument(
        "--papers", "-p",
        default=None,
        help="学生论文文件夹路径（包含.docx文件），不填则使用 .env 中的 PAPERS_DIR"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/requirements.yaml",
        help="评分标准配置文件路径"
    )
    parser.add_argument(
        "--requirements-doc", "-r",
        default=None,
        help="题目要求Word文档路径（覆盖.env中的配置）"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录（覆盖.env中的配置）"
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="跳过AI评审（仅做格式检测和查重）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("论文评审系统 v1.0")
    print("=" * 60)

    # ── 1. 加载配置 ──
    print("\n[1/6] 加载配置...")
    env_config = load_env()
    req_config = load_requirements_config(args.config)

    # 论文文件夹路径：命令行参数 > .env
    papers_dir = args.papers or env_config["papers_dir"]
    if not papers_dir:
        print("  ✗ 未指定论文文件夹，请通过 --papers 参数或 .env 文件配置 PAPERS_DIR")
        sys.exit(1)

    # 题目要求文档路径：命令行参数 > .env
    requirements_doc_path = args.requirements_doc or env_config["requirements_doc"]
    if not requirements_doc_path:
        print("  ✗ 未指定题目要求文档，请通过 --requirements-doc 参数或 .env 文件配置 REQUIREMENTS_DOC")
        sys.exit(1)

    # 输出目录：命令行参数 > .env > 默认
    output_dir = args.output or env_config["output_dir"]

    # 读取题目要求Word文档
    print(f"  读取题目要求文档: {requirements_doc_path}")
    requirements_text = PaperParser.parse_requirements_doc(requirements_doc_path)
    print(f"  ✓ 题目要求已读取 ({len(requirements_text)}字符)")

    # 评分维度
    dimensions = req_config.get("dimensions", [])
    if not dimensions:
        print("  ✗ requirements.yaml 中未定义评分维度")
        sys.exit(1)
    print(f"  ✓ 评分维度: {', '.join(d['name'] for d in dimensions)}")

    # 输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ 输出目录: {output_path}")

    # ── 2. 解析论文 ──
    print("\n[2/6] 解析论文...")
    paper_parser = PaperParser()
    papers = paper_parser.parse_directory(papers_dir)

    if not papers:
        print("  ✗ 未找到任何Word文档，请检查路径")
        sys.exit(1)
    print(f"  ✓ 共解析 {len(papers)} 篇论文")

    # ── 3. 完整性检测 ──
    print("\n[3/6] 完整性检测...")
    # 根据报告要求调整必要章节
    completeness_config = {
        "required_sections": ["项目概述", "功能实现", "技术栈", "项目结构",
                              "代码实现", "项目演示截图", "遇到的问题与解决方案", "总结与展望"],
        "min_word_count": 2000,
        "min_references": 0,
        "require_figures": True,  # 项目报告通常需要截图
    }
    completeness_checker = CompletenessChecker(completeness_config)
    completeness_results = []
    for paper in papers:
        result = completeness_checker.check(paper)
        completeness_results.append(result)
        status = "✓" if result.is_complete else "⚠"
        print(f"  {status} {paper.student_name}: {result.score:.0f}分")

    # ── 4. AIGC检测 ──
    print("\n[4/6] AIGC检测...")
    aigc_detector = AIGCDetector({"threshold": 0.7, "ai_patterns": []})
    aigc_results = []
    for paper in papers:
        result = aigc_detector.detect(paper)
        aigc_results.append(result)
        icons = {"高风险": "🔴", "中风险": "🟡", "低风险": "🟢", "正常": "✅"}
        print(f"  {icons.get(result.overall_risk, '❓')} {paper.student_name}: "
              f"{result.overall_risk} (AI概率{result.ai_probability:.0%})")

    # ── 5. 查重检测 ──
    print("\n[5/6] 查重检测...")
    plagiarism_checker = PlagiarismChecker({
        "similarity_threshold": 0.3,
        "min_match_length": 20,
        "ngram_size": 5,
    })
    plagiarism_results = plagiarism_checker.check_all(papers)

    plag_summary = plagiarism_checker.get_plagiarism_summary(plagiarism_results)
    if plag_summary["suspected_plagiarism_count"] > 0:
        print(f"  ⚠ 发现 {plag_summary['suspected_plagiarism_count']} 对疑似抄袭:")
        for case in plag_summary["details"]:
            print(f"    - {case['student']} ↔ {case['similar_to']} ({case['similarity']:.0%})")
    else:
        print("  ✓ 未发现明显抄袭")

    # ── 6. AI评审 ──
    evaluation_results = []
    if not args.skip_ai:
        print("\n[6/6] AI评审（这可能需要一些时间）...")
        api_config = {
            "base_url": env_config["base_url"],
            "api_key": env_config["api_key"],
            "model": env_config["model"],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        if not api_config["base_url"] or not api_config["api_key"]:
            print("  ✗ 未配置API地址和密钥，请检查 .env 文件")
            sys.exit(1)

        ai_evaluator = AIEvaluator(api_config)
        evaluation_results = ai_evaluator.evaluate_batch(
            papers=papers,
            requirements=requirements_text,
            evaluation_criteria=req_config.get("evaluation_criteria", ""),
            dimensions=dimensions,
        )
        print("  ✓ AI评审完成")
    else:
        print("\n[6/6] 跳过AI评审")

    # ── 生成报告 ──
    print("\n" + "=" * 60)
    print("生成报告...")
    
    print("=" * 60)

    report_gen = ReportGenerator(output_dir)

    # Excel 汇总表（每个维度一列）
    excel_path = report_gen.generate_excel(
        papers=papers,
        completeness_results=completeness_results,
        evaluation_results=evaluation_results,
        aigc_results=aigc_results,
        plagiarism_results=plagiarism_results,
        dimensions=dimensions,
    )
    print(f"\n  📊 Excel汇总表: {excel_path}")

    # Word 详细报告
    word_path = report_gen.generate_word_report(
        papers=papers,
        completeness_results=completeness_results,
        evaluation_results=evaluation_results,
        aigc_results=aigc_results,
        plagiarism_results=plagiarism_results,
        requirements=requirements_text,
    )
    print(f"  📝 Word详细报告: {word_path}")

    # Markdown 报告（不含题目要求）
    md_path = report_gen.generate_markdown_report(
        papers=papers,
        completeness_results=completeness_results,
        evaluation_results=evaluation_results,
        aigc_results=aigc_results,
        plagiarism_results=plagiarism_results,
        dimensions=dimensions,
    )
    print(f"  📄 MD评审报告: {md_path}")

    print("\n" + "=" * 60)
    print("评审完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
