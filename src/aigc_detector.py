"""
AIGC检测模块
检测论文中可能由AI生成的内容
"""

import re
from dataclasses import dataclass, field

from src.paper_parser import ParsedPaper


@dataclass
class AIGCResult:
    """AIGC检测结果"""
    student_name: str
    ai_probability: float = 0.0           # AI生成概率（0-1）
    is_suspicious: bool = False           # 是否可疑
    suspicious_segments: list[dict] = field(default_factory=list)  # 可疑段落
    ai_pattern_count: int = 0              # AI特征词出现次数
    format_issues: list[str] = field(default_factory=list)        # 格式问题
    image_issues: list[str] = field(default_factory=list)        # 图片问题
    overall_risk: str = "低风险"           # 总体风险等级


class AIGCDetector:
    """AI生成内容检测器"""

    # AI写作常见特征模式
    AI_PATTERNS = [
        # 开头模式
        r"首先[，,]\s*我们?需要?明确",
        r"在本文中[，,]\s*我们?",
        r"本文将?从以下几个方面",
        r"随着.*的发展[，,]",
        r"近年来[，,].*得到了广泛关注",
        r"不言而喻[，,]",
        r"众所周知[，,]",
        r"在当今社会",
        r"随着科技的不断发展",
        r"在这个快速发展的时代",

        # 过渡模式
        r"综上所述[，,]",
        r"总而言之[，,]",
        r"由此可见[，,]",
        r"不难看出[，,]",
        r"值得注意的是",
        r"需要指出的是",
        r"不可否认的是",
        r"毫无疑问",
        r"毋庸置疑",

        # 结尾模式
        r"未来[，,].*将会?",
        r"相信在不久的将来",
        r"我们应该?.*认识到",
        r"只有这样[，,].*才能",
        r"让我们?共同",

        # AI特有的"平衡"表达
        r"一方面.*另一方面",
        r"虽然.*但是.*因此",
        r"不仅.*而且.*同时",
    ]

    # 英文AI写作模式
    AI_PATTERNS_EN = [
        r"In conclusion[,\s]",
        r"To summarize[,\s]",
        r"It is worth noting that",
        r"It is important to note that",
        r"Furthermore[,\s]",
        r"Moreover[,\s]",
        r"In today's world",
        r"With the development of",
        r"As we all know",
    ]

    def __init__(self, config: dict):
        self.threshold = config.get("threshold", 0.6)
        self.fake_impl_weight = config.get("fake_impl_weight", 0.5)
        self.ai_writing_weight = config.get("ai_writing_weight", 0.4)
        self.custom_patterns = config.get("ai_patterns", [])
        # 编译正则
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in (self.AI_PATTERNS + self.AI_PATTERNS_EN)
        ]

    def detect(self, paper: ParsedPaper) -> AIGCResult:
        """检测论文的AI生成可能性"""
        result = AIGCResult(student_name=paper.student_name)

        # 1. 检测AI特征词
        self._detect_ai_patterns(paper.raw_text, result)

        # 2. 检测格式异常（可能是复制粘贴）
        self._detect_format_issues(paper, result)

        # 3. 检测图片问题
        self._detect_image_issues(paper, result)

        # 4. 检测文本特征（句子长度均匀度、词汇丰富度等）
        self._detect_text_features(paper.raw_text, result)

        # 计算总体AI概率
        self._calculate_probability(result)

        # 确定风险等级
        self._determine_risk_level(result)

        return result

    def _detect_ai_patterns(self, text: str, result: AIGCResult):
        """检测AI写作特征模式"""
        suspicious = []
        pattern_count = 0

        for pattern in self.compiled_patterns:
            matches = pattern.findall(text)
            if matches:
                pattern_count += len(matches)
                for match in matches[:3]:  # 每类模式最多记录3个
                    # 获取上下文
                    start = max(0, text.find(match) - 20)
                    end = min(len(text), text.find(match) + len(match) + 20)
                    context = text[start:end].replace("\n", " ")

                    suspicious.append({
                        "pattern": match if isinstance(match, str) else match[:50],
                        "context": f"...{context}...",
                        "type": "AI特征表达",
                    })

        result.ai_pattern_count = pattern_count
        result.suspicious_segments.extend(suspicious)

    def _detect_format_issues(self, paper: ParsedPaper, result: AIGCResult):
        """检测格式异常"""
        text = paper.raw_text

        # 检测是否有不连贯的格式切换（可能是多处复制粘贴）
        if text:
            # 检测异常的空行
            double_newlines = len(re.findall(r"\n{3,}", text))
            if double_newlines > 10:
                result.format_issues.append(f"存在{double_newlines}处异常空行，可能为复制粘贴")

            # 检测是否有明显的中英文混合标点
            mixed_punct = len(re.findall(r"[，。！？][,.!?]|[,.!?][，。！？]", text))
            if mixed_punct > 5:
                result.format_issues.append("存在中英文标点混用，可能来源于不同来源")

            # 检测是否有特殊的Unicode字符（可能是从网页复制）
            special_chars = len(re.findall(r"[​-‏ - ⁦-⁩]", text))
            if special_chars > 0:
                result.format_issues.append(f"存在{special_chars}个特殊Unicode字符，可能从网页复制")

    def _detect_image_issues(self, paper: ParsedPaper, result: AIGCResult):
        """检测图片问题"""
        if paper.figure_count > 0:
            # 如果图片数量异常多
            if paper.figure_count > 20:
                result.image_issues.append(f"图片数量异常多（{paper.figure_count}张），可能非原创")

            # 如果字数很少但图片很多
            if paper.word_count < 1000 and paper.figure_count > 5:
                result.image_issues.append("文字内容少但图片多，可能用图片凑字数")

    def _detect_text_features(self, text: str, result: AIGCResult):
        """检测文本统计特征"""
        if not text:
            return

        # 1. 句子长度均匀度（AI倾向于生成均匀的句子）
        sentences = re.split(r"[。！？.!?]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) > 5:
            lengths = [len(s) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)

            # 方差过小说明句子长度过于均匀
            if variance < 50 and avg_len > 10:
                result.suspicious_segments.append({
                    "pattern": "句子长度过于均匀",
                    "context": f"平均句长{avg_len:.1f}字，方差仅{variance:.1f}",
                    "type": "AI文本特征",
                })

        # 2. 词汇丰富度（重复词比例）
        words = re.findall(r"[一-鿿]{2,4}", text)
        if len(words) > 100:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                result.suspicious_segments.append({
                    "pattern": "词汇重复度高",
                    "context": f"词汇重复率{1-unique_ratio:.1%}，可能为模板化写作",
                    "type": "AI文本特征",
                })

    def _calculate_probability(self, result: AIGCResult):
        """计算AI生成概率（加强版）"""
        score = 0.0

        # AI特征词评分（权重更高）
        if result.ai_pattern_count > 15:
            score += 0.5
        elif result.ai_pattern_count > 10:
            score += 0.4
        elif result.ai_pattern_count > 5:
            score += 0.25
        elif result.ai_pattern_count > 2:
            score += 0.15

        # 格式问题评分（加强）
        score += len(result.format_issues) * 0.15

        # 图片问题评分（加强，可能是伪造）
        score += len(result.image_issues) * 0.2

        # 可疑段落评分（加强）
        score += min(len(result.suspicious_segments) * 0.08, 0.4)

        result.ai_probability = min(score, 1.0)
        result.is_suspicious = result.ai_probability >= self.threshold

    def _determine_risk_level(self, result: AIGCResult):
        """确定风险等级（更严格）"""
        prob = result.ai_probability
        if prob >= 0.7:
            result.overall_risk = "高风险"
        elif prob >= 0.45:
            result.overall_risk = "中风险"
        elif prob >= 0.25:
            result.overall_risk = "低风险"
        else:
            result.overall_risk = "正常"
