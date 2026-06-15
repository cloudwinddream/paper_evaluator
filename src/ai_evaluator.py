"""
AI模型评审评分模块
调用OpenAI兼容API对论文进行智能评审
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.llm_client import LLMClient
from src.paper_parser import ParsedPaper

PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_prompt(name: str) -> str:
    """从 config/prompts/ 加载 prompt 模板文件，不存在则返回空字符串"""
    path = PROMPT_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@dataclass
class EvaluationResult:
    """评审结果"""
    student_name: str
    total_score: float = 0.0
    dimension_scores: dict = field(default_factory=dict)
    evaluation_basis: str = ""
    short_comment: str = ""
    core_problems: list = field(default_factory=list)
    raw_response: str = ""
    success: bool = True
    error_message: str = ""


class AIEvaluator:
    """AI论文评审器"""

    def __init__(self, llm_client: LLMClient, score_min: int = 0, score_max: int = 100,
                 temperature: float = 0.4):
        self.llm = llm_client
        self.score_min = score_min
        self.score_max = score_max
        self.temperature = temperature

    def evaluate(
        self,
        paper: ParsedPaper,
        requirements: str,
        evaluation_criteria: str,
        dimensions: list[dict],
        image_analysis: Optional[list] = None,
    ) -> EvaluationResult:
        """评审单篇论文"""
        result = EvaluationResult(student_name=paper.student_name)

        prompt = self._build_prompt(paper, requirements, evaluation_criteria, dimensions)

        try:
            paper_text = paper.raw_text
            max_chars = 15000
            if len(paper_text) > max_chars:
                paper_text = paper_text[:max_chars] + "\n...（论文内容过长，已截断）"

            # 附加元数据帮助识别伪造
            meta_info = f"\n\n【解析元数据】字数:{paper.word_count} | 段落:{paper.paragraph_count} | 图片:{paper.figure_count} | 表格:{paper.table_count}"
            if paper.figure_count == 0:
                meta_info += "\n【注意】该文档未检测到嵌入图片（可能为纯文本或PDF解析降级结果）"
            if image_analysis:
                aigc_images = [a for a in image_analysis if a.is_likely_aigc and a.aigc_confidence > 0.5]
                low_quality_images = [a for a in image_analysis if a.quality_issues]
                if aigc_images:
                    meta_info += f"\n【视觉分析】{len(aigc_images)}张图片疑似AIGC生成"
                if low_quality_images:
                    meta_info += f"\n【视觉分析】{len(low_quality_images)}张图片存在质量问题"

            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"请评审以下论文：\n\n{paper_text}{meta_info}"},
                ],
                temperature=self.temperature,
                max_tokens=4096,
            )
            result.raw_response = response

            parsed = self._parse_response(response, dimensions)
            result.total_score = parsed.get("total_score", 0)
            result.dimension_scores = parsed.get("dimension_scores", {})
            result.evaluation_basis = parsed.get("evaluation_basis", "")
            result.short_comment = parsed.get("short_comment", "")
            result.core_problems = parsed.get("core_problems", [])

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
        """构建评审prompt：从模板文件加载 + 填充变量"""
        template = _load_prompt("evaluation_system.md")
        if not template:
            template = _load_prompt("evaluation_system.txt")
        if not template:
            template = """你是一位严格的课程设计报告评审专家。请根据以下题目要求，评审学生的项目报告。

## 课程设计要求
{requirements}

## 参考评分维度
{dimensions}

## 评审要求
1. 严格对照题目要求进行评审
2. 所有维度的分数及综合总分必须在 **{score_min}分 ~ {score_max}分** 之间
3. 计算加权总分（四舍五入取整）
4. 提供详细的评分依据
5. 给出简短评语（20字以内），包含3-5个关键词
6. 对于课程设计报告，不要求参考文献，不因缺少文献扣分

## 输出格式（严格JSON格式）
```json
{{
    "dimension_scores": {{
        "维度1名称": 整数分数,
        "维度2名称": 整数分数
    }},
    "total_score": 整数综合总分,
    "evaluation_basis": "详细的评分依据...",
    "short_comment": "关键词1 关键词2 关键词3..."
}}
```

重要：所有分数必须在{score_min}到{score_max}之间，超出范围视为无效。请直接输出JSON。"""

        dim_desc = "\n".join(
            f"- {d['name']}（权重{d['weight']*100:.0f}%）：{d['description']}"
            for d in dimensions
        )

        safe_req = requirements.replace("{", "{{").replace("}", "}}")
        safe_dim = dim_desc.replace("{", "{{").replace("}", "}}")
        template = template.replace("{requirements}", safe_req, 1)
        template = template.replace("{dimensions}", safe_dim, 1)
        return template.format(
            score_min=str(self.score_min),
            score_max=str(self.score_max),
        )

    def _parse_response(self, response: str, dimensions: list[dict]) -> dict:
        """解析API响应"""
        json_str = response

        if "```" in response:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if match:
                json_str = match.group(1)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            json_str = json_str.strip().strip("`").strip()
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                return self._extract_from_text(response, dimensions)

        result = {
            "dimension_scores": {},
            "total_score": 0,
            "evaluation_basis": "",
            "short_comment": "",
            "core_problems": [],
        }

        dim_scores = data.get("dimension_scores", {})
        for dim in dimensions:
            dim_name = dim["name"]
            score = dim_scores.get(dim_name, 0)
            result["dimension_scores"][dim_name] = min(self.score_max, max(self.score_min, round(float(score))))

        if result["dimension_scores"]:
            total = sum(
                result["dimension_scores"].get(d["name"], 0) * d["weight"]
                for d in dimensions
            )
            result["total_score"] = min(self.score_max, max(self.score_min, round(total)))
        else:
            result["total_score"] = min(self.score_max, max(self.score_min, round(float(data.get("total_score", 0)))))

        result["evaluation_basis"] = data.get("evaluation_basis", "未提供评分依据")
        result["short_comment"] = data.get("short_comment", "无评语")

        raw_problems = data.get("core_problems", [])
        if isinstance(raw_problems, dict):
            # dict format: {"P0": [...], "P1": [...], "P2": [...]}
            flat = []
            for level in ("P0", "P1", "P2"):
                for item in raw_problems.get(level, []):
                    flat.append(f"[{level}]{item}")
            result["core_problems"] = flat
        elif isinstance(raw_problems, list):
            result["core_problems"] = raw_problems

        return result

    def _extract_from_text(self, text: str, dimensions: list[dict]) -> dict:
        """从非结构化文本中提取评分信息（备用方案）"""
        result = {
            "dimension_scores": {},
            "total_score": 0,
            "evaluation_basis": text[:500],
            "short_comment": "解析失败，请人工复核",
            "core_problems": [],
        }

        for dim in dimensions:
            pattern = rf"{dim['name']}[：:]\s*(\d+)"
            match = re.search(pattern, text)
            if match:
                result["dimension_scores"][dim["name"]] = min(self.score_max, max(self.score_min, round(float(match.group(1)))))

        total_match = re.search(r"总[分得分][：:]\s*(\d+)", text)
        if total_match:
            result["total_score"] = min(self.score_max, max(self.score_min, round(float(total_match.group(1)))))

        return result

    def evaluate_batch(
        self,
        papers: list[ParsedPaper],
        requirements: str,
        evaluation_criteria: str,
        dimensions: list[dict],
        delay: float = 60.0,
        image_analysis_map: Optional[dict[str, list]] = None,
    ) -> list[EvaluationResult]:
        """批量评审论文"""
        results = []
        total = len(papers)
        if image_analysis_map is None:
            image_analysis_map = {}

        for i, paper in enumerate(papers, 1):
            print(f"[AI评审] 正在评审 {i}/{total}: {paper.student_name}")

            analysis = image_analysis_map.get(paper.student_name, [])
            result = self.evaluate(paper, requirements, evaluation_criteria, dimensions, image_analysis=analysis)
            results.append(result)

            if result.success:
                print(f"  → 得分: {result.total_score}分")
            else:
                print(f"  → 评审失败: {result.error_message}")

            if i < total:
                time.sleep(delay)

        return results
