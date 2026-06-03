# 论文评审系统

一个自动化的学生课程报告检测与评分工具。每次运行将题目要求传给大模型，由 AI 动态生成评分维度和完整性检测规则，再据之进行评审。

## 功能

1. **智能标准生成** — 每次运行自动将题目要求传给大模型，动态推断评分维度、权重、完整性规则（必要章节/字数/图表/格式）
2. **完整性检测** — 按 AI 生成的规则检查章节完整性、字数、图表、格式，扣分制计分（满分 100，保底 60）
3. **AI 智能评审** — 调用 OpenAI 兼容 API 多维度评分，提供评分依据和评语（分数范围可配置，默认 60-89）
4. **AIGC 检测** — 检测 AI 生成内容和可疑段落
5. **查重检测** — 学生报告两两比对（默认关闭，需 `--plagiarism` 开启），含模板过滤/中文分词/MinHash指纹/AI辅助判断
6. **报告生成** — 自动生成 Excel 汇总表、Word 详细报告和 Markdown 评审报告
7. **支持 .doc** — 兼容旧版 Word 格式（自动转换修复）
8. **多 Provider 自动容灾** — 配置多个 API Provider，遇限流(429)/鉴权失败/token超限/网络故障时自动切换
9. **可配置分数范围** — 通过 `config/settings.yaml` 或 CLI 参数 `--score-min`/`--score-max` 自定义最低/最高分

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
# 第一 API Provider（必填）
API_BASE_URL=https://your-api-endpoint.com/v1
API_KEY=your-api-key
API_MODEL=your-model-name

# 第二 API Provider（可选，遇限流/鉴错时自动切换）
API_BASE_URL_2=https://api.openai.com/v1
API_KEY_2=sk-your-second-key
API_MODEL_2=gpt-4o-mini

# 第三、四……以此类推（可选）
# API_BASE_URL_3=...
# API_KEY_3=...
# API_MODEL_3=...

PAPERS_DIR=./学生论文文件夹路径
REQUIREMENTS_DOC=./题目要求.docx
OUTPUT_DIR=./outputs
```

### 3. 准备论文

将学生的 Word 报告（.docx 或 .doc）放入 `PAPERS_DIR` 指定的文件夹：

- 文件名建议包含学生姓名或学号
- 支持命名格式：`学部-专业-班级-学号-姓名.doc`、`姓名_题目.docx`、`学号-姓名.doc` 等

### 4. 运行评审

**命令行：**
```bash
# 自动分析题目要求生成评分标准和完整性规则，然后评审（默认行为）
python main.py

# 仅生成标准，不评审
python main.py --generate-standards

# 使用已有标准，不重新生成
python main.py --skip-standards

# 跳过 AI 评审（仅做完整性检测和 AIGC 检测）
python main.py --skip-ai

# 启用查重检测
python main.py --plagiarism

# 自定义分数范围
python main.py --score-min 50 --score-max 95
```

**本地图形界面：**
```bash
python gui.py
```

图形界面提供路径浏览、LLM 配置（地址/密钥/模型，密钥可切换显示）、Provider 互换、分数范围自定义、选项勾选（跳过 AI/查重/跳过生成等）、运行/停止按钮、实时日志显示，配置自动保存到 `.env`。

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
| `--score-min` | 最低分数（默认从 settings.yaml 读取，兜底 60） |
| `--score-max` | 最高分数（默认从 settings.yaml 读取，兜底 89） |

## 标准生成与加载机制

### AI 动态生成（默认）
每次运行（不传 `--skip-standards`）自动将题目要求发给大模型，输出包含两部分的 JSON：

1. **评分维度**（dimensions）：4-6 个维度，含名称、权重、详细评分说明
2. **完整性规则**（completeness）：必要章节检测正则、字数下限、图表下限、格式要求，以及各部分分值权重

生成结果保存至 `config/requirements.yaml`，AI 评审和完整性检测均读取该文件执行。

### 使用已有标准
```bash
python main.py --skip-standards
```
跳过 AI 生成，直接使用 `config/requirements.yaml` 现有配置。

### 强制重新生成
```bash
python main.py --force-standards
```
覆盖已有配置重新生成。

### 容错处理
若 LLM 返回的 JSON 中 `dimensions` 或 `sections` 字段为字符串列表而非对象列表（如 `["功能完整性", "技术能力"]`），系统会自动将其转换为标准对象格式，避免 `'str' object has no attribute 'get'` 错误。

## 完整性评分

完整性检测按 AI 生成的规则以**扣分制**计分：

- 各检查项从满分开始，每缺一项按项权重扣分
- 所有维度得分求和后归一化到百分制
- 最终完整性得分**最低 60 分**（保底），最高 100 分

| 检查项 | 权重（AI 动态分配） | 说明 |
|--------|---------------------|------|
| 必要章节 | ~40% | 检测各章节是否存在（AI 提供模糊正则），每缺一章按章节权重扣分 |
| 字数 | ~25% | 是否达到最低字数要求，按比例扣分 |
| 图表/截图 | ~15% | 演示截图数量是否充足，按比例扣分 |
| 格式 | ~10% | 段落数、超长行占比等 |

各检查项权重由 AI 根据项目类型动态分配。

## 评分机制

### 分数范围
所有分数默认在 **60-89 分**之间，可通过以下方式自定义：

1. **`config/settings.yaml`** — 全局默认配置
   ```yaml
   score_range:
     min: 60
     max: 89
   ```
2. **CLI 参数** — 覆盖 settings.yaml
   ```bash
   python main.py --score-min 50 --score-max 95
   ```
3. **GUI 界面** — 在配置面板直接输入最低/最高分

优先级：**CLI 参数 > settings.yaml > 代码默认（60-89）**

### 最终得分公式

```python
final_score = completeness × 0.2 + total_score × 0.8
if AIGC 可疑:  final_score *= (1 - ai_probability × 0.3)    # 最高扣 30%
if 查重有风险: final_score *= (1 - highest_similarity × 0.2) # 最高扣 20%
clamp(final_score, score_min, score_max)
```

- **completeness**：完整性检测得分（扣分制，保底 60）
- **total_score**：AI 多维度评审加权总分
- **AIGC 扣减**：检测到 AI 生成内容时，按概率最高扣减 30%
- **查重扣减**：检测到抄袭时，按相似度最高扣减 20%

### Prompt 模板
评审提示词存放在 `config/prompts/` 目录（.md 格式），从文件动态加载，修改无需改动代码：

- `evaluation_system.md` — AI 评审系统提示词，含 `{score_min}`/`{score_max}` 占位符
- `standards_generation.md` — 评分标准生成提示词
- `standards_system.md` — 标准生成系统提示词
- `plagiarism_system.md` — AI 辅助查重判断提示词

## 查重检测（`--plagiarism`）

默认关闭，需显式开启。启用后的检测流程：

1. **模板文本过滤** — 自动移除封面、目录、参考文献、致谢等公共部分
2. **三种方法取平均** — 字符 8-gram + jieba 词级 3-gram + MinHash 128 位指纹
3. **分级判定** — 疑似（≥0.4）/ 高度疑似（≥0.6）
4. **AI 辅助判断** — 对高度疑似对调用 LLM 做语义判定，可纠正误报

## API 多 Provider 自动容灾

可配置多个 API Provider（`API_*_2`、`API_*_3`……），按顺序优先使用第一个，遇以下情况立即切换到下一个：

- **429 限流** — 直接切换，不等待重试
- **401 鉴权失败** — API Key 无效时跳过
- **Token 超限** — 上下文过长时自动切换
- **网络超时/连接失败** — 网络故障时自动跳转

系统会遍历所有 Provider，直到成功返回结果；若全部失败则报错。

## 输出文件

| 文件 | 说明 |
|------|------|
| `scores_summary.xlsx` | Excel 汇总表（每个维度单独一列，含最终得分和评语） |
| `evaluation_report.docx` | Word 详细评审报告 |
| `evaluation_report.md` | Markdown 评审报告 |

## 本地图形界面（gui.py）

基于 Tkinter 的本地 GUI，与 CLI 共享同一套流水线：

| 功能 | 说明 |
|------|------|
| 路径配置 | 论文文件夹、题目要求文档、输出目录、评分标准文件，均带浏览按钮 |
| LLM 配置 | API 地址 / 密钥（可切换显示） / 模型，支持第二 Provider 备用，带 ⇅ 互换按钮 |
| 分数范围 | 自定义最低/最高分（默认 60-89），立即生效 |
| 选项勾选 | 跳过 AI 评审、启用查重、使用已有标准、强制重新生成 |
| 运行控制 | ▶ 开始评审 / 仅生成标准 / ■ 停止 |
| 实时日志 | 深色终端风格文本框，子进程输出逐行显示 |
| 自动保存 | 每次运行时路径和 API 配置写入 `.env`，下次启动自动加载 |

运行方式：`python gui.py`，无额外依赖（Tkinter 为 Python 内置）。

## 项目结构

```
paper_evaluator/
├── config/
│   ├── requirements.yaml      # 评分标准（自动生成或手动编辑）
│   ├── settings.yaml          # 非敏感系统配置（含分数范围）
│   └── prompts/               # LLM prompt 模板（.md 格式）
├── src/
│   ├── paper_parser.py        # Word 文档解析（支持 .doc / .docx）
│   ├── completeness_checker.py # 完整性检测（扣分制，保底 60）
│   ├── llm_client.py          # 多 Provider LLM 客户端（自动容灾）
│   ├── ai_evaluator.py        # AI 评审（可配置分数范围）
│   ├── aigc_detector.py       # AIGC 检测
│   ├── plagiarism_checker.py  # 查重检测（MinHash/中文分词/AI辅助）
│   ├── standards_generator.py # 智能标准生成（评分+完整性规则）
│   └── report_generator.py    # 报告生成
├── main.py                    # CLI 入口
├── gui.py                     # 本地图形界面（Tkinter）
├── .env                       # 敏感配置（不上传）
├── .env.example               # 配置模板
├── requirements.txt           # Python 依赖
└── .gitignore
```

## 注意事项

- `.env` 文件含 API 密钥，已加入 `.gitignore`，不会上传到仓库
- AIGC 检测结果仅供参考，需人工复核
- 查重仅对比本次提交的论文之间，默认关闭
- 首次运行会自动调用 API 生成评分标准和完整性规则，需要有效的 API 配置
- `.doc` 文件依赖本地 Microsoft Word 转换（自动调用 COM 接口）
- 查重功能依赖 `jieba` 分词库，需 `pip install -r requirements.txt`
