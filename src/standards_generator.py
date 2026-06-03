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

PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@dataclass
class GeneratedStandards:
    dimensions: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    min_word_count: int = 2000
    completeness_config: dict = field(default_factory=dict)
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
            system_prompt = _load_prompt("standards_system.md")
            if not system_prompt:
                system_prompt = _load_prompt("standards_system.txt")
            if not system_prompt:
                system_prompt = "你是一位资深的课程设计指导教师，擅长制定评分标准和完整性检测规则。"

            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
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
        template = _load_prompt("standards_generation.md")
        if not template:
            template = _load_prompt("standards_generation.txt")
        if not template:
            template = """你是一位资深的课程设计指导教师。请严格根据以下题目要求，制定一套完整的评审方案。

## 题目要求
{requirements}

## 任务要求

### 第一部分：评分维度（4-6个）
每个维度必须包含：
- **name**: 维度名称（2-6字）
- **weight**: 权重（0-1小数，总和严格等于1）
- **description**: 详细评分说明（至少50字）

### 第二部分：完整性检测规则
#### 2.1 必要章节（sections）
列出报告中必须包含的章节，每项包含：
- **name**: 章节名称
- **patterns**: 检测该章节的正则表达式列表（中文模糊匹配），至少2个不同写法
- **weight**: 该章节分值

#### 2.2 字数要求（word_count）
- **min**: 最低字数（课设报告建议1500-2500字）
- **weight**: 字数项分值

#### 2.3 图表/截图（figures）
- **min**: 最少图片数量
- **weight**: 该项分值

#### 2.4 格式（format）
- **min_paragraphs**: 最少段落数
- **max_long_line_ratio**: 超长行占比上限（0-1）
- **weight**: 该项分值

#### 2.5 总分配置
- **sections_weight**: 章节检查总分
- **word_count_weight**: 字数检查总分
- **figures_weight**: 图表检查总分
- **format_weight**: 格式检查总分
以上四项之和应为100。

注意：课程设计报告不要求参考文献，不要包含 references 相关字段。"""

        safe_req = requirements.replace("{", "{{").replace("}", "}}")
        return template.replace("{requirements}", safe_req, 1).format()

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

        # 处理完整性规则
        completeness = data.get("completeness", {})
        completeness.setdefault("sections_weight", 40)
        completeness.setdefault("word_count_weight", 30)
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
            old_sections = data.get("sections", [])
            old_min_words = data.get("min_word_count", 2000)
            completeness["sections"] = [
                {"name": s, "patterns": [s], "weight": 0}
                for s in old_sections
            ]
            completeness.setdefault("word_count", {"min": old_min_words, "weight": 30})
        else:
            completeness.setdefault("word_count", {"min": 2000, "weight": 30})

        completeness.setdefault("figures", {"min": 3, "weight": 15})
        completeness.setdefault("format", {"min_paragraphs": 10, "max_long_line_ratio": 0.3, "weight": 15})

        return {
            "dimensions": dimensions,
            "evaluation_criteria": data.get("evaluation_criteria", ""),
            "completeness": completeness,
        }
