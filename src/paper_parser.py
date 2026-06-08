"""
论文解析模块
负责读取和解析Word文档，提取文本内容、结构信息等
"""

import re
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from docx import Document


def _try_markitdown(filepath: Path) -> str | None:
    """通过 MarkItDown 提取文本（兜底方案，支持 .docx/.doc/.pdf）"""
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(filepath))
        text = result.text_content
        if text and text.strip():
            return text.strip()
        return None
    except ImportError:
        return None
    except Exception:
        return None


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """从 PDF 文件中提取文本"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        raise RuntimeError(f"无法解析PDF文件: {pdf_path.name}: {e}")


def _count_images_from_pdf(pdf_path: Path) -> int:
    """从 PDF 文件中提取图片数量（使用 pymupdf）"""
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(pdf_path))
        image_count = 0
        for page in doc:
            image_list = page.get_images(full=True)
            image_count += len(image_list)
        doc.close()
        return image_count
    except ImportError:
        return 0
    except Exception:
        return 0


def _try_via_word(doc_path: Path) -> Path | None:
    """策略1: 通过 Word COM 直接打开（含修复模式）"""
    import win32com.client
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(
            str(doc_path.absolute()), ReadOnly=True,
            AddToRecentFiles=False, OpenAndRepair=True, Format=0,
        )
        tmp_dir = Path(tempfile.mkdtemp())
        docx_path = tmp_dir / f"{doc_path.stem}.docx"
        doc.SaveAs(str(docx_path.absolute()), FileFormat=16)
        doc.Close()
        word.Quit()
        return docx_path
    except Exception:
        try: word.Quit()
        except: pass
        return None


def _try_via_word_shortpath(doc_path: Path) -> Path | None:
    """策略2: 复制到短路径后通过 Word 打开"""
    import win32com.client
    try:
        import shutil
        short_dir = Path(tempfile.mkdtemp())
        short_path = short_dir / "input.doc"
        shutil.copy2(doc_path, short_path)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(
            str(short_path.absolute()), ReadOnly=True,
            AddToRecentFiles=False, OpenAndRepair=True, Format=0,
        )
        tmp_dir = Path(tempfile.mkdtemp())
        docx_path = tmp_dir / f"{doc_path.stem}.docx"
        doc.SaveAs(str(docx_path.absolute()), FileFormat=16)
        doc.Close()
        word.Quit()
        shutil.rmtree(short_dir, ignore_errors=True)
        return docx_path
    except Exception:
        try: word.Quit()
        except: pass
        try: shutil.rmtree(short_dir, ignore_errors=True)
        except: pass
        return None


def _try_via_word_as_text(doc_path: Path) -> Path | None:
    """策略3: 通过 Word 以纯文本方式打开（绕过 XML 解析器）"""
    import win32com.client
    try:
        import shutil
        short_dir = Path(tempfile.mkdtemp())
        short_path = short_dir / "input.doc"
        shutil.copy2(doc_path, short_path)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(
            str(short_path.absolute()), ReadOnly=True,
            AddToRecentFiles=False, Format=7,  # 纯文本
        )
        tmp_dir = Path(tempfile.mkdtemp())
        docx_path = tmp_dir / f"{doc_path.stem}.docx"
        doc.SaveAs(str(docx_path.absolute()), FileFormat=16)
        doc.Close()
        word.Quit()
        shutil.rmtree(short_dir, ignore_errors=True)
        return docx_path
    except Exception:
        try: word.Quit()
        except: pass
        try: shutil.rmtree(short_dir, ignore_errors=True)
        except: pass
        return None


def _try_as_docx(doc_path: Path) -> Path | None:
    """策略3: 尝试直接当 .docx 解析（可能只是扩展名错误）"""
    try:
        import zipfile
        from docx import Document as DocxDocument
        if not zipfile.is_zipfile(doc_path):
            return None
        with zipfile.ZipFile(doc_path) as z:
            if "word/document.xml" not in z.namelist():
                return None
        tmp_dir = Path(tempfile.mkdtemp())
        docx_path = tmp_dir / f"{doc_path.stem}.docx"
        import shutil
        shutil.copy2(doc_path, docx_path)
        DocxDocument(docx_path)
        return docx_path
    except Exception:
        return None


def _try_extract_text_raw(doc_path: Path) -> Path | None:
    """策略4: 从二进制文件中暴力提取可读文本（最后手段）"""
    try:
        text_parts = []
        with open(doc_path, "rb") as f:
            data = f.read()

        # 尝试 UTF-16LE 解码（Word 内部编码）
        i = 0
        current = []
        while i < len(data) - 1:
            try:
                char = data[i:i+2].decode("utf-16-le")
                if char.isprintable() or char in "\n\r\t":
                    current.append(char)
                else:
                    if len("".join(current)) > 20:
                        text_parts.append("".join(current))
                    current = []
            except:
                if len("".join(current)) > 20:
                    text_parts.append("".join(current))
                current = []
                i += 1
                continue
            i += 2

        text = "\n".join(text_parts)
        if len(text) < 50:
            return None

        tmp_dir = Path(tempfile.mkdtemp())
        docx_path = tmp_dir / f"{doc_path.stem}.docx"

        from docx import Document
        doc = Document()
        for line in text.split("\n"):
            line = line.strip()
            if line:
                doc.add_paragraph(line)
        doc.save(docx_path)
        return docx_path
    except Exception:
        return None


def _convert_doc_to_docx(doc_path: Path) -> Path:
    """将 .doc 文件转换为临时的 .docx 文件（自动尝试多种修复策略）"""
    strategies = [
        ("Word 修复模式打开", _try_via_word),
        ("复制到短路径后重试", _try_via_word_shortpath),
        ("纯文本方式打开", _try_via_word_as_text),
        ("尝试作为 .docx 解析", _try_as_docx),
        ("暴力提取文本", _try_extract_text_raw),
    ]
    for name, func in strategies:
        result = func(doc_path)
        if result is not None:
            return result

    raise RuntimeError(f"无法解析文件: {doc_path.name}（所有修复策略均失败）")


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
        """解析单个文件（支持 .docx, .doc 和 .pdf）"""
        filepath = Path(filepath)
        suffix = filepath.suffix.lower()

        if suffix == ".pdf":
            return self._parse_pdf(filepath)

        is_doc = suffix == ".doc"
        temp_docx = None
        source_path = filepath

        if is_doc:
            temp_docx = _convert_doc_to_docx(filepath)
            source_path = temp_docx

        try:
            try:
                doc = Document(source_path)

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
            except Exception:
                raw_text = _try_markitdown(filepath)
                if raw_text:
                    return self._build_paper_from_text(filepath, raw_text)
                raise
        finally:
            if temp_docx and temp_docx.exists():
                temp_docx.unlink()
                try:
                    temp_docx.parent.rmdir()
                except OSError:
                    pass

    def _build_paper_from_text(self, filepath: Path, raw_text: str, figure_count: int = 0) -> ParsedPaper:
        """从纯文本构建 ParsedPaper（兜底降级用）"""
        lines = [l for l in raw_text.split("\n") if l.strip()]
        paper = ParsedPaper(
            filename=filepath.name,
            student_name=self._extract_student_name(filepath.name),
            raw_text=raw_text,
            word_count=self._count_words(raw_text),
            paragraph_count=len(lines),
            figure_count=figure_count,
        )
        paper.sections = self._extract_sections_from_text(raw_text)
        paper.has_abstract = bool(paper.sections.get("abstract"))
        paper.has_keywords = bool(paper.sections.get("keywords"))
        paper.has_references = bool(paper.sections.get("references"))
        paper.reference_count = self._count_references(paper.sections.get("references", ""))
        paper.title = self._extract_title_from_text(raw_text, lines)
        return paper

    def _parse_pdf(self, filepath: Path) -> ParsedPaper:
        """解析 PDF 文件（pypdf + pymupdf 图片计数，失败后降级到 MarkItDown）"""
        raw_text = None
        try:
            raw_text = _extract_text_from_pdf(filepath)
        except Exception:
            raw_text = _try_markitdown(filepath)
        if not raw_text:
            raise RuntimeError(f"无法解析PDF文件: {filepath.name}（pypdf + MarkItDown 均失败）")

        # 尝试用 pymupdf 统计图片数量
        figure_count = _count_images_from_pdf(filepath)
        return self._build_paper_from_text(filepath, raw_text, figure_count)

    def parse_directory(self, directory: str | Path) -> list[ParsedPaper]:
        """解析目录下所有支持的文件（.docx, .doc, .pdf）"""
        directory = Path(directory)
        self.papers = []

        docx_names = {f.stem for f in directory.glob("*.docx")}
        for filepath in sorted(directory.glob("*.docx")) + sorted(directory.glob("*.doc")) + sorted(directory.glob("*.pdf")):
            # 同名的 .doc 和 .docx 同时存在时，跳过 .doc 避免重复
            if filepath.suffix.lower() == ".doc" and filepath.stem in docx_names:
                continue
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

    def _extract_sections_from_text(self, text: str) -> dict[str, str]:
        """从纯文本中提取各章节内容"""
        sections = {}
        current_section = "header"
        current_content = []

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            matched_section = None
            for section_name, patterns in self.SECTION_PATTERNS.items():
                for pattern in patterns:
                    if re.match(pattern, line, re.IGNORECASE):
                        matched_section = section_name
                        break
                if matched_section:
                    break

            if matched_section:
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = matched_section
                current_content = []
            else:
                current_content.append(line)

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
        """从文件名提取学生标识
        格式1: 学部-专业-班级-学号-姓名  → 学号-姓名
        格式2: 学号_姓名                → 学号-姓名
        格式3: 姓名_题目                → 姓名
        格式4: 姓名                    → 姓名
        """
        name = Path(filename).stem
        parts = [p for p in re.split(r"[_\-\s]+", name) if p]

        # 找出所有数字段（学号）和非数字段
        digits = [(i, p) for i, p in enumerate(parts) if p.isdigit() and len(p) >= 6]
        names = [(i, p) for i, p in enumerate(parts) if not p.isdigit() and len(p) >= 2]

        if digits:
            # 有学号 → 取最后一个学号及它之后的第一个姓名
            sid_idx, sid = digits[-1]
            sname = parts[-1]  # 默认取最后一段
            for i, p in names:
                if i > sid_idx:
                    sname = p
                    break
            return f"{sid}-{sname}"

        # 无学号 → 取第一个非数字段作为姓名
        if names:
            return names[0][1]

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

    def _extract_title_from_text(self, text: str, lines: list[str] | None = None) -> str:
        """从纯文本中提取标题"""
        if lines is None:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            if len(line) < 100:
                if re.match(r"论文题目|题目|Title", line, re.IGNORECASE):
                    continue
                return line
        return "未识别标题"

    @staticmethod
    def parse_requirements_doc(filepath: str | Path) -> str:
        """读取题目要求文档（支持 .docx, .doc, .pdf），返回纯文本"""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"题目要求文档不存在: {filepath}")

        suffix = filepath.suffix.lower()
        if suffix == ".pdf":
            try:
                raw_text = _extract_text_from_pdf(filepath)
            except Exception:
                raw_text = _try_markitdown(filepath)
            if not raw_text:
                raise RuntimeError(f"无法解析题目要求文档: {filepath.name}")
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            return "\n".join(lines)

        is_doc = suffix == ".doc"
        temp_docx = None
        source_path = filepath

        if is_doc:
            temp_docx = _convert_doc_to_docx(filepath)
            source_path = temp_docx

        try:
            try:
                doc = Document(source_path)
                paragraphs = []
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        paragraphs.append(text)
                return "\n".join(paragraphs)
            except Exception:
                raw_text = _try_markitdown(filepath)
                if raw_text:
                    return raw_text
                raise
        finally:
            if temp_docx and temp_docx.exists():
                temp_docx.unlink()
                try:
                    temp_docx.parent.rmdir()
                except OSError:
                    pass
