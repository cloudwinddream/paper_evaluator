# 论文评审系统

一个自动化的学生课程报告检测与评分工具。每次运行将题目要求传给大模型，由 AI 动态生成评分维度和完整性检测规则，再据之进行评审。

## 功能

1. **智能标准生成** — 每次运行自动将题目要求传给大模型，动态推断评分维度、权重、完整性规则（必要章节/字数/图表/格式）
2. **完整性检测** — 按 AI 生成的规则检查章节完整性、字数、图表、格式，扣分制计分（0-100）
3. **AI 智能评审** — 调用 OpenAI 兼容 API 多维度评分，含全链路穿透审计、12大问题标签、强制评分梯度分布
4. **AIGC 检测** — 检测 AI 生成内容、伪实现、截图造假，惩罚系数加权到最终得分
5. **查重检测** — 学生报告两两比对（默认关闭，需 `--plagiarism` 开启），含模板过滤/中文分词/MinHash指纹/AI辅助判断
6. **报告生成** — 自动生成 Excel 汇总表、Word 详细报告和 Markdown 评审报告
7. **支持 .doc / .pdf** — 兼容旧版 Word 格式（自动转换修复）和 PDF 格式
8. **MarkItDown 自动降级** — .docx/.doc/.pdf 解析失败时自动降级到 MarkItDown 兜底提取文本（依赖可选：`pip install markitdown`）
9. **多 Provider 自动容灾** — 配置多个 API Provider，遇限流(429)/鉴权失败/token超限/网络故障时自动切换
10. **后处理归一化** — AI 评审输出原始分数，报告生成后通过独立步骤调整输出范围与映射曲线
11. **增量评审** — 检测已有评审报告，自动跳过已评论文只审新增，合并新旧结果重新生成完整报告

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

将学生的报告（.docx / .doc / .pdf）或压缩包放入 `PAPERS_DIR` 指定的文件夹：

- 文件名建议包含学生姓名或学号
- 支持命名格式：`学部-专业-班级-学号-姓名.doc`、`姓名_题目.docx`、`学号_姓名.pdf` 等
- **支持 .zip 压缩包**：系统自动解压，将内部文档文件重命名为压缩包的名字（如 `张三.zip` → `张三.docx`），解压后自动删除压缩包
- 报告输出按**学号**自动排序（Excel / MD / Word 三个报告均按学号排列）

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
python main.py --score-min 0 --score-max 100

# 后处理归一化
python main.py --post-normalize ./outputs --output-min 60 --output-max 90 --output-exponent 1.5
```

**本地图形界面：**
```bash
python gui.py
```

图形界面提供路径浏览、LLM 配置（地址/密钥/模型，密钥可切换显示）、Provider 互换、分数范围自定义、选项勾选（跳过 AI/查重/跳过生成等）、运行/停止按钮、实时日志显示，配置自动保存到 `.env`。

## 参数说明

| 参数 | 说明 |
|------|------|
| `--papers, -p` | 论文文件夹路径（覆盖 .env 中的 PAPERS_DIR，支持 .docx/.doc/.pdf） |
| `--config, -c` | 评分标准配置文件（默认 config/requirements.yaml） |
| `--requirements-doc, -r` | 题目要求文档（支持 .docx/.doc/.pdf，覆盖 .env） |
| `--output, -o` | 输出目录（覆盖 .env） |
| `--skip-ai` | 跳过 AI 评审 |
| `--plagiarism` | 启用查重检测（默认关闭） |
| `--skip-standards` | 跳过 AI 自动生成评分标准，使用已有配置文件 |
| `--generate-standards, -g` | 仅生成评分标准后退出 |
| `--force-standards` | 强制重新生成评分标准 |
| `--score-min` | 内部最低分（默认 0，仅改变原始分数区间） |
| `--score-max` | 内部最高分（默认 100，仅改变原始分数区间） |
| `--incremental` | 增量模式：跳过已有评审结果的学生，只评审新增论文，合并输出完整报告 |
| `--post-normalize` | 对已有输出目录执行分数归一化后处理 |
| `--output-min` | 后处理归一化目标最低分（与 `--post-normalize` 搭配） |
| `--output-max` | 后处理归一化目标最高分（与 `--post-normalize` 搭配） |
| `--output-exponent` | 后处理映射指数（1.0=线性，>1=高分压缩，<1=低分压缩，与 `--post-normalize` 搭配） |

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

## 增量评审

当有部分论文已有评审结果时，可直接**增量续评**，跳过已评论文只审新增，合并输出完整报告：

```bash
python main.py --incremental
```

启动时自动检测输出目录中的 `scores_summary.xlsx`，读取已有结果过滤已评学生。支持两种触发方式：

1. **`--incremental` 参数** — 显式指定增量模式
2. **交互式检测** — 不带 `--incremental` 运行时，若检测到已有报告会询问是否增量

未评论文的图片分析 / 完整性检测 / AIGC 检测 / AI 评审照常执行。评审结果与已有结果合并，重新生成包含**全部**学生的 Excel 汇总表和 MD 报告。

GUI 模式下输出目录如有已有报告，自动勾选"增量评审" checkbox，也可手动切换。

### 容错处理
若 LLM 返回的 JSON 中 `dimensions` 或 `sections` 字段为字符串列表而非对象列表（如 `["功能完整性", "技术能力"]`），系统会自动将其转换为标准对象格式，避免 `'str' object has no attribute 'get'` 错误。

## 完整性评分

完整性检测按 AI 生成的规则以**扣分制**计分（0-100）：

- 各检查项从满分开始，每缺一项按项权重扣分
- 所有维度得分求和后归一化到百分制
- 有缺章时额外施加**缺章全局惩罚**：每缺一章扣减最终分的 12%（上限扣 60%）
- 例如缺 3 章 → 最终分 × 0.64，缺 4 章及以上 → 最终分 × 0.40
- 最终完整性得分在 0-100 之间

| 检查项 | 权重（AI 动态分配） | 说明 |
|--------|---------------------|------|
| 必要章节 | ~40% | 检测各章节是否存在（AI 提供模糊正则），每缺一章按章节权重扣分 |
| 字数 | ~25% | 是否达到最低字数要求，按比例扣分 |
| 图表/截图 | ~15% | 演示截图数量是否充足，按比例扣分 |
| 格式 | ~10% | 段落数、超长行占比等 |

各检查项权重由 AI 根据项目类型动态分配。

## 评分机制

### 分数归一化（两阶段分离）

系统采用**评审输出原始分 + 后处理归一化**分离机制：

1. **原始评分**：AI 管道输出 0-100 原始分数（可配 `--score-min`/`--score-max` 调整区间）
2. **后处理归一化**：评审完毕后通过独立步骤将原始分数映射到目标区间

```bash
# 1. 先运行评审，得到原始分数（默认 0-100）
python main.py

# 2. 查看原始分数分布，再决定归一化范围
python main.py --post-normalize ./outputs --output-min 60 --output-max 90 --output-exponent 1.5
```

### 最终得分公式

```python
# 1. 内部加权（0-100）
internal_score = completeness × 0.2 + total_score × 0.8

# 2. 惩罚扣减
if AIGC 可疑:   internal_score *= (1 - ai_probability × 0.8)   # 最高扣 80%
if 查重有风险:  internal_score *= (1 - highest_similarity × 0.3) # 最高扣 30%

# 3. 后处理归一化（仅在有映射参数时执行）
final_score = output_min + (internal_score / 100) ** output_exponent × (output_max - output_min)
```

后处理归一化的指数映射：
- `exponent=1.0`：线性映射（默认）
- `exponent>1.0`：高分区间压缩，低分区间拉伸
- `0<exponent<1.0`：低分区间压缩，高分区间拉伸

### AI 评审梯度分布（强制）

Prompt 内置强制分布要求，防止 AI 给分集中在高分段：

| 分数段 | 占比要求 | 典型特征 |
|--------|----------|----------|
| 90-100 | ≤20% | 全链路完整、有性能测试、截图真实 |
| 75-89 | 少数优秀 | 链路基本完整、有核心代码解释 |
| 60-74 | 多数良好 | 1-2处断裂、测试不充分 |
| 45-59 | 及格边缘 | 多处断裂、代码黑盒 |
| 0-44 | 不及格 | 伪实现、AI代写、核心缺失 |

### Prompt 模板
评审提示词存放在 `config/prompts/` 目录（.md 格式，已纳入版本管理），从文件动态加载，修改无需改动代码：

- `evaluation_system.md` — AI 评审系统提示词（V8.0 穿透审计版），含全链路流水线审计、12大问题标签、强制评分梯度、禁止空泛评语
- `standards_generation.md` — 评分标准生成提示词
- `standards_system.md` — 标准生成系统提示词
- `plagiarism_system.md` — AI 辅助查重判断提示词

### 12大问题标签体系
评审过程中自动标注以下缺陷标签：

| 标签 | 含义 |
|------|------|
| `[CODE_BLACKBOX]` | 代码黑盒：只贴代码无逻辑解释 |
| `[LOGIC_BREAK]` | 逻辑断层：需求章提到的功能在实现章消失 |
| `[FAKE_IMAGE]` | 截图造假：静态原型图伪装真实系统 |
| `[DATA_CONFLICT]` | 数据矛盾：需求章与测试章数据不一致 |
| `[DB_FLAW]` | 数据库缺陷：主外键缺失、范式违反 |
| `[EMPTY_TEST]` | 测试空洞：无测试用例、无性能数据 |
| `[ORPHAN_CHART]` | 图表孤儿：图表无正文引导和解释 |
| `[TECH_MISMATCH]` | 技术脱节：用了框架但未体现其核心特性 |

## AIGC 检测（加强版）

自动检测 AI 生成内容和伪实现，惩罚系数加权到最终得分：

- **AI 特征词检测**：中英文 AI 套话模式匹配
- **伪实现识别**：前端截图伪装、代码模板化、数据库与代码脱节
- **风险阈值**：0.7 高风险 / 0.45 中风险 / 0.25 低风险
- **惩罚权重**：AI 概率 × 0.8（最高扣 80%，在最终得分中直接扣减，Excel/MD 报告新增 AIGC 扣分列）

## 查重检测（`--plagiarism`）

默认关闭，需显式开启。启用后的检测流程：

1. **模板文本过滤** — 自动移除封面、目录、参考文献、致谢等公共部分
2. **三种方法取平均** — 字符 8-gram + jieba 词级 3-gram + MinHash 128 位指纹
3. **分级判定** — 疑似（≥0.35）/ 高度疑似（≥0.55）
4. **AI 辅助判断** — 对高度疑似对调用 LLM 做语义判定，可纠正误报
5. **惩罚权重**：相似度 × 0.3（最高扣 30%）

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
| `scores_raw.json` | JSON 原始评分明细（每个维度的原始分、未归一化） |
| `scores_summary.xlsx` | Excel 汇总表（每个维度单独一列，含最终得分和评语） |
| `evaluation_report.md` | Markdown 评审报告 |

## 本地图形界面（gui.py）

基于 Tkinter 的本地 GUI，与 CLI 共享同一套流水线：

| 功能 | 说明 |
|------|------|
| 路径配置 | 论文文件夹、题目要求文档、输出目录、评分标准文件，均带浏览按钮 |
| LLM 配置 | API 地址 / 密钥（可切换显示） / 模型，支持第二 Provider 备用，带 ⇅ 互换按钮 |
| 后处理归一化 | 独立面板设置目标输出范围（min/max）和映射指数，支持单独运行归一化 |
| 选项勾选 | 跳过 AI 评审、启用查重、增量评审、使用已有标准、强制重新生成 |
| 运行控制 | ▶ 开始评审 / 仅生成标准 / 运行归一化 / ■ 停止 |
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
│   ├── paper_parser.py        # 文档解析（支持 .docx / .doc / .pdf，含 MarkItDown 降级、PyMuPDF 图片计数）
│   ├── completeness_checker.py # 完整性检测（扣分制，0-100）
│   ├── llm_client.py          # 多 Provider LLM 客户端（自动容灾）
│   ├── ai_evaluator.py        # AI 评审（可配置分数范围）
│   ├── aigc_detector.py       # AIGC 检测
│   ├── plagiarism_checker.py  # 查重检测（MinHash/中文分词/AI辅助）
│   ├── standards_generator.py # 智能标准生成（评分+完整性规则）
│   ├── report_generator.py    # 报告生成（默认恒等映射，输出原始分）
├── main.py                    # CLI 入口（含后处理归一化逻辑）
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
- `.doc` 文件依赖本地 Microsoft Word 转换（自动调用 COM 接口，仅 Windows）；图片提取通过 Word COM 将文档另存为 HTML 后采集，自动过滤 < 20px 的微小图片
- `.pdf` 文件通过 `pypdf` 解析文本 + `PyMuPDF` 统计图片数量，失败时自动降级到 MarkItDown
- `markitdown` 为可选依赖（不安装不影响主流程，仅影响降级兜底能力）
- 查重功能依赖 `jieba` 分词库，需 `pip install -r requirements.txt`
- 归一化是后处理步骤，管道运行输出原始分数（0-100），评审结束后可用 `--post-normalize` 或 GUI "运行归一化" 调整分数区间
