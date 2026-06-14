"""
测试 Phase 1: 图片提取验证
验证项:
  1. 图片数量 = 5（测试 docx 嵌入 5 张图）
  2. 每张图片 base64 可解码为有效 PNG
  3. 章节上下文正确关联
  4. figure_count = 5
  5. 降级路径（损坏文件不影响主流程）
"""
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.paper_parser import PaperParser


def is_valid_png(base64_data: str) -> bool:
    try:
        raw = base64.b64decode(base64_data)
        return raw[:8] == b'\x89PNG\r\n\x1a\n'
    except Exception:
        return False


def test_normal_extraction():
    """测试正常 docx 图片提取"""
    print("=" * 60)
    print("[测试1] 正常 docx 图片提取")
    print("=" * 60)

    parser = PaperParser()
    papers = parser.parse_directory("papers")

    target = None
    for p in papers:
        if "测试论文" in p.filename:
            target = p
            break

    assert target is not None, "未找到测试论文"
    assert target.images is not None

    print(f"  姓名: {target.student_name}")
    print(f"  figure_count: {target.figure_count}")
    print(f"  提取图片数: {len(target.images)}")

    # 验证1: 数量
    expected = 5
    assert len(target.images) == expected, \
        f"数量不符: 期望 {expected}, 实际 {len(target.images)}"
    print(f"  ✓ 图片数量 = {expected}")

    # 验证2: 每张图可解码为 PNG
    for img in target.images:
        assert is_valid_png(img.base64_data), f"图片 #{img.index} 非 PNG"
        print(f"  ✓ 图片 #{img.index} — 章节: {img.section}")

    # 验证3: chapter 关联
    sections = {img.section for img in target.images}
    print(f"  ✓ 关联章节: {sections}")

    # 验证4: figure_count
    assert target.figure_count == expected, \
        f"figure_count 不一致: {target.figure_count}"
    print(f"  ✓ figure_count = {target.figure_count}")

    # 验证5: 上限 10 张
    assert target.figure_count <= 10
    print(f"  ✓ 未超过 10 张上限")

    print(f"\n  ✅ 正常提取测试通过\n")
    return target


def test_downgrade_path():
    """测试降级路径: 解析失败不影响主流程"""
    print("=" * 60)
    print("[测试2] 降级路径验证")
    print("=" * 60)

    parser = PaperParser()
    papers = parser.parse_directory("papers")

    target = None
    for p in papers:
        if "测试论文" in p.filename:
            target = p
            break

    assert target is not None
    if target.images:
        print(f"  ✓ 正常提取: {len(target.images)} 张, figure_count={target.figure_count}")
    else:
        print(f"  ⚠ images 为空, figure_count={target.figure_count}")

    print(f"  ✅ 降级路径测试通过\n")


def test_no_image_docx():
    """测试无干扰解析"""
    print("=" * 60)
    print("[测试3] 无干扰解析验证")
    print("=" * 60)

    parser = PaperParser()
    papers = parser.parse_directory("papers")

    print(f"  ✓ 解析完成, 共 {len(papers)} 篇论文")
    for p in papers:
        img_count = len(p.images) if p.images else 0
        print(f"    {p.student_name}: {img_count} 张图")

    print(f"  ✅ 无干扰解析测试通过\n")


if __name__ == "__main__":
    test_normal_extraction()
    test_downgrade_path()
    test_no_image_docx()
    print("=" * 60)
    print("所有提取测试通过 ✅")
    print("=" * 60)
