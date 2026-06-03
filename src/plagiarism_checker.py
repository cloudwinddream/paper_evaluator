"""
查重检测模块 - 改进版
- 自动过滤模板文本（封面/目录/参考文献/致谢）
- 三种方法改进：字符 8-gram + 词级 3-gram（jieba）+ MinHash 指纹
- 取三方法平均值，分级判定（疑似/高度疑似）
- 可选 AI 辅助语义判断（对高度疑似对调用 LLM）
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from src.llm_client import LLMClient

PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ── 模板章节标题（用于过滤） ──
_TEMPLATE_HEADERS = [
    "封面", "封皮", "目录",
    "参考文献", "reference", "bibliography",
    "致谢", "谢辞", "acknowledgement",
    "附录", "appendix",
    "诚信声明", "原创性声明",
]


def _build_template_pattern() -> re.Pattern:
    """构建匹配模板章节的正则"""
    patterns = []
    for h in _TEMPLATE_HEADERS:
        patterns.append(rf"(?:^|\n)\s*第.+(?:章|节)\s+{h}\s*\n")
        patterns.append(rf"(?:^|\n)\s*{h}\s*\n")
    return re.compile("|".join(patterns), re.IGNORECASE)


_TEMPLATE_RE = _build_template_pattern()


def _remove_template_sections(text: str) -> str:
    """移除封面、目录、参考文献、致谢等模板章节"""
    return _TEMPLATE_RE.sub("\n", text)


def _char_ngrams(text: str, n: int = 8) -> set[str]:
    """字符级 n-gram（仅保留中英文和数字）"""
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", text)
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def _word_ngrams(text: str, n: int = 3) -> set[str]:
    """词级 n-gram（jieba 分词）"""
    import jieba
    clean = re.sub(r"[^\w\u4e00-\u9fff]", " ", text)
    words = [w.strip() for w in jieba.cut(clean) if w.strip()]
    return {":".join(words[i:i+n]) for i in range(len(words) - n + 1)}


def _minhash_signature(ngrams: set[str], num_hashes: int = 128) -> list[int]:
    """计算 MinHash 签名"""
    signatures = []
    for seed in range(num_hashes):
        min_hash = 2**64 - 1
        for ng in ngrams:
            h = hashlib.md5((str(seed) + ng).encode("utf-8")).hexdigest()
            val = int(h[:16], 16)
            if val < min_hash:
                min_hash = val
        signatures.append(min_hash)
    return signatures


def _minhash_similarity(sig_a: list[int], sig_b: list[int]) -> float:
    """估算 MinHash 签名间的 Jaccard 相似度"""
    if not sig_a or not sig_b:
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


# ── 判级 ──
_SUSPECT_THRESHOLD = 0.40
_HIGH_THRESHOLD = 0.60


def _grade_similarity(sim: float) -> str:
    if sim >= _HIGH_THRESHOLD:
        return "高度疑似"
    if sim >= _SUSPECT_THRESHOLD:
        return "疑似"
    return "正常"


@dataclass
class PlagiarismPair:
    """一对论文的查重结果"""
    student_a: str
    student_b: str
    similarity: float = 0.0
    severity: str = "正常"
    common_segments: list[dict] = field(default_factory=list)
    is_plagiarism: bool = False
    ai_judgment: str = ""


@dataclass
class PlagiarismResult:
    """单个学生的查重结果"""
    student_name: str
    highest_similarity: float = 0.0
    most_similar_student: str = ""
    suspicious_pairs: list[PlagiarismPair] = field(default_factory=list)


class PlagiarismChecker:
    """论文查重检测器（改进版）"""

    def __init__(self, config: dict, llm_client: Optional[LLMClient] = None):
        self.suspect_threshold = config.get("suspect_threshold", _SUSPECT_THRESHOLD)
        self.high_threshold = config.get("high_threshold", _HIGH_THRESHOLD)
        self.min_match_length = config.get("min_match_length", 30)
        self.char_ngram_size = config.get("char_ngram_size", 8)
        self.word_ngram_size = config.get("word_ngram_size", 3)
        self.minhash_hashes = config.get("minhash_hashes", 128)
        self.ai_check = config.get("ai_check", True)
        self.llm = llm_client

    def check_all(self, papers: list["ParsedPaper"]) -> list[PlagiarismResult]:
        from src.paper_parser import ParsedPaper

        results = {p.student_name: PlagiarismResult(student_name=p.student_name) for p in papers}

        processed = {}
        for p in papers:
            clean_text = _remove_template_sections(p.raw_text)
            char_set = _char_ngrams(clean_text, self.char_ngram_size)
            word_set = _word_ngrams(clean_text, self.word_ngram_size)
            sig = _minhash_signature(char_set, self.minhash_hashes)
            processed[p.student_name] = {
                "text": clean_text,
                "char_set": char_set,
                "word_set": word_set,
                "signature": sig,
            }

        pairs_to_check = []
        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                pairs_to_check.append((papers[i], papers[j]))

        print(f"[查重] 共需比对 {len(pairs_to_check)} 对论文")

        for idx, (paper_a, paper_b) in enumerate(pairs_to_check, 1):
            if idx % 10 == 0:
                print(f"  进度: {idx}/{len(pairs_to_check)}")

            pair_result = self._compare_pair(
                paper_a, paper_b,
                processed[paper_a.student_name],
                processed[paper_b.student_name],
            )

            if pair_result.is_plagiarism:
                results[paper_a.student_name].suspicious_pairs.append(pair_result)
                results[paper_b.student_name].suspicious_pairs.append(pair_result)

                if pair_result.similarity > results[paper_a.student_name].highest_similarity:
                    results[paper_a.student_name].highest_similarity = pair_result.similarity
                    results[paper_a.student_name].most_similar_student = paper_b.student_name

                if pair_result.similarity > results[paper_b.student_name].highest_similarity:
                    results[paper_b.student_name].highest_similarity = pair_result.similarity
                    results[paper_b.student_name].most_similar_student = paper_a.student_name

        return list(results.values())

    def _compare_pair(
        self,
        paper_a: "ParsedPaper",
        paper_b: "ParsedPaper",
        proc_a: dict,
        proc_b: dict,
    ) -> PlagiarismPair:
        from src.paper_parser import ParsedPaper

        pair = PlagiarismPair(
            student_a=paper_a.student_name,
            student_b=paper_b.student_name,
        )

        char_sim = self._jaccard_similarity(proc_a["char_set"], proc_b["char_set"])
        word_sim = self._jaccard_similarity(proc_a["word_set"], proc_b["word_set"])
        minhash_sim = _minhash_similarity(proc_a["signature"], proc_b["signature"])

        pair.similarity = round((char_sim + word_sim + minhash_sim) / 3, 4)
        pair.severity = _grade_similarity(pair.similarity)

        if pair.similarity >= self.suspect_threshold:
            pair.common_segments = self._find_common_segments(
                proc_a["text"], proc_b["text"]
            )

            if pair.similarity >= self.high_threshold:
                pair.is_plagiarism = True
                if self.ai_check and self.llm:
                    pair.ai_judgment = self._ai_judge(proc_a["text"], proc_b["text"])
                    if "非抄袭" in pair.ai_judgment or "不构成抄袭" in pair.ai_judgment:
                        pair.is_plagiarism = False
            else:
                pair.is_plagiarism = True

        return pair

    def _jaccard_similarity(self, set_a: set, set_b: set) -> float:
        if not set_a or not set_b:
            return 0.0
        inter = set_a & set_b
        union = set_a | set_b
        return len(inter) / len(union) if union else 0.0

    def _find_common_segments(self, text_a: str, text_b: str) -> list[dict]:
        segments = []
        matcher = SequenceMatcher(None, text_a, text_b)

        for match in matcher.get_matching_blocks():
            if match.size >= self.min_match_length:
                segment = text_a[match.a:match.a + match.size]
                segments.append({
                    "text": segment[:100] + "..." if len(segment) > 100 else segment,
                    "length": match.size,
                })

        segments.sort(key=lambda x: x["length"], reverse=True)
        return segments[:10]

    def _ai_judge(self, text_a: str, text_b: str) -> str:
        """调用 LLM 判断两篇论文是否抄袭"""
        try:
            system_prompt = _load_prompt("plagiarism_system.md")
            if not system_prompt:
                system_prompt = _load_prompt("plagiarism_system.txt")
            if not system_prompt:
                system_prompt = "你是一名查重专家。判断两篇课程设计报告是否存在实质抄袭。关注：共享相同的创新性内容/核心代码/独特表述 > 50% 才判定抄袭。模板文字、公共引用、通用技术术语不视为抄袭依据。仅回复「抄袭」或「非抄袭」。"
            resp = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"论文A：\n{text_a[:3000]}\n\n论文B：\n{text_b[:3000]}",
                    },
                ],
                temperature=0.1,
                max_tokens=128,
            )
            return resp.strip()
        except Exception as e:
            return f"AI 判断失败: {e}"

    def get_plagiarism_summary(self, results: list[PlagiarismResult]) -> dict:
        plagiarism_cases = []
        high_risk_students = set()

        for result in results:
            if result.highest_similarity >= self.suspect_threshold:
                plagiarism_cases.append({
                    "student": result.student_name,
                    "similar_to": result.most_similar_student,
                    "similarity": result.highest_similarity,
                })
                high_risk_students.add(result.student_name)

        return {
            "total_students": len(results),
            "suspected_plagiarism_count": len(plagiarism_cases),
            "high_risk_students": list(high_risk_students),
            "details": plagiarism_cases,
        }
