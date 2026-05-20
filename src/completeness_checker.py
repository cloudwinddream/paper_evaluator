"""
论文完整性检测模块
检查论文是否包含必要部分，字数是否达标等
"""

import re
from dataclasses import dataclass, field

from src.paper_parser import ParsedPaper


@dataclass
class CompletenessResult:
    """完整性检测结果"""
    student_name: str
    is_complete: bool = True                    # 是否完整
    score: float = 100.0                        # 完整性得分
    missing_sections: list[str] = field(default_factory=list)  # 缺失部分
    warnings: list[str] = field(default_factory=list)          # 警告信息
    details: dict = field(default_factory=dict)                 # 详细检查项


class CompletenessChecker:
    """论文完整性检查器"""

    def __init__(self, config: dict):
        self.required_sections = config.get("required_sections", [])
        self.min_word_count = config.get("min_word_count", 3000)
        self.min_references = config.get("min_references", 5)
        self.require_figures = config.get("require_figures", False)

    def check(self, paper: ParsedPaper) -> CompletenessResult:
        """检查论文完整性"""
        result = CompletenessResult(student_name=paper.student_name)
        deductions = []

        # 1. 检查必要章节（40分）
        section_score = self._check_sections(paper, result)
        if section_score < 40:
            deductions.append(40 - section_score)

        # 2. 检查字数（20分）
        word_count_score = self._check_word_count(paper, result)
        if word_count_score < 20:
            deductions.append(20 - word_count_score)

        # 3. 检查参考文献（10分）
        ref_score = self._check_references(paper, result)
        if ref_score < 10:
            deductions.append(10 - ref_score)

        # 4. 检查图表/截图（15分）
        if self.require_figures:
            figure_score = self._check_figures(paper, result)
            if figure_score < 15:
                deductions.append(15 - figure_score)

        # 5. 检查格式（15分）
        format_score = self._check_format(paper, result)

        # 计算总分
        total_deduction = sum(deductions)
        result.score = max(0, 100 - total_deduction)
        result.is_complete = result.score >= 60 and len(result.missing_sections) <= 2

        # 详细检查结果
        result.details = {
            "字数": f"{paper.word_count}字（要求至少{self.min_word_count}字）",
            "段落数": paper.paragraph_count,
            "图片/截图数": paper.figure_count,
            "表格数": paper.table_count,
        }

        return result

    def _check_sections(self, paper: ParsedPaper, result: CompletenessResult) -> float:
        """检查必要章节，返回得分（40分）"""
        text = paper.raw_text
        found_sections = []
        missing_sections = []

        # 用正则模糊匹配章节标题
        section_patterns = {
            "项目概述": [r"项?\s*目?\s*概?\s*述", r"第\s*1\s*[章节]"],
            "功能实现": [r"功\s*能\s*实?\s*现", r"第\s*2\s*[章节]", r"主\s*要\s*功\s*能"],
            "技术栈": [r"技\s*术\s*栈", r"第\s*3\s*[章节]", r"技\s*术?\s*选?\s*型?"],
            "项目结构": [r"项?\s*目?\s*结?\s*构", r"第\s*4\s*[章节]"],
            "代码实现": [r"代?\s*码?\s*实?\s*现", r"第\s*5\s*[章节]", r"核?\s*心?\s*代?\s*码"],
            "项目演示截图": [r"演?\s*示?\s*截?\s*图", r"界?\s*面?\s*展?\s*示", r"第\s*6\s*[章节]", r"运?\s*行?\s*结?\s*果"],
            "遇到的问题与解决方案": [r"遇?\s*到?\s*的?\s*问?\s*题", r"解?\s*决?\s*方?\s*案", r"第\s*7\s*[章节]"],
            "总结与展望": [r"总?\s*结", r"展?\s*望", r"结?\s*语", r"第\s*8\s*[章节]"],
        }

        for section_name, patterns in section_patterns.items():
            found = False
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found = True
                    break
            if found:
                found_sections.append(section_name)
            else:
                missing_sections.append(section_name)
                result.missing_sections.append(section_name)

        if missing_sections:
            result.warnings.append(f"缺少章节：{', '.join(missing_sections)}")

        # 每个章节5分，共8个章节40分
        score = len(found_sections) * 5
        return score

    def _check_word_count(self, paper: ParsedPaper, result: CompletenessResult) -> float:
        """检查字数（20分）"""
        if paper.word_count >= self.min_word_count:
            return 20.0

        ratio = paper.word_count / self.min_word_count
        score = 20 * ratio

        if paper.word_count < self.min_word_count * 0.5:
            result.warnings.append(
                f"字数严重不足：仅{paper.word_count}字，要求至少{self.min_word_count}字"
            )
        else:
            result.warnings.append(
                f"字数略少：{paper.word_count}字，建议达到{self.min_word_count}字"
            )

        return score

    def _check_references(self, paper: ParsedPaper, result: CompletenessResult) -> float:
        """检查参考文献（10分）"""
        if self.min_references == 0:
            return 10.0
        if paper.reference_count >= self.min_references:
            return 10.0
        if paper.reference_count == 0:
            return 0.0
        return 10 * paper.reference_count / self.min_references

    def _check_figures(self, paper: ParsedPaper, result: CompletenessResult) -> float:
        """检查图表/截图（15分）"""
        if paper.figure_count >= 3:
            return 15.0
        if paper.figure_count > 0:
            result.warnings.append(f"图片/截图数量偏少（{paper.figure_count}张），建议提供至少3张演示截图")
            return 15 * paper.figure_count / 3
        result.warnings.append("缺少项目演示截图")
        return 0.0

    def _check_format(self, paper: ParsedPaper, result: CompletenessResult) -> float:
        """检查格式（15分）"""
        score = 15.0

        if paper.paragraph_count < 10:
            result.warnings.append("段落数过少，可能存在格式问题")
            score -= 5

        if paper.raw_text:
            lines = paper.raw_text.split("\n")
            very_long_lines = [l for l in lines if len(l) > 500]
            if len(very_long_lines) > len(lines) * 0.3:
                result.warnings.append("存在大量超长段落，可能为复制粘贴内容")
                score -= 5

        return max(0, score)
