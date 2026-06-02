# 论文评审系统

一个自动化的学生课程报告检测与评分工具。支持智能评分标准生成、完整性检测、AI 评审、AIGC 检测和可选查重功能。

## 功能

1. **智能评分标准生成** — 每次运行自动将题目要求传给大模型，动态推断评分维度、权重、必要章节和字数要求
2. **完整性检测** — 检查报告是否包含必要章节，字数是否达标
3. **AI 智能评审** — 调用 OpenAI 兼容 API 多维度评分（60-89 分），提供评分依据和评语
4. **AIGC 检测** — 检测 AI 生成内容和可疑段落
5. **查重检测** — 学生报告两两比对（默认关闭，需 `--plagiarism` 开启）
6. **报告生成** — 自动生成 Excel 汇总表、Word 详细报告和 Markdown 评审报告
7. **支持 .doc** — 兼容旧版 Word 格式（自动转换修复）

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

将学生的 Word 报告（.docx 或 .doc）放入 `PAPERS_DIR` 指定的文件夹：

- 文件名建议包含学生姓名或学号
- 支持命名格式：`学部-专业-班级-学号-姓名.doc`、`姓名_题目.docx`、`学号-姓名.doc` 等

### 4. 运行评审

```bash
# 自动分析题目要求生成评分标准，然后评审（默认行为）
python main.py

# 仅生成评分标准，不评审
python main.py --generate-standards

# 使用已有评分标准，不重新生成
python main.py --skip-standards

# 跳过 AI 评审（仅做格式检测和 AIGC 检测）
python main.py --skip-ai

# 启用查重检测
python main.py --plagiarism
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `--papers, -p` | 论文文件夹路径（覆盖 .env 中的 PAPERS_DIR） |
| `--config, -c` | 评分标准配置文件（默认 config/requirements.yaml） |
| `--requirements-doc, -r` | 题目要求 Word 文档（覆盖 .env） |
| `--output, -o` | 输出目录（覆盖 .env） |
| `--skip-ai` | 跳过 AI 评审 |
| `--plagiarism` | 启用查重检测（默认关闭） |
| `--skip-standards` | 跳过 AI 自动生成评分标准，使用已有配置文件 |
| `--generate-standards, -g` | 仅生成评分标准后退出 |
| `--force-standards` | 强制重新生成评分标准 |

## 评分机制

- 每次运行自动调用 AI 分析题目要求，动态生成评分维度和标准
- 各维度分、综合总分、最终得分均控制 **60-89 分** 之间
- 评分依据引用学生报告具体内容
- 可使用 `--skip-standards` 固定已生成的评分标准

## 输出文件

| 文件 | 说明 |
|------|------|
| `scores_summary.xlsx` | Excel 汇总表（每个维度单独一列，含最终得分和评语） |
| `evaluation_report.docx` | Word 详细评审报告 |
| `evaluation_report.md` | Markdown 评审报告 |

## 项目结构

```
paper_evaluator/
├── config/
│   ├── requirements.yaml      # 评分标准（自动生成或手动编辑）
│   └── settings.yaml          # 非敏感系统配置
├── src/
│   ├── paper_parser.py        # Word 文档解析（支持 .doc / .docx）
│   ├── completeness_checker.py # 完整性检测
│   ├── ai_evaluator.py        # AI 评审（60-89 分范围）
│   ├── aigc_detector.py       # AIGC 检测
│   ├── plagiarism_checker.py  # 查重检测
│   ├── standards_generator.py # 智能评分标准生成
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
- 查重仅对比本次提交的论文之间，默认关闭
- 首次运行会自动调用 API 生成评分标准，需要有效的 API 配置
- `.doc` 文件依赖本地 Microsoft Word 转换（自动调用 COM 接口）
