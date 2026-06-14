"""
测试 Phase 2+3: 图片分析管道验证
验证项:
  1. 图片压缩正确（PNG → ≤1024px）
  2. JSON 响应解析正确
  3. ImageAnalyzer 批量分析（mock LLM）
  4. 完整管道: parse → ImageAnalyzer with mock
  5. API 错误降级（返回默认结果）
  6. 分批逻辑（≤5 张/批）
"""
import sys
import base64
import io
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from src.image_analyzer import ImageAnalyzer, _parse_batch_response
from src.paper_parser import PaperParser, ImageData


def _make_test_png(width: int, height: int) -> str:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_compress_image():
    """测试图片压缩：2000px 宽 → ≤1024px 宽"""
    print("=" * 60)
    print("[测试1] 图片压缩")
    print("=" * 60)

    analyzer = ImageAnalyzer(vision_llm=None)
    png_b64 = _make_test_png(2000, 1000)
    compressed = analyzer._compress_image(png_b64, "image/png")
    raw = base64.b64decode(compressed)

    assert raw[:8] == b'\x89PNG\r\n\x1a\n', "压缩后非 PNG"
    compressed_img = Image.open(io.BytesIO(raw))
    w, h = compressed_img.size
    print(f"  原始: 2000×1000 → 压缩: {w}×{h}")

    assert w <= 1024, f"宽度 > 1024px: {w}"
    expected_h = int(1000 * (w / 2000))
    assert h == expected_h, f"宽高比不符: 期望 {expected_h}, 实际 {h}"
    print(f"  ✓ 宽高比保持 (2000:1000 → {w}:{h})")
    print(f"  ✅ 压缩测试通过\n")


def test_parse_batch_response():
    """测试 JSON 响应解析"""
    print("=" * 60)
    print("[测试2] JSON 响应解析")
    print("=" * 60)

    class MockImage:
        index = 1
        section = "测试章节"
        caption_context = "图1 测试图"

    batch = [MockImage()]

    canned = '''```json
[
  {
    "image_index": 1,
    "description": "HDFS文件系统界面截图",
    "relevance": "高",
    "has_caption": true,
    "quality_issues": ["分辨率偏低"],
    "is_likely_aigc": false,
    "aigc_confidence": 0.05
  }
]
```'''
    results = _parse_batch_response(canned, batch)
    assert len(results) == 1
    r = results[0]
    print(f"  index={r.index}, relevance={r.relevance}, has_caption={r.has_caption}, aigc_confidence={r.aigc_confidence}")

    assert r.index == 1
    assert r.relevance == "高"
    assert r.has_caption is True
    assert r.aigc_confidence == 0.05
    assert "HDFS" in r.description
    print(f"  ✅ JSON 解析测试通过\n")


def test_analyze_with_mock():
    """测试 ImageAnalyzer mock 分析"""
    print("=" * 60)
    print("[测试3] ImageAnalyzer mock 分析")
    print("=" * 60)

    class MockLLM:
        def chat(self, messages, **kwargs):
            return '''```json
[
  {"image_index": 1, "description": "架构图", "relevance": "高", "has_caption": true, "quality_issues": [], "is_likely_aigc": false, "aigc_confidence": 0.1},
  {"image_index": 2, "description": "数据图", "relevance": "中", "has_caption": false, "quality_issues": ["模糊"], "is_likely_aigc": true, "aigc_confidence": 0.8}
]
```'''
        called = True

    images = [
        ImageData(index=1, section="章节1", caption_context="图1", mime_type="image/png", base64_data=_make_test_png(100, 100)),
        ImageData(index=2, section="章节2", caption_context="图2", mime_type="image/png", base64_data=_make_test_png(200, 150)),
    ]

    analyzer = ImageAnalyzer(vision_llm=MockLLM())
    results = analyzer.analyze_images(images)

    assert len(results) == 2
    assert results[0].index == 1
    assert results[1].index == 2
    print(f"  结果: {len(results)} 张")
    for r in results:
        print(f"   #{r.index}: {r.description[:20]} is_aigc={r.is_likely_aigc} conf={r.aigc_confidence}")
    print(f"  ✅ mock 分析测试通过\n")


def test_batch_5_limit():
    """测试分批：6 张 → 2 批"""
    print("=" * 60)
    print("[测试4] 分批逻辑 (6 张 → 2 批)")
    print("=" * 60)

    call_count = [0]

    class MockLLM:
        def chat(self, messages, **kwargs):
            call_count[0] += 1
            text = messages[0]["content"][0]["text"]
            indices = [int(m) for m in re.findall(r"图片 #(\d+)", text)]
            items = [
                f'{{"image_index": {i}, "description": "图{i}", "relevance": "高", "has_caption": false, "quality_issues": [], "is_likely_aigc": false, "aigc_confidence": 0.0}}'
                for i in indices
            ]
            return f"```json\n[{','.join(items)}]\n```"

    images = [
        ImageData(index=i, section=f"章节{i}", caption_context=f"图{i}", mime_type="image/png", base64_data=_make_test_png(100, 100))
        for i in range(1, 7)
    ]

    analyzer = ImageAnalyzer(vision_llm=MockLLM())
    results = analyzer.analyze_images(images)

    assert len(results) == 6
    assert call_count[0] == 2, f"期望 2 次调用, 实际 {call_count[0]}"
    print(f"  结果: {len(results)} 张, API 调用: {call_count[0]} 次")
    print(f"  ✅ 分批测试通过\n")


def test_api_error_downgrade():
    """测试 API 错误降级"""
    print("=" * 60)
    print("[测试5] API 错误降级")
    print("=" * 60)

    class MockLLM:
        def chat(self, messages, **kwargs):
            raise Exception("API timeout")

    images = [
        ImageData(index=1, section="章节1", caption_context="图1", mime_type="image/png", base64_data=_make_test_png(100, 100)),
    ]

    analyzer = ImageAnalyzer(vision_llm=MockLLM())
    results = analyzer.analyze_images(images)

    assert len(results) == 1
    r = results[0]
    assert r.description == ""
    assert "分析失败" in r.quality_issues
    assert r.is_likely_aigc is False
    assert r.aigc_confidence == 0.0
    print(f"  降级结果: index={r.index}, quality_issues={r.quality_issues}")
    print(f"  ✅ 降级测试通过\n")


def test_full_pipeline_with_mock():
    """完整管道: parse → ImageAnalyzer (mock)"""
    print("=" * 60)
    print("[测试6] 完整管道: parse → ImageAnalyzer")
    print("=" * 60)

    parser = PaperParser()
    papers = parser.parse_directory("papers")

    target = None
    for p in papers:
        if "测试论文" in p.filename:
            target = p
            break
    assert target is not None
    assert len(target.images) == 5
    print(f"  解析: {len(target.images)} 张图片")

    class MockLLM:
        def chat(self, messages, **kwargs):
            text = messages[0]["content"][0]["text"]
            indices = [int(m) for m in re.findall(r"图片 #(\d+)", text)]
            items = [
                f'{{"image_index": {i}, "description": "论文第{i}张图", "relevance": "高", "has_caption": true, "quality_issues": [], "is_likely_aigc": false, "aigc_confidence": 0.0}}'
                for i in indices
            ]
            return f"```json\n[{','.join(items)}]\n```"

    analyzer = ImageAnalyzer(vision_llm=MockLLM())
    results = analyzer.analyze_images(target.images)

    assert len(results) == 5
    print(f"  分析: {len(results)} 张结果")
    for r in results:
        print(f"   #{r.index}: {r.description}")
    print(f"  ✅ 完整管道测试通过\n")


if __name__ == "__main__":
    test_compress_image()
    test_parse_batch_response()
    test_analyze_with_mock()
    test_batch_5_limit()
    test_api_error_downgrade()
    test_full_pipeline_with_mock()
    print("=" * 60)
    print("所有管道测试通过 ✅")
    print("=" * 60)
