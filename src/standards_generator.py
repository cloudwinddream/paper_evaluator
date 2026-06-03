"""
智能评分标准生成模块
调用大模型分析题目要求，自动生成评分维度、完整性规则和章节要求
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.llm_client import LLMClient


@dataclass
class GeneratedStandards:
    dimensions: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)   # 每项含 name / patterns / weight
    min_word_count: int = 2000
    completeness_config: dict = field(default_factory=dict)  # 完整配置
    evaluation_criteria: str = ""
    raw_response: str = ""
    success: bool = True
    error_message: str = ""


class StandardsGenerator:
    """智能评分标准生成器"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate(self, requirements: str) -> GeneratedStandards:
        result = GeneratedStandards()
        prompt = self._build_analysis_prompt(requirements)

        try:
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": "你是一位资深的课程设计指导教师，擅长制定评分标准和完整性检测规则。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            result.raw_response = response
            parsed = self._parse_response(response)
            result.dimensions = parsed.get("dimensions", [])
            result.evaluation_criteria = parsed.get("evaluation_criteria", "")
            result.sections = parsed.get("completeness", {}).get("sections", [])
            result.min_word_count = (
                parsed.get("completeness", {})
                .get("word_count", {})
                .get("min", 2000)
            )
            result.completeness_config = parsed.get("completeness", {})
        except Exception as e:
            result.success = False
            result.error_message = str(e)

        return result

    def generate_and_save(
        self,
        requirements: str,
        output_path: str | Path = "config/requirements.yaml",
    ) -> GeneratedStandards:
        result = self.generate(requirements)

        if result.success and result.dimensions:
            data = {
                "evaluation_criteria": result.evaluation_criteria or "自动生成的评分标准",
                "dimensions": result.dimensions,
                "completeness": result.completeness_config,
            }
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            print(f"  ✓ 评分标准已保存至: {output_path}")

        return result

    def _build_analysis_prompt(self, requirements: str) -> str:
        return f"""你是一位资深的课程设计指导教师。请严格根据以下题目要求，制定一套完整的评审方案，包含评分标准和完整性检测规则。

## 题目要求
{requirements}

## 任务要求

### 第一部分：评分维度（4-6个）
每个维度必须包含：
- **name**: 维度名称（2-6字）
- **weight**: 权重（0-1小数，总和严格等于1）
- **description**: 详细评分说明（至少50字）

### 第二部分：完整性检测规则
根据题目要求，制定论文完整性检测规则：

#### 2.1 必要章节（sections）
列出报告中必须包含的章节，**每项**包含：
- **name**: 章节名称
- **patterns**: 检测该章节的正则表达式列表（中文模糊匹配），至少提供2个不同写法
- **weight**: 该章节分值（所有章节weight之和应等于 sections_weight）

#### 2.2 字数要求（word_count）
- **min**: 最低字数
- **weight**: 字数项分值

#### 2.3 参考文献（references）
- **min**: 最少参考文献数量（若题目未要求则为0）
- **weight**: 该项分值

#### 2.4 图表/截图（figures）
- **min**: 最少图片数量（若题目要求截图则为3，否则为0）
- **weight**: 该项分值

#### 2.5 格式（format）
- **min_paragraphs**: 最少段落数
- **max_long_line_ratio**: 超长行占比上限（0-1）
- **weight**: 该项分值

#### 2.6 总分配置
- **sections_weight**: 章节检查总分
- **word_count_weight**: 字数检查总分
- **references_weight**: 参考文献总分
- **figures_weight**: 图表检查总分
- **format_weight**: 格式检查总分
以上五项之和应为100。

## 输出格式（严格JSON，不要包含其他内容）
```json
{{{{
    "evaluation_criteria": "整体评分原则...",
    "dimensions": [
        {{{{"name": "功能完整性", "weight": 0.30, "description": "详细说明..."}}}}
    ],
    "completeness": {{{{
        "sections_weight": 40,
        "sections": [
            {{{{ "name": "项目概述", "patterns": ["项目概述|项目背景|项目简介", "第1[章节]"], "weight": 5 }}}}
        ],
        "word_count": {{{{ "min": 3000, "weight": 20 }}}},
        "references": {{{{ "min": 5, "weight": 10 }}}},
        "figures": {{{{ "min": 3, "weight": 15 }}}},
        "format": {{{{ "min_paragraphs": 10, "max_long_line_ratio": 0.3, "weight": 15 }}}}
    }}}}
}}}}
```

注意：
- 维度权重之和必须严格等于 1.0
- 完整性各检查项weight之和必须等于100
- sections内各章节weight之和等于 sections_weight
- 请直接输出JSON，不要包含其他内容"""

    def _parse_response(self, response: str) -> dict:
        json_str = response
        if "```" in response:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if match:
                json_str = match.group(1)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            json_str = json_str.strip().strip("`").strip()
            data = json.loads(json_str)

        # 处理评分维度
        raw_dims = data.get("dimensions", [])
        dimensions = []
        for d in raw_dims:
            if isinstance(d, str):
                dimensions.append({"name": d, "weight": 0.2, "description": d})
            elif isinstance(d, dict):
                dimensions.append(d)
        if dimensions:
            total_weight = sum(d.get("weight", 0) for d in dimensions)
            if abs(total_weight - 1.0) > 0.01:
                for d in dimensions:
                    d["weight"] = round(d["weight"] / total_weight, 2)
                dimensions[-1]["weight"] = round(
                    1.0 - sum(d["weight"] for d in dimensions[:-1]), 2
                )
        for d in dimensions:
            d["weight"] = max(0.05, min(0.50, d["weight"]))

        # 处理完整性规则（合并默认值）
        completeness = data.get("completeness", {})
        completeness.setdefault("sections_weight", 40)
        completeness.setdefault("word_count_weight", 20)
        completeness.setdefault("references_weight", 10)
        completeness.setdefault("figures_weight", 15)
        completeness.setdefault("format_weight", 15)

        sections = completeness.get("sections", [])
        if sections and isinstance(sections[0], str):
            # 将字符串列表转换为 dict 列表
            completeness["sections"] = [
                {"name": s, "patterns": [s], "weight": 0}
                for s in sections
            ]
            sections = completeness["sections"]
        if not sections:
            # 向后兼容：从旧版 sections 列表转换
            old_sections = data.get("sections", [])
            old_min_words = data.get("min_word_count", 2000)
            completeness["sections"] = [
                {"name": s, "patterns": [s], "weight": 0}
                for s in old_sections
            ]
            completeness.setdefault("word_count", {"min": old_min_words, "weight": 20})
        else:
            completeness.setdefault("word_count", {"min": 3000, "weight": 20})

        completeness.setdefault("references", {"min": 5, "weight": 10})
        completeness.setdefault("figures", {"min": 3, "weight": 15})
        completeness.setdefault("format", {"min_paragraphs": 10, "max_long_line_ratio": 0.3, "weight": 15})

        return {
            "dimensions": dimensions,
            "evaluation_criteria": data.get("evaluation_criteria", ""),
            "completeness": completeness,
        }
