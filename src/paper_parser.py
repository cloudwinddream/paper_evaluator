"""
论文解析模块
负责读取和解析Word文档，提取文本内容、结构信息等
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from docx import Document


@dataclass
class ParsedPaper:
    """解析后的论文数据结构"""
    filename: str                          # 文件名
    student_name: str = ""                 # 学生姓名（从文件名提取）
    student_id: str = ""                   # 学号（如果有）
    title: str = ""                        # 论文标题
    raw_text: str = ""                     # 原始文本
    sections: dict = field(default_factory=dict)  # 各部分内容
    word_count: int = 0                    # 字数
    paragraph_count: int = 0               # 段落数
    figure_count: int = 0                  # 图片数量
    table_count: int = 0                   # 表格数量
    reference_count: int = 0               # 参考文献数量
    has_abstract: bool = False             # 是否有摘要
    has_keywords: bool = False             # 是否有关键词
    has_references: bool = False           # 是否有参考文献


class PaperParser:
    """Word论文解析器"""

    # 常见章节标题模式
    SECTION_PATTERNS = {
        "abstract": [r"摘\s*要", r"Abstract"],
        "keywords": [r"关\s*键\s*词", r"Keywords"],
        "introduction": [r"引\s*言", r"绪\s*论", r"前\s*言", r"第\s*1\s*章", r"Chapter\s*1"],
        "body": [r"正\s*文", r"第\s*[2-9]\s*章", r"Chapter\s*[2-9]"],
        "conclusion": [r"结\s*论", r"总\s*结", r"结\s*语", r"Conclusion"],
        "references": [r"参\s*考\s*文\s*献", r"References", r"Bibliography"],
    }

    def __init__(self):
        self.papers: list[ParsedPaper] = []

    def parse_file(self, filepath: str | Path) -> ParsedPaper:
        """解析单个Word文件"""
        filepath = Path(filepath)
        doc = Document(filepath)

        paper = ParsedPaper(
            filename=filepath.name,
            student_name=self._extract_student_name(filepath.name),
        )

        # 提取纯文本
        paper.raw_text = self._extract_text(doc)

        # 统计字数（中文字符+英文单词）
        paper.word_count = self._count_words(paper.raw_text)

        # 段落数
        paper.paragraph_count = len(doc.paragraphs)

        # 图片数量
        paper.figure_count = self._count_figures(doc)

        # 表格数量
        paper.table_count = len(doc.tables)

        # 提取各部分内容
        paper.sections = self._extract_sections(doc)

        # 检查必要部分
        paper.has_abstract = bool(paper.sections.get("abstract"))
        paper.has_keywords = bool(paper.sections.get("keywords"))
        paper.has_references = bool(paper.sections.get("references"))

        # 统计参考文献数量
        paper.reference_count = self._count_references(paper.sections.get("references", ""))

        # 提取标题（通常是文档第一个有意义的段落）
        paper.title = self._extract_title(doc)

        return paper

    def parse_directory(self, directory: str | Path) -> list[ParsedPaper]:
        """解析目录下所有Word文件"""
        directory = Path(directory)
        self.papers = []

        for filepath in sorted(directory.glob("*.docx")):
            try:
                paper = self.parse_file(filepath)
                self.papers.append(paper)
                print(f"[解析成功] {filepath.name} - {paper.word_count}字")
            except Exception as e:
                print(f"[解析失败] {filepath.name}: {e}")

        return self.papers

    def _extract_text(self, doc: Document) -> str:
        """提取文档纯文本"""
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)

    def _count_words(self, text: str) -> int:
        """统计字数（中文字符数 + 英文单词数）"""
        # 中文字符数
        chinese_chars = len(re.findall(r"[一-鿿]", text))
        # 英文单词数
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        return chinese_chars + english_words

    def _count_figures(self, doc: Document) -> int:
        """统计图片数量"""
        image_count = 0
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_count += 1
        return image_count

    def _extract_sections(self, doc: Document) -> dict[str, str]:
        """提取各章节内容"""
        sections = {}
        current_section = "header"
        current_content = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 检查是否是章节标题
            matched_section = None
            for section_name, patterns in self.SECTION_PATTERNS.items():
                for pattern in patterns:
                    if re.match(pattern, text, re.IGNORECASE):
                        matched_section = section_name
                        break
                if matched_section:
                    break

            if matched_section:
                # 保存前一个章节的内容
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = matched_section
                current_content = []
            else:
                current_content.append(text)

        # 保存最后一个章节
        if current_content:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _count_references(self, references_text: str) -> int:
        """统计参考文献数量"""
        if not references_text:
            return 0
        # 通常参考文献以数字编号，如 [1] [2] ...
        matches = re.findall(r"\[\d+\]", references_text)
        if matches:
            return len(matches)
        # 如果没有编号，按行数估算
        lines = [l for l in references_text.split("\n") if l.strip()]
        return len(lines)

    def _extract_student_name(self, filename: str) -> str:
        """从文件名提取学生姓名"""
        # 假设文件名格式：学号_姓名.docx 或 姓名_学号.docx 或 姓名.docx
        name = Path(filename).stem
        # 移除常见的学号模式（纯数字）
        parts = re.split(r"[_\-\s]", name)
        for part in parts:
            if not part.isdigit() and len(part) >= 2:
                return part
        return name

    def _extract_title(self, doc: Document) -> str:
        """提取论文标题"""
        for para in doc.paragraphs:
            text = para.text.strip()
            if text and len(text) < 100:
                # 跳过"论文题目"等标签
                if re.match(r"论文题目|题目|Title", text, re.IGNORECASE):
                    continue
                return text
        return "未识别标题"

    @staticmethod
    def parse_requirements_doc(filepath: str | Path) -> str:
        """读取题目要求Word文档，返回纯文本"""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"题目要求文档不存在: {filepath}")
        doc = Document(filepath)
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)
