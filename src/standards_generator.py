"""
智能评分标准生成模块
调用大模型分析题目要求，自动生成评分维度、权重和章节要求
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
import yaml


@dataclass
class GeneratedStandards:
    """大模型生成的评分标准"""
    dimensions: list[dict] = field(default_factory=list)   # 评分维度列表
    sections: list[str] = field(default_factory=list)       # 必要章节
    min_word_count: int = 2000                              # 最少字数
    evaluation_criteria: str = ""                           # 评分说明
    raw_response: str = ""                                  # 原始API响应
    success: bool = True
    error_message: str = ""


class StandardsGenerator:
    """智能评分标准生成器"""

    def __init__(self, api_config: dict):
        self.base_url = api_config["base_url"].rstrip("/")
        self.api_key = api_config["api_key"]
        self.model = api_config["model"]
        self.temperature = api_config.get("temperature", 0.3)
        self.max_tokens = api_config.get("max_tokens", 4096)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def generate(self, requirements: str) -> GeneratedStandards:
        """
        根据题目要求自动生成评分标准
        返回 GeneratedStandards，包含维度、章节、字数要求等
        """
        result = GeneratedStandards()

        prompt = self._build_analysis_prompt(requirements)

        try:
            response = self._call_api(prompt)
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
        """生成评分标准并保存到 yaml 文件"""
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
        """构建分析题目的 prompt"""
        return f"""你是一位资深的课程设计指导教师。请分析以下课程设计的题目要求，制定一套科学合理的评分标准。

## 题目要求
{requirements}

## 任务
请根据题目要求的内容和特点，完成以下工作：

1. **分析项目类型**：这是什么类型的项目（如管理系统、网站、算法设计等）
2. **制定评分维度**：设计 4-6 个评分维度，每个维度包含：
   - name: 维度名称（简洁，2-6字）
   - weight: 权重（0-1之间的小数，所有维度权重之和为1）
   - description: 维度说明（一句话，说明这个维度考察什么）
3. **确定必要章节**：列出学生报告中必须包含的章节/部分
4. **确定字数要求**：根据项目复杂度给出最低字数建议
5. **编写评分说明**：一段话说明整体评分原则

## 输出格式（严格JSON）
```json
{{
    "dimensions": [
        {{"name": "内容质量", "weight": 0.30, "description": "..."}},
        {{"name": "技术能力", "weight": 0.25, "description": "..."}}
    ],
    "sections": ["章节1", "章节2", "..."],
    "min_word_count": 3000,
    "evaluation_criteria": "整体评分说明..."
}}
```

注意：
- 所有维度权重之和必须等于 1.0
- 维度数量 4-6 个
- 章节名称简洁明了
- 请直接输出JSON，不要包含其他内容"""

    def _call_api(self, prompt: str) -> str:
        """调用 OpenAI 兼容 API"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位资深的课程设计指导教师，擅长制定评分标准。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        response = requests.post(url, headers=self.headers, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> dict:
        """解析 API 响应"""
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

        # 校验并修正权重
        dimensions = data.get("dimensions", [])
        if dimensions:
            total_weight = sum(d.get("weight", 0) for d in dimensions)
            # 如果权重和不等于1，按比例修正
            if abs(total_weight - 1.0) > 0.01:
                for d in dimensions:
                    d["weight"] = round(d["weight"] / total_weight, 2)
                # 修正最后一个维度的权重确保总和为1
                dimensions[-1]["weight"] = round(
                    1.0 - sum(d["weight"] for d in dimensions[:-1]), 2
                )

        # 校验分数范围
        for d in dimensions:
            d["weight"] = max(0.05, min(0.50, d["weight"]))

        return {
            "dimensions": dimensions,
            "sections": data.get("sections", []),
            "min_word_count": data.get("min_word_count", 2000),
            "evaluation_criteria": data.get("evaluation_criteria", ""),
        }
