# 论文评审系统

一个自动化的学生课程报告检测与评分工具。支持完整性检测、AI 评审、AIGC 检测和查重功能。

## 功能

1. **完整性检测** — 检查报告是否包含必要章节（项目概述、功能实现、技术栈、项目结构、代码实现、演示截图、问题与方案、总结与展望）
2. **AI 智能评审** — 调用 OpenAI 兼容 API 多维度评分，提供评分依据和简短评语
3. **AIGC 检测** — 检测 AI 生成内容和可疑段落
4. **查重检测** — 学生报告两两比对，找出重复率高的配对
5. **报告生成** — 自动生成 Excel 汇总表、Word 详细报告和 Markdown 评审报告

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env` 并填入实际值：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
API_BASE_URL=https://your-api-endpoint.com/v1
API_KEY=your-api-key
API_MODEL=your-model-name
PAPERS_DIR=./学生论文文件夹路径
REQUIREMENTS_DOC=./题目要求.docx
OUTPUT_DIR=./outputs
```

### 3. 准备论文

将学生的 Word 报告（.docx）放入 `PAPERS_DIR` 指定的文件夹，文件名建议包含学生姓名：

- `张三_图书管理系统.docx`
- `李四_学生信息管理系统.docx`

### 4. 运行评审

```bash
# 使用 .env 中的配置直接运行
python main.py

# 或临时指定参数
python main.py --papers ./学生论文 --skip-ai
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `--papers, -p` | 论文文件夹路径（覆盖 .env） |
| `--config, -c` | 评分标准配置文件（默认 config/requirements.yaml） |
| `--requirements-doc, -r` | 题目要求 Word 文档（覆盖 .env） |
| `--output, -o` | 输出目录（覆盖 .env） |
| `--skip-ai` | 跳过 AI 评审 |

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 内容质量 | 30% | 项目完成度、功能完整性 |
| 技术能力 | 25% | 技术选型、代码质量、架构设计 |
| 文档规范 | 20% | 报告结构、格式、图表 |
| 创新性 | 10% | 创新点和独特方法 |
| 学术诚信 | 15% | 原创性 |

## 输出文件

- `scores_summary.xlsx` — Excel 汇总表（含每个维度分数）
- `evaluation_report.docx` — Word 详细报告
- `evaluation_report.md` — Markdown 评审报告

## 项目结构

```
paper_evaluator/
├── config/
│   ├── requirements.yaml      # 评分标准和维度
│   └── settings.yaml          # 非敏感系统配置
├── src/
│   ├── paper_parser.py        # Word 文档解析
│   ├── completeness_checker.py # 完整性检测
│   ├── ai_evaluator.py        # AI 评审
│   ├── aigc_detector.py       # AIGC 检测
│   ├── plagiarism_checker.py  # 查重检测
│   └── report_generator.py    # 报告生成
├── main.py                    # 主程序入口
├── .env                       # 敏感配置（不上传）
├── .env.example               # 配置模板
├── requirements.txt           # Python 依赖
└── .gitignore
```

## 注意事项

- `.env` 文件含 API 密钥，已加入 `.gitignore`，不会上传到仓库
- AIGC 检测结果仅供参考，需人工复核
- 查重仅对比本次提交的论文之间
