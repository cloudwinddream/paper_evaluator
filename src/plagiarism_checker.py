"""
查重检测模块
检测学生论文之间的重复内容
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from src.paper_parser import ParsedPaper


@dataclass
class PlagiarismPair:
    """一对论文的查重结果"""
    student_a: str                   # 学生A
    student_b: str                   # 学生B
    similarity: float = 0.0          # 相似度（0-1）
    common_segments: list[dict] = field(default_factory=list)  # 重复段落
    is_plagiarism: bool = False      # 是否构成抄袭


@dataclass
class PlagiarismResult:
    """单个学生的查重结果"""
    student_name: str
    highest_similarity: float = 0.0           # 最高相似度
    most_similar_student: str = ""            # 最相似的学生
    suspicious_pairs: list[PlagiarismPair] = field(default_factory=list)  # 可疑配对


class PlagiarismChecker:
    """论文查重检测器"""

    def __init__(self, config: dict):
        self.similarity_threshold = config.get("similarity_threshold", 0.3)
        self.min_match_length = config.get("min_match_length", 20)
        self.ngram_size = config.get("ngram_size", 5)  # N-gram大小

    def check_all(self, papers: list[ParsedPaper]) -> list[PlagiarismResult]:
        """对所有论文进行两两查重"""
        results = {p.student_name: PlagiarismResult(student_name=p.student_name) for p in papers}

        # 两两比对
        pairs_to_check = []
        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                pairs_to_check.append((papers[i], papers[j]))

        print(f"[查重] 共需比对 {len(pairs_to_check)} 对论文")

        for idx, (paper_a, paper_b) in enumerate(pairs_to_check, 1):
            if idx % 10 == 0:
                print(f"  进度: {idx}/{len(pairs_to_check)}")

            pair_result = self._compare_pair(paper_a, paper_b)

            if pair_result.is_plagiarism:
                # 记录到双方的结果中
                results[paper_a.student_name].suspicious_pairs.append(pair_result)
                results[paper_b.student_name].suspicious_pairs.append(pair_result)

                # 更新最高相似度
                if pair_result.similarity > results[paper_a.student_name].highest_similarity:
                    results[paper_a.student_name].highest_similarity = pair_result.similarity
                    results[paper_a.student_name].most_similar_student = paper_b.student_name

                if pair_result.similarity > results[paper_b.student_name].highest_similarity:
                    results[paper_b.student_name].highest_similarity = pair_result.similarity
                    results[paper_b.student_name].most_similar_student = paper_a.student_name

        return list(results.values())

    def _compare_pair(self, paper_a: ParsedPaper, paper_b: ParsedPaper) -> PlagiarismPair:
        """比较两篇论文"""
        pair = PlagiarismPair(
            student_a=paper_a.student_name,
            student_b=paper_b.student_name,
        )

        # 使用多种方法检测相似度
        # 方法1：整体文本相似度
        overall_sim = self._text_similarity(paper_a.raw_text, paper_b.raw_text)

        # 方法2：N-gram指纹相似度
        ngram_sim = self._ngram_similarity(paper_a.raw_text, paper_b.raw_text)

        # 方法3：最长公共子串
        lcs_sim = self._lcs_similarity(paper_a.raw_text, paper_b.raw_text)

        # 取最高相似度
        pair.similarity = max(overall_sim, ngram_sim, lcs_sim)

        # 如果相似度较高，找出具体重复段落
        if pair.similarity > self.similarity_threshold:
            pair.common_segments = self._find_common_segments(
                paper_a.raw_text, paper_b.raw_text
            )
            pair.is_plagiarism = True

        return pair

    def _text_similarity(self, text_a: str, text_b: str) -> float:
        """计算两段文本的整体相似度"""
        if not text_a or not text_b:
            return 0.0
        return SequenceMatcher(None, text_a, text_b).ratio()

    def _ngram_similarity(self, text_a: str, text_b: str) -> float:
        """使用N-gram指纹计算相似度"""
        def get_ngrams(text, n):
            # 移除空白字符
            text = re.sub(r"\s+", "", text)
            return set(text[i:i+n] for i in range(len(text) - n + 1))

        ngrams_a = get_ngrams(text_a, self.ngram_size)
        ngrams_b = get_ngrams(text_b, self.ngram_size)

        if not ngrams_a or not ngrams_b:
            return 0.0

        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b

        return len(intersection) / len(union) if union else 0.0

    def _lcs_similarity(self, text_a: str, text_b: str) -> float:
        """基于最长公共子串的相似度"""
        if not text_a or not text_b:
            return 0.0

        matcher = SequenceMatcher(None, text_a, text_b)
        match = matcher.find_longest_match(0, len(text_a), 0, len(text_b))

        if match.size == 0:
            return 0.0

        # 最长公共子串占较短文本的比例
        shorter_len = min(len(text_a), len(text_b))
        return match.size / shorter_len if shorter_len > 0 else 0.0

    def _find_common_segments(self, text_a: str, text_b: str) -> list[dict]:
        """找出两段文本中的公共子串"""
        segments = []
        matcher = SequenceMatcher(None, text_a, text_b)

        for match in matcher.get_matching_blocks():
            if match.size >= self.min_match_length:
                segment = text_a[match.a:match.a + match.size]
                segments.append({
                    "text": segment[:100] + "..." if len(segment) > 100 else segment,
                    "length": match.size,
                })

        # 按长度排序，取前10个最长的
        segments.sort(key=lambda x: x["length"], reverse=True)
        return segments[:10]

    def get_plagiarism_summary(self, results: list[PlagiarismResult]) -> dict:
        """生成查重总结"""
        plagiarism_cases = []
        high_risk_students = set()

        for result in results:
            if result.highest_similarity > self.similarity_threshold:
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
