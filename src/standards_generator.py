"""
智能评分标准生成模块
调用大模型分析题目要求，自动生成评分维度、权重和章节要求
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
    """大模型生成的评分标准"""
    dimensions: list[dict] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    min_word_count: int = 2000
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
                    {"role": "system", "content": "你是一位资深的课程设计指导教师，擅长制定评分标准。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            result.raw_response = response
            parsed = self._parse_response(response)
            result.dimensions = parsed.get("dimensions", [])
            result.sections = parsed.get("sections", [])
            result.min_word_count = parsed.get("min_word_count", 2000)
            result.evaluation_criteria = parsed.get("evaluation_criteria", "")
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
                "_generated": {
                    "sections": result.sections,
                    "min_word_count": result.min_word_count,
                },
            }
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            print(f"  ✓ 评分标准已保存至: {output_path}")

        return result

    def _build_analysis_prompt(self, requirements: str) -> str:
        return f"""你是一位资深的课程设计指导教师。请严格根据以下题目要求，制定一套完整、细化、可操作的评分标准。

## 题目要求
{requirements}

## 任务要求
请逐项完成以下工作：

### 1. 提取项目核心要求
- 明确这个项目的**项目类型**（管理系统 / 网站 / 算法设计 / 数据分析 / 其他）
- 列出题目中明确要求的**功能模块**和**技术点**
- 标注题目中提到的**格式要求**（字数、章节、参考文献等）

### 2. 制定评分维度（4-6个）
每个维度必须包含：
- **name**: 维度名称（简洁，2-6字）
- **weight**: 权重（0-1之间的小数，所有维度权重之和严格等于1）
- **description**: 详细的评分说明（至少50字），包含该维度下什么情况得高分、什么情况扣分

### 3. 规定报告章节
根据题目要求，列出学生报告中**必须包含的章节名称**（按顺序排列）

### 4. 字数要求
根据题目要求和项目复杂度给出合理的最低字数

### 5. 整体评分说明
一段话说明评分原则，包括：
- 总分计算方式
- 扣分规则
- 加分规则

## 输出格式（严格JSON）
```json
{{
    "project_type": "项目类型",
    "dimensions": [
        {{"name": "功能完整性", "weight": 0.30, "description": "详细说明..."}},
        {{"name": "技术实现", "weight": 0.25, "description": "..."}}
    ],
    "sections": ["项目概述", "需求分析", "..."],
    "min_word_count": 3000,
    "evaluation_criteria": "整体评分原则..."
}}
```

注意：
- 维度权重之和必须严格等于 1.0
- 维度数量 4-6 个
- description 每个至少50字
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

        dimensions = data.get("dimensions", [])
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

        return {
            "dimensions": dimensions,
            "sections": data.get("sections", []),
            "min_word_count": data.get("min_word_count", 2000),
            "evaluation_criteria": data.get("evaluation_criteria", ""),
        }
