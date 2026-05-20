# 论文评审系统

一个自动化的学生课程报告检测与评分工具。支持智能评分标准生成、完整性检测、AI 评审、AIGC 检测和查重功能。

## 功能

1. **智能评分标准生成** — 将题目要求传给大模型，自动分析项目类型，生成评分维度、权重、必要章节和字数要求
2. **完整性检测** — 检查报告是否包含必要章节，字数是否达标
3. **AI 智能评审** — 调用 OpenAI 兼容 API 多维度评分，提供评分依据和简短评语
4. **AIGC 检测** — 检测 AI 生成内容和可疑段落
5. **查重检测** — 学生报告两两比对，找出重复率高的配对
6. **报告生成** — 自动生成 Excel 汇总表、Word 详细报告和 Markdown 评审报告

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
# 首次运行：自动分析题目要求生成评分标准，然后评审
python main.py

# 只生成评分标准，不评审
python main.py --generate-standards

# 强制重新生成评分标准
python main.py --force-standards

# 跳过 AI 评审（仅做格式检测和查重）
python main.py --skip-ai
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `--papers, -p` | 论文文件夹路径（覆盖 .env 中的 PAPERS_DIR） |
| `--config, -c` | 评分标准配置文件（默认 config/requirements.yaml） |
| `--requirements-doc, -r` | 题目要求 Word 文档（覆盖 .env） |
| `--output, -o` | 输出目录（覆盖 .env） |
| `--skip-ai` | 跳过 AI 评审 |
| `--generate-standards, -g` | 根据题目要求自动生成评分标准，然后退出 |
| `--force-standards` | 强制重新生成评分标准（覆盖已有配置） |

## 智能评分标准

系统可以将题目要求传给大模型，自动分析项目内容并生成评分标准：

- 自动识别项目类型（管理系统、网站、算法设计等）
- 生成 4-6 个评分维度，每个维度包含名称、权重和说明
- 确定学生报告中必须包含的章节
- 根据项目复杂度建议最低字数要求

生成的配置保存在 `config/requirements.yaml`，你可以手动调整。

## 输出文件

| 文件 | 说明 |
|------|------|
| `scores_summary.xlsx` | Excel 汇总表（每个维度单独一列，含最终得分和评语） |
| `evaluation_report.docx` | Word 详细评审报告 |
| `evaluation_report.md` | Markdown 评审报告（不含题目要求） |

## 项目结构

```
paper_evaluator/
├── config/
│   ├── requirements.yaml      # 评分标准（可自动生成或手动编辑）
│   └── settings.yaml          # 非敏感系统配置
├── src/
│   ├── paper_parser.py        # Word 文档解析
│   ├── completeness_checker.py # 完整性检测
│   ├── ai_evaluator.py        # AI 评审
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
- 查重仅对比本次提交的论文之间
- 首次运行会自动调用 API 生成评分标准，需要有效的 API 配置
