"""
测试 Phase 3+4: AIGC 检测图片分析集成 + 降级路径
验证项:
  1. image_analysis 含高置信 AIGC → image_issues 追加"疑似AIGC生成"
  2. image_analysis 全为非 AIGC → image_issues 不变
  3. image_analysis=None → 走启发式规则
  4. image_analysis=[] → 同上（降级）
  5. image_analysis_weight 影响概率计算
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aigc_detector import AIGCDetector, ParsedPaper
from src.image_analyzer import ImageAnalysisResult


def _make_detector(image_analysis_weight: float = 0.25) -> AIGCDetector:
    return AIGCDetector(config={
        "threshold": 0.5,
        "image_analysis_weight": image_analysis_weight,
    })


def test_image_analysis_detects_aigc():
    """image_analysis 含 AIGC → 产生 image_issues"""
    print("=" * 60)
    print("[测试1] image_analysis 含 AIGC → 告警")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=3, word_count=3000)
    analysis = [
        ImageAnalysisResult(index=1, section="章节1", caption_context="图1", description="正常截图", relevance="高", has_caption=True, quality_issues=[], is_likely_aigc=False, aigc_confidence=0.05),
        ImageAnalysisResult(index=2, section="章节2", caption_context="图2", description="疑似 AI", relevance="中", has_caption=False, quality_issues=["模糊"], is_likely_aigc=True, aigc_confidence=0.85),
        ImageAnalysisResult(index=3, section="章节3", caption_context="图3", description="正常", relevance="高", has_caption=True, quality_issues=[], is_likely_aigc=False, aigc_confidence=0.0),
    ]

    result = _make_detector().detect(paper, image_analysis=analysis)
    aigc_issues = [i for i in result.image_issues if "疑似AIGC" in i]
    print(f"  image_issues: {result.image_issues}")
    assert len(aigc_issues) >= 1
    assert "图片#2" in aigc_issues[0]
    print(f"  ✓ ai_probability={result.ai_probability:.3f}")
    print(f"  ✅ 通过\n")


def test_image_analysis_no_aigc():
    """全非 AIGC → 不告警"""
    print("=" * 60)
    print("[测试2] 全非 AIGC → 不告警")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=5, word_count=4000)
    analysis = [
        ImageAnalysisResult(index=1, section="a", caption_context="a", description="架构图", relevance="高", has_caption=True, quality_issues=[], is_likely_aigc=False, aigc_confidence=0.02),
        ImageAnalysisResult(index=2, section="b", caption_context="b", description="代码", relevance="高", has_caption=True, quality_issues=["分辨率偏低"], is_likely_aigc=False, aigc_confidence=0.08),
    ]

    result = _make_detector().detect(paper, image_analysis=analysis)
    aigc_issues = [i for i in result.image_issues if "疑似AIGC" in i]
    assert len(aigc_issues) == 0
    print(f"  image_issues: {result.image_issues}")
    print(f"  ✅ 通过\n")


def test_downgrade_heuristic():
    """image_analysis=None → 启发式"""
    print("=" * 60)
    print("[测试3] image_analysis=None → 启发式")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=25, word_count=500)
    result = _make_detector().detect(paper, image_analysis=None)
    hits = [i for i in result.image_issues if "图片数量异常多" in i or "文字内容少" in i]
    assert len(hits) >= 1
    print(f"  image_issues: {result.image_issues}")
    print(f"  ✅ 通过\n")


def test_downgrade_empty_list():
    """image_analysis=[] → 启发式"""
    print("=" * 60)
    print("[测试4] image_analysis=[] → 启发式")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=6, word_count=800)
    result = _make_detector().detect(paper, image_analysis=[])
    hits = [i for i in result.image_issues if "文字内容少" in i]
    assert len(hits) >= 1
    print(f"  image_issues: {result.image_issues}")
    print(f"  ✅ 通过\n")


def test_image_analysis_weight():
    """image_analysis_weight 生效"""
    print("=" * 60)
    print("[测试5] image_analysis_weight 配置生效")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=3, word_count=3000)
    analysis = [
        ImageAnalysisResult(index=i, section=f"节{i}", caption_context=f"图{i}", description="", relevance="高", has_caption=False, quality_issues=[], is_likely_aigc=True, aigc_confidence=0.9)
        for i in range(1, 6)
    ]

    r_high = _make_detector(image_analysis_weight=0.5).detect(paper, image_analysis=analysis)
    r_low = _make_detector(image_analysis_weight=0.1).detect(paper, image_analysis=analysis)
    assert r_high.ai_probability > r_low.ai_probability
    print(f"  weight=0.5 → {r_high.ai_probability:.3f}")
    print(f"  weight=0.1 → {r_low.ai_probability:.3f}")
    print(f"  ✅ 通过\n")


def test_no_image_no_issues():
    """无图片 → 无 image_issues"""
    print("=" * 60)
    print("[测试6] 无图片 → 无 image_issues")
    print("=" * 60)

    paper = ParsedPaper(filename="test.docx", student_name="测试", figure_count=0, word_count=5000)
    result = _make_detector().detect(paper, image_analysis=None)
    assert len(result.image_issues) == 0
    print(f"  ✅ 通过\n")


if __name__ == "__main__":
    test_image_analysis_detects_aigc()
    test_image_analysis_no_aigc()
    test_downgrade_heuristic()
    test_downgrade_empty_list()
    test_image_analysis_weight()
    test_no_image_no_issues()
    print("=" * 60)
    print("所有 AIGC 集成测试通过 ✅")
    print("=" * 60)
