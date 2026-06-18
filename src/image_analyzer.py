"""
图片分析模块 (ImageAnalyzer)
负责通过视觉多模态模型对论文中的图片进行批量分析，包括：
- 图片压缩（PIL，最长边 ≤ 1024px）
- 分批调用多模态 API（每批 ≤ 5 张）
- 结构化结果提取与错误降级
"""

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PIL 按需导入
# ---------------------------------------------------------------------------
try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    _PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# 输出数据结构
# ---------------------------------------------------------------------------
@dataclass
class ImageAnalysisResult:
    """单张图片的分析结果"""
    index: int                     # 图片编号（1-indexed，与 ImageData.index 一致）
    section: str                   # 所在章节名称（来自 ImageData.section）
    caption_context: str           # 上下文文本（来自 ImageData.caption_context）
    description: str               # 详细的视觉描述
    relevance: str                 # 与论文主题的相关性（"高"/"中"/"低"）
    has_caption: bool              # 是否有标题/标注
    quality_issues: list[str]      # 观察到的质量问题（模糊、文字不可读等）
    is_likely_aigc: bool           # 是否疑似 AI 生成
    aigc_confidence: float         # AIGC 置信度 0.0-1.0


# ---------------------------------------------------------------------------
# 默认兜底结果（解析失败/API 异常时使用）
# ---------------------------------------------------------------------------
def _default_result(index: int, section: str = "", caption_context: str = "") -> ImageAnalysisResult:
    return ImageAnalysisResult(
        index=index,
        section=section,
        caption_context=caption_context,
        description="",
        relevance="未知",
        has_caption=False,
        quality_issues=["分析失败"],
        is_likely_aigc=False,
        aigc_confidence=0.0,
    )


# ---------------------------------------------------------------------------
# 多模态分析 Prompt（中文）
# ---------------------------------------------------------------------------
ANALYSIS_PROMPT_TEMPLATE = """你是一位论文评审专家，负责分析论文中的图片。

以下是一次性提交的多张图片，每张图片的信息如下：
{image_info_list}

请严格按以下 JSON 格式输出，针对 **每张图片** 输出一个对象，外层是一个 JSON 数组：

```json
[
  {{
    "image_index": <图片序号>,
    "description": "<详细的视觉描述>",
    "relevance": "<高/中/低>",
    "has_caption": true/false,
    "quality_issues": ["<质量问题1>", "<质量问题2>"],
    "is_likely_aigc": true/false,
    "aigc_confidence": <0.0-1.0的小数>
  }}
]
```

字段说明：
- description：详细描述图片中的内容（图表类型、数据趋势、界面元素等）
- relevance：该图片与论文主题的相关性，用"高"/"中"/"低"表示
- has_caption：图片是否有图标题或标注文字
- quality_issues：图片质量问题列表，如模糊、分辨率低、文字不可读、过暗/过亮、有遮挡等，如果没有问题则填 []
- is_likely_aigc：是否看起来像 AI 生成的图片
- aigc_confidence：AI 生成的置信度，0.0 表示肯定不是，1.0 表示肯定是

请只输出 JSON 数组，不要包含其他说明文字。"""


def _build_image_info_section(batch: list) -> str:
    """构造图片信息列表文本，供 prompt 使用"""
    lines = []
    for img in batch:
        caption_preview = (img.caption_context[:120] + "...") if len(img.caption_context) > 120 else img.caption_context
        lines.append(
            f"  图片 #{img.index} — 所在章节：{img.section}，上下文：{caption_preview}"
        )
    return "\n".join(lines)


def _build_analysis_messages(batch: list) -> list[dict]:
    """构造多模态请求消息列表

    格式：(text + 多张 image_url)
        text 块包含所有图片的索引/章节/上下文信息
        image_url 块每张图片一个
    """
    image_info = _build_image_info_section(batch)

    content: list[dict] = [
        {"type": "text", "text": ANALYSIS_PROMPT_TEMPLATE.format(image_info_list=image_info)},
    ]

    for img in batch:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img.mime_type};base64,{img.base64_data}",
            },
        })

    return [{"role": "user", "content": content}]


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------
def _parse_batch_response(response_text: str, batch: list) -> list[ImageAnalysisResult]:
    """从 LLM 响应中解析 JSON 数组，返回 ImageAnalysisResult 列表"""
    # 尝试提取 ```json ... ``` 包裹的内容
    text = response_text.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    data = json.loads(text)

    # 确保是列表
    if not isinstance(data, list):
        data = [data]

    # 构建 index -> ImageData 的映射
    batch_map = {img.index: img for img in batch}

    results: list[ImageAnalysisResult] = []
    for item in data:
        idx = item.get("image_index", 0)
        img_data = batch_map.get(idx)
        section = img_data.section if img_data else ""
        caption = img_data.caption_context if img_data else ""

        results.append(ImageAnalysisResult(
            index=idx,
            section=section,
            caption_context=caption,
            description=item.get("description", ""),
            relevance=item.get("relevance", "未知"),
            has_caption=bool(item.get("has_caption", False)),
            quality_issues=item.get("quality_issues", []),
            is_likely_aigc=bool(item.get("is_likely_aigc", False)),
            aigc_confidence=float(item.get("aigc_confidence", 0.0)),
        ))

    return results


# ---------------------------------------------------------------------------
# ImageAnalyzer
# ---------------------------------------------------------------------------
class ImageAnalyzer:
    """论文图片分析器

    使用多模态大模型批量分析论文中的图片，自动压缩、分批调用、解析结果。
    """

    BATCH_SIZE = 5  # 每批最多 5 张图片
    MAX_WIDTH = 1024  # 压缩后最大宽度

    def __init__(self, vision_llm):
        """
        Args:
            vision_llm: LLMClient 实例，需配置为支持视觉的多模态模型
        """
        self._vision_llm = vision_llm

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def analyze_images(self, images: list) -> list[ImageAnalysisResult]:
        """分析所有图片

        按 ≤5 张分批，每批压缩后调用多模态 API，最后合并结果。
        永远不会抛出异常——异常时返回降级结果。

        Args:
            images: list[ImageData]，论文解析器提取的图片列表

        Returns:
            list[ImageAnalysisResult]，顺序与输入一致
        """
        if not images:
            return []

        # 先压缩所有图片
        compressed = []
        for img in images:
            try:
                compressed_data = self._compress_image(img.base64_data, img.mime_type)
                # 压缩后再次检查尺寸，过滤过小的图片
                if _PIL_AVAILABLE:
                    raw = base64.b64decode(compressed_data)
                    test_img = Image.open(io.BytesIO(raw))
                    w, h = test_img.size
                    if w < 20 or h < 20:
                        logger.info("图片 #%d 尺寸过小 (%dx%d)，跳过分析", img.index, w, h)
                        continue
                # 创建一个轻量副本以便压缩后使用
                compressed.append(_ImageItem(
                    index=img.index,
                    section=img.section,
                    caption_context=img.caption_context,
                    mime_type=img.mime_type,
                    base64_data=compressed_data,
                ))
            except Exception:
                logger.warning("图片 #%d 压缩失败，使用原始数据", img.index)
                compressed.append(_ImageItem(
                    index=img.index,
                    section=img.section,
                    caption_context=img.caption_context,
                    mime_type=img.mime_type,
                    base64_data=img.base64_data,
                ))

        # 分批调用
        all_results: list[ImageAnalysisResult] = []
        for start in range(0, len(compressed), self.BATCH_SIZE):
            batch = compressed[start:start + self.BATCH_SIZE]
            batch_results = self._analyze_batch(batch)
            all_results.extend(batch_results)

        # 按 index 排序确保与输入顺序一致
        all_results.sort(key=lambda r: r.index)
        return all_results

    # ------------------------------------------------------------------
    # 图片压缩
    # ------------------------------------------------------------------
    def _compress_image(self, base64_data: str, mime_type: str) -> str:
        """压缩图片到最大宽度 1024px，保持宽高比

        - 使用 PIL 进行压缩
        - JPEG 用于照片类（image/jpeg），PNG 用于含透明通道的图片
        - 若 PIL 不可用，直接返回原始 base64 数据

        Args:
            base64_data: base64 编码的图片数据
            mime_type: MIME 类型（如 "image/png", "image/jpeg"）

        Returns:
            str: 压缩后的 base64 编码数据
        """
        if not _PIL_AVAILABLE:
            return base64_data

        raw_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(raw_bytes))

        # 转换为 RGB（去除透明通道，便于保存为 JPEG）
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")

        # 按最大宽度等比缩放
        original_width, original_height = img.size
        if original_width > self.MAX_WIDTH:
            scale = self.MAX_WIDTH / original_width
            new_width = self.MAX_WIDTH
            new_height = int(original_height * scale)
            img = img.resize((new_width, new_height), Image.LANCZOS)

        # 选择合适的输出格式
        is_png = mime_type == "image/png" or (img.mode == "RGBA" and mime_type != "image/jpeg")

        buf = io.BytesIO()
        if is_png:
            # RGBA → PNG
            img = img.convert("RGBA") if img.mode != "RGBA" else img
            img.save(buf, format="PNG", optimize=True)
        else:
            # 其他 → JPEG
            if img.mode == "RGBA":
                # PNG with transparency fallback to PNG anyway
                img = img.convert("RGBA")
                img.save(buf, format="PNG", optimize=True)
            else:
                rgb_img = img.convert("RGB") if img.mode != "RGB" else img
                rgb_img.save(buf, format="JPEG", quality=85, optimize=True)

        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ------------------------------------------------------------------
    # 批量分析
    # ------------------------------------------------------------------
    def _analyze_batch(self, batch: list) -> list[ImageAnalysisResult]:
        """分析一批图片（≤5 张）

        构造多模态消息，调用 vision_llm.chat()，解析 JSON 响应。
        若任一环节失败，为批次中所有图片返回默认降级结果。

        Args:
            batch: list[_ImageItem]，当前批次的图片数据

        Returns:
            list[ImageAnalysisResult]，与 batch 顺序一一对应
        """
        if not batch:
            return []

        try:
            messages = _build_analysis_messages(batch)
            response_text = self._vision_llm.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("图片分析 API 调用失败: %s", e)
            return [_default_result(
                index=img.index,
                section=img.section,
                caption_context=img.caption_context,
            ) for img in batch]

        # 解析 JSON
        try:
            results = _parse_batch_response(response_text, batch)
        except Exception as e:
            logger.error("图片分析响应解析失败: %s", e)
            return [_default_result(
                index=img.index,
                section=img.section,
                caption_context=img.caption_context,
            ) for img in batch]

        # 补齐缺失的图片（模型可能漏掉某些 index）
        batch_indices = {img.index for img in batch}
        result_indices = {r.index for r in results}
        missing = batch_indices - result_indices

        for idx in missing:
            img_data = next(img for img in batch if img.index == idx)
            results.append(_default_result(
                index=idx,
                section=img_data.section,
                caption_context=img_data.caption_context,
            ))

        # 按 index 排序返回
        results.sort(key=lambda r: r.index)
        return results


# ---------------------------------------------------------------------------
# 内部辅助数据类（压缩后的轻量图片载体）
# ---------------------------------------------------------------------------
class _ImageItem:
    """压缩后用于传输的轻量图片数据（避免修改外部 ImageData）"""

    __slots__ = ("index", "section", "caption_context", "mime_type", "base64_data")

    def __init__(
        self,
        index: int,
        section: str,
        caption_context: str,
        mime_type: str,
        base64_data: str,
    ):
        self.index = index
        self.section = section
        self.caption_context = caption_context
        self.mime_type = mime_type
        self.base64_data = base64_data
