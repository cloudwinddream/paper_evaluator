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
from src.standards_generator import StandardsGenerator


def load_env():
    """加载 .env 文件并返回配置字典"""
    load_dotenv()
    return {
        "base_url": os.getenv("API_BASE_URL", ""),
        "api_key": os.getenv("API_KEY", ""),
        "model": os.getenv("API_MODEL", ""),
        "requirements_doc": os.getenv("REQUIREMENTS_DOC", ""),
        "output_dir": os.getenv("OUTPUT_DIR", "./outputs"),
        "papers_dir": os.getenv("PAPERS_DIR", ""),
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
    parser.add_argument(
        "--generate-standards", "-g",
        action="store_true",
        help="根据题目要求自动生成评分标准（保存到 requirements.yaml），然后退出"
    )
    parser.add_argument(
        "--force-standards",
        action="store_true",
        help="强制重新生成评分标准（覆盖已有配置）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("论文评审系统 v1.0")
    print("=" * 60)

    # ── 1. 加载配置 ──
    print("\n[1/6] 加载配置...")
    env_config = load_env()

    # 题目要求文档路径：命令行参数 > .env
    requirements_doc_path = args.requirements_doc or env_config["requirements_doc"]
    if not requirements_doc_path:
        print("  ✗ 未指定题目要求文档，请通过 --requirements-doc 参数或 .env 文件配置 REQUIREMENTS_DOC")
        sys.exit(1)

    # 读取题目要求Word文档
    print(f"  读取题目要求文档: {requirements_doc_path}")
    requirements_text = PaperParser.parse_requirements_doc(requirements_doc_path)
    print(f"  ✓ 题目要求已读取 ({len(requirements_text)}字符)")

    # ── 智能生成评分标准 ──
    api_config = {
        "base_url": env_config["base_url"],
        "api_key": env_config["api_key"],
        "model": env_config["model"],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    # 判断是否需要生成评分标准
    config_path = Path(args.config)
    need_generate = (
        args.generate_standards
        or args.force_standards
        or not config_path.exists()
    )

    if need_generate:
        if args.generate_standards and not args.force_standards and config_path.exists():
            # 仅生成模式：生成后退出
            print("\n[生成评分标准] 正在分析题目要求...")
            generator = StandardsGenerator(api_config)
            result = generator.generate_and_save(requirements_text, args.config)
            if result.success:
                print("\n  ✓ 评分标准生成完成！")
                print(f"  维度: {', '.join(d['name'] for d in result.dimensions)}")
                print(f"  章节: {', '.join(result.sections)}")
                print(f"  最少字数: {result.min_word_count}")
                print(f"\n  已保存至 {args.config}，请检查后重新运行评审。")
            else:
                print(f"\n  ✗ 生成失败: {result.error_message}")
            return

        # 强制重新生成或配置文件不存在
        if args.force_standards:
            print("\n[生成评分标准] 强制重新生成...")
        else:
            print("\n[生成评分标准] 未找到配置文件，自动生成...")

        generator = StandardsGenerator(api_config)
        result = generator.generate_and_save(requirements_text, args.config)
        if result.success:
            print("  ✓ 评分标准已生成")
            print(f"  维度: {', '.join(d['name'] for d in result.dimensions)}")
            for d in result.dimensions:
                print(f"    - {d['name']}（{d['weight']*100:.0f}%）：{d['description']}")
            print(f"  必要章节: {', '.join(result.sections)}")
            print(f"  最少字数: {result.min_word_count}")
        else:
            print(f"  ✗ 生成失败: {result.error_message}")
            print("  将使用默认评分标准...")
            args.config = None

    # ── 加载评分标准 ──
    if args.config and Path(args.config).exists():
        req_config = load_requirements_config(args.config)
    else:
        # 使用默认配置
        req_config = {
            "evaluation_criteria": "默认评分标准",
            "dimensions": [
                {"name": "内容质量", "weight": 0.30, "description": "内容深度和广度"},
                {"name": "技术能力", "weight": 0.25, "description": "技术选型和代码质量"},
                {"name": "文档规范", "weight": 0.20, "description": "报告结构和格式"},
                {"name": "创新性", "weight": 0.10, "description": "创新点"},
                {"name": "学术诚信", "weight": 0.15, "description": "原创性"},
            ],
        }

    dimensions = req_config.get("dimensions", [])
    if not dimensions:
        print("  ✗ 评分维度为空，请检查配置文件")
        sys.exit(1)
    print(f"  ✓ 评分维度: {', '.join(d['name'] for d in dimensions)}")

    # 从生成的配置中读取章节要求（如果有）
    generated_meta = req_config.get("_generated", {})
    auto_sections = generated_meta.get("sections", [])
    auto_min_word_count = generated_meta.get("min_word_count", 2000)

    # 论文文件夹路径：命令行参数 > .env
    papers_dir = args.papers or env_config["papers_dir"]
    if not papers_dir:
        print("  ✗ 未指定论文文件夹，请通过 --papers 参数或 .env 文件配置 PAPERS_DIR")
        sys.exit(1)

    # 输出目录：命令行参数 > .env > 默认
    output_dir = args.output or env_config["output_dir"]
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
    # 使用自动生成的章节要求，或默认章节
    default_sections = auto_sections or [
        "项目概述", "功能实现", "技术栈", "项目结构",
        "代码实现", "项目演示截图", "遇到的问题与解决方案", "总结与展望"
    ]
    completeness_config = {
        "required_sections": default_sections,
        "min_word_count": auto_min_word_count,
        "min_references": 0,
        "require_figures": True,
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
