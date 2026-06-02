"""
AI模型评审评分模块
调用OpenAI兼容API对论文进行智能评审
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from src.paper_parser import ParsedPaper


@dataclass
class EvaluationResult:
    """评审结果"""
    student_name: str
    total_score: float = 0.0           # 总分
    dimension_scores: dict = field(default_factory=dict)  # 各维度得分
    evaluation_basis: str = ""         # 评分依据
    short_comment: str = ""            # 简短评语（含关键词）
    raw_response: str = ""             # 原始API响应
    success: bool = True               # 是否成功
    error_message: str = ""            # 错误信息


class AIEvaluator:
    """AI论文评审器"""

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

    def evaluate(
        self,
        paper: ParsedPaper,
        requirements: str,
        evaluation_criteria: str,
        dimensions: list[dict],
    ) -> EvaluationResult:
        """评审单篇论文"""
        result = EvaluationResult(student_name=paper.student_name)

        # 构建评审prompt
        prompt = self._build_prompt(paper, requirements, evaluation_criteria, dimensions)

        try:
            # 调用API
            response = self._call_api(paper.raw_text, prompt)
            result.raw_response = response

            # 解析响应
            parsed = self._parse_response(response, dimensions)
            result.total_score = parsed.get("total_score", 0)
            result.dimension_scores = parsed.get("dimension_scores", {})
            result.evaluation_basis = parsed.get("evaluation_basis", "")
            result.short_comment = parsed.get("short_comment", "")

        except Exception as e:
            result.success = False
            result.error_message = str(e)

        return result

    def _build_prompt(
        self,
        paper: ParsedPaper,
        requirements: str,
        evaluation_criteria: str,
        dimensions: list[dict],
    ) -> str:
        """构建评审prompt"""
        dim_desc = "\n".join(
            f"- {d['name']}（权重{d['weight']*100:.0f}%）：{d['description']}"
            for d in dimensions
        )

        prompt = f"""你是一位严格的课程设计报告评审专家。请根据以下题目要求，评审学生的项目报告。

## 课程设计要求
{requirements}

## 参考评分维度
以下维度供参考，请根据课程设计的具体类型和要求，自行判断每个维度的实际考察重点，并在评分依据中说明：
{dim_desc}

## 评审要求
1. **严格对照题目要求**进行评审，根据课程设计的类型（管理系统、网站、算法、数据分析等）判断评审重点
2. 所有维度的分数及综合总分必须在 **60分 ~ 89分** 之间（60分及格，89分封顶），只输出整数
3. 计算加权总分（四舍五入取整），总分同样必须在60-89之间
4. 提供详细的评分依据，说明每个维度扣分或得分的原因，并引用学生报告中的具体内容
5. 给出简短评语（20字以内），包含3-5个关键词，指出主要优缺点
6. 如果学生报告中缺少题目要求的必要章节或内容，应在对应维度中扣分

## 评分参考标准
- 优秀（80-89）：完全满足题目要求，内容充实，逻辑清晰，有独立见解
- 良好（70-79）：基本满足题目要求，内容较完整，有少量不足
- 及格（60-69）：部分满足题目要求，但存在明显不足或缺失
- 不及格（<60）：不设置，所有分数必须在60-89之间

## 输出格式（严格JSON格式）
```json
{{
    "dimension_scores": {{
        "维度1名称": 整数分数,
        "维度2名称": 整数分数
    }},
    "total_score": 整数综合总分,
    "evaluation_basis": "详细的评分依据，包含对各维度得分原因的分析...",
    "short_comment": "关键词1 关键词2 关键词3..."
}}
```

重要：所有分数（含各维度分和总分）必须在60到89之间，超出范围视为无效。请直接输出JSON。"""

        return prompt

    def _call_api(self, paper_text: str, system_prompt: str) -> str:
        """调用OpenAI兼容API（含限流重试）"""
        url = f"{self.base_url}/chat/completions"

        # 截断过长的文本（避免超出token限制）
        max_chars = 15000
        if len(paper_text) > max_chars:
            paper_text = paper_text[:max_chars] + "\n...（论文内容过长，已截断）"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请评审以下论文：\n\n{paper_text}"},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        for attempt in range(5):
            response = requests.post(url, headers=self.headers, json=payload, timeout=120)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"  ⏳ 触发限流，等待 {retry_after} 秒后重试 ({attempt+1}/5)...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]

        raise Exception("API 限流重试次数耗尽")

    def _parse_response(self, response: str, dimensions: list[dict]) -> dict:
        """解析API响应"""
        # 尝试提取JSON
        json_str = response

        # 如果响应包含```json```标记，提取其中的内容
        if "```" in response:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if match:
                json_str = match.group(1)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 尝试修复常见的JSON问题
            json_str = json_str.strip().strip("`").strip()
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # 如果还是失败，尝试从文本中提取信息
                return self._extract_from_text(response, dimensions)

        # 标准化结果
        result = {
            "dimension_scores": {},
            "total_score": 0,
            "evaluation_basis": "",
            "short_comment": "",
        }

        # 提取各维度分数（取整，强制 60-89 范围）
        dim_scores = data.get("dimension_scores", {})
        for dim in dimensions:
            dim_name = dim["name"]
            score = dim_scores.get(dim_name, 0)
            result["dimension_scores"][dim_name] = min(89, max(60, round(float(score))))

        # 计算总分（取整，强制 60-89 范围）
        if result["dimension_scores"]:
            total = sum(
                result["dimension_scores"].get(d["name"], 0) * d["weight"]
                for d in dimensions
            )
            result["total_score"] = min(89, max(60, round(total)))
        else:
            result["total_score"] = min(89, max(60, round(float(data.get("total_score", 0)))))

        result["evaluation_basis"] = data.get("evaluation_basis", "未提供评分依据")
        result["short_comment"] = data.get("short_comment", "无评语")

        return result

    def _extract_from_text(self, text: str, dimensions: list[dict]) -> dict:
        """从非结构化文本中提取评分信息（备用方案）"""
        import re

        result = {
            "dimension_scores": {},
            "total_score": 0,
            "evaluation_basis": text[:500],
            "short_comment": "解析失败，请人工复核",
        }

        # 尝试提取分数（强制 60-89）
        for dim in dimensions:
            pattern = rf"{dim['name']}[：:]\s*(\d+)"
            match = re.search(pattern, text)
            if match:
                result["dimension_scores"][dim["name"]] = min(89, max(60, round(float(match.group(1)))))

        # 尝试提取总分（强制 60-89）
        total_match = re.search(r"总[分得分][：:]\s*(\d+)", text)
        if total_match:
            result["total_score"] = min(89, max(60, round(float(total_match.group(1)))))

        return result

    def evaluate_batch(
        self,
        papers: list[ParsedPaper],
        requirements: str,
        evaluation_criteria: str,
        dimensions: list[dict],
        delay: float = 60.0,
    ) -> list[EvaluationResult]:
        """批量评审论文"""
        results = []
        total = len(papers)

        for i, paper in enumerate(papers, 1):
            print(f"[AI评审] 正在评审 {i}/{total}: {paper.student_name}")

            result = self.evaluate(paper, requirements, evaluation_criteria, dimensions)
            results.append(result)

            if result.success:
                print(f"  → 得分: {result.total_score}分")
            else:
                print(f"  → 评审失败: {result.error_message}")

            # 避免API限流
            if i < total:
                time.sleep(delay)

        return results
