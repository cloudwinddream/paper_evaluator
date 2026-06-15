"""
论文完整性检测模块
从 requirements.yaml 加载动态规则进行检测
"""

import re
from dataclasses import dataclass, field

from src.paper_parser import ParsedPaper


@dataclass
class CompletenessResult:
    student_name: str
    is_complete: bool = True
    score: float = 100.0
    missing_sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    dimension_scores: dict = field(default_factory=dict)


class CompletenessChecker:
    """论文完整性检查器（规则由 AI 动态生成）"""

    def __init__(self, config: dict):
        self.sections = config.get("sections", [])
        self.word_count_cfg = config.get("word_count", {"min": 2000, "weight": 30})
        self.references_cfg = config.get("references", {"min": 0, "weight": 0})
        self.figures_cfg = config.get("figures", {"min": 3, "weight": 15})
        self.format_cfg = config.get("format", {"min_paragraphs": 10, "max_long_line_ratio": 0.3, "weight": 15})

        self.sections_weight = config.get("sections_weight", 40)
        self.word_count_weight = self.word_count_cfg.get("weight", 30)
        self.references_weight = self.references_cfg.get("weight", 0)
        self.figures_weight = self.figures_cfg.get("weight", 15)
        self.format_weight = self.format_cfg.get("weight", 15)

    def check(self, paper: ParsedPaper) -> CompletenessResult:
        result = CompletenessResult(student_name=paper.student_name)

        dim_scores = {}

        section_score, section_warnings = self._check_sections(paper, result)
        dim_scores["章节完整性"] = section_score

        word_score, word_warnings = self._check_word_count(paper)
        dim_scores["字数"] = word_score
        result.warnings.extend(word_warnings)

        ref_score, ref_warnings = self._check_references(paper)
        dim_scores["参考文献"] = ref_score
        result.warnings.extend(ref_warnings)

        figure_score, figure_warnings = self._check_figures(paper)
        dim_scores["图表"] = figure_score
        result.warnings.extend(figure_warnings)

        format_score, format_warnings = self._check_format(paper)
        dim_scores["格式"] = format_score
        result.warnings.extend(format_warnings)

        result.dimension_scores = dim_scores

        weights = {
            "章节完整性": self.sections_weight,
            "字数": self.word_count_weight,
            "参考文献": self.references_weight,
            "图表": self.figures_weight,
            "格式": self.format_weight,
        }
        total_weight = sum(weights.values()) or 100
        result.score = sum(dim_scores.get(k, 0) for k in dim_scores)
        result.score = result.score * 100 / total_weight
        # 缺章全局惩罚：每缺一章扣减最终分的 12%（上限扣 60%）
        if result.missing_sections:
            penalty = 1 - len(result.missing_sections) * 0.12
            result.score *= max(0.4, penalty)
        result.score = round(result.score, 1)
        result.is_complete = result.score >= 60 and len(result.missing_sections) <= 2

        result.details = {
            "字数": f"{paper.word_count}字（要求至少{self.word_count_cfg.get('min', 2000)}字）",
            "段落数": paper.paragraph_count,
            "图片/截图数": paper.figure_count,
            "表格数": paper.table_count,
        }

        return result

    def _check_sections(self, paper: ParsedPaper, result: CompletenessResult) -> tuple[float, list[str]]:
        text = paper.raw_text
        warnings = []

        if not self.sections:
            return 0, ["未配置章节检测规则"]

        total_weight = sum(sec.get("weight", 1) for sec in self.sections)
        score = float(self.sections_weight)

        for sec in self.sections:
            name = sec.get("name", "")
            patterns = sec.get("patterns", [name])
            found = False
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    found = True
                    break
            if not found:
                result.missing_sections.append(name)
                deduction = self.sections_weight * sec.get("weight", 1) / total_weight
                score -= deduction

        if result.missing_sections:
            warnings.append(f"缺少章节：{', '.join(result.missing_sections)}")

        return max(0, score), warnings

    def _check_word_count(self, paper: ParsedPaper) -> tuple[float, list[str]]:
        warnings = []
        min_words = self.word_count_cfg.get("min", 2000)
        if paper.word_count >= min_words:
            return float(self.word_count_weight), warnings

        ratio = paper.word_count / min_words
        score = self.word_count_weight * ratio

        if paper.word_count < min_words * 0.5:
            warnings.append(f"字数严重不足：仅{paper.word_count}字，要求至少{min_words}字")
        else:
            warnings.append(f"字数略少：{paper.word_count}字，建议达到{min_words}字")

        return score, warnings

    def _check_references(self, paper: ParsedPaper) -> tuple[float, list[str]]:
        warnings = []
        min_refs = self.references_cfg.get("min", 0)
        if min_refs == 0:
            return float(self.references_weight), warnings
        if paper.reference_count >= min_refs:
            return float(self.references_weight), warnings
        if paper.reference_count == 0:
            warnings.append("缺少参考文献")
            return 0, warnings
        score = self.references_weight * paper.reference_count / min_refs
        warnings.append(f"参考文献偏少（{paper.reference_count}篇，要求至少{min_refs}篇）")
        return score, warnings

    def _check_figures(self, paper: ParsedPaper) -> tuple[float, list[str]]:
        warnings = []
        min_figs = self.figures_cfg.get("min", 3)
        if min_figs == 0:
            return float(self.figures_weight), warnings
        if paper.figure_count >= min_figs:
            return float(self.figures_weight), warnings
        if paper.figure_count > 0:
            warnings.append(f"图片/截图数量偏少（{paper.figure_count}张），建议提供至少{min_figs}张演示截图")
            return self.figures_weight * paper.figure_count / min_figs, warnings
        warnings.append("缺少项目演示截图")
        return 0, warnings

    def _check_format(self, paper: ParsedPaper) -> tuple[float, list[str]]:
        score = float(self.format_weight)
        warnings = []

        min_paras = self.format_cfg.get("min_paragraphs", 10)
        if paper.paragraph_count < min_paras:
            warnings.append(f"段落数过少（{paper.paragraph_count}），可能存在格式问题")
            score -= self.format_weight * 0.4

        max_ratio = self.format_cfg.get("max_long_line_ratio", 0.3)
        if paper.raw_text:
            lines = paper.raw_text.split("\n")
            very_long = [l for l in lines if len(l) > 500]
            if very_long and len(very_long) / max(1, len(lines)) > max_ratio:
                warnings.append("存在大量超长段落，可能为复制粘贴内容")
                score -= self.format_weight * 0.4

        return max(0, score), warnings
