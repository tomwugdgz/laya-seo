# laya-seo

**级联式网站 SEO 审计：本地 Laya 判别模型作置信度闸门，Jev 云端模型作权威兜底。**

由 [jev-seo](https://github.com/AgriciDaniel/jev-seo) 分叉而来。爬虫、52 项规则、PageSpeed、
评分与三种报告格式**全部保持原样**；改变的是语义判断层——从「只调 Jev」变为「Laya 先判、
置信度不足才升级 Jev」。

---

## 为什么是级联，不是替换

原始设想是「把 Jev 内核换成 Laya」。**实测证明字面替换会产出高置信度的错误结论。**

2026-10-04，在 4 个已知答案的中文 SEO 页面上实测 Laya：

| 页面 | 正确答案 | Laya 判断 | 置信度 | |
| --- | --- | --- | --- | --- |
| 价格页 | pricing | pricing | 1.000 | ✓ |
| 文章页 | article_or_guide | **homepage** | **0.962** | ✗ |
| 产品页 | product_or_service | **homepage** | 0.642 | ✗ |
| 联系页 | contact_or_location | contact_or_location | 1.000 | ✓ |

**准确率 2/4，且错误与高置信度正相关。** 文章页被误判为 homepage 时置信度仍达 0.962，
会稳稳越过原项目的 `ACT=0.80` 阈值——报告会把错答案当作确定结论展示。

根因：Laya 的权重训练于金融交易语料（state 为 OHLC + EMA + ATR），迁移到 SEO 语义属于
跨域零样本推断。**它可以当闸门，不能当权威。**

好消息是两者接口同构：都使用 System One 原语 `choice` / `noul` / `score`，
`predict(state, questions)` 与 `POST /v1/systemone` 的输入输出结构几乎逐字段一致。
所以级联是纯工程问题，不是模型能力问题。

完整实测数据与阈值依据见 **[references/cascade.md](references/cascade.md)**。

---

## 工作方式

```
Laya 本地先判（$0，毫秒级，完全离线）
  ↓
整页加权置信度 ≥ 0.80 ?
  ├─ 是 → Laya 定案，跳过 Jev 调用
  └─ 否 → Jev 云端权威（$0.042/Mtok）
              ↓
          仍不确定 → 标记 needs_review，人工兜底
```

### 三条设计铁律

1. **单题置信度达标不直接采信。** 实测证明 Laya 单题 0.962 可能是错的，
   逐题 AND 挡不住。必须整页加权平均同时达标。
2. **所有答案带 `origin` 标记**（`laya` / `jev` / `code`），报告层必须能区分来源。
   XLSX 的 Semantic judgments 表有 Engine 列，Markdown 有引擎披露段落，
   `score.py` 的口径说明按实际引擎自动改写，不会让读者误以为全是生成式模型结论。
3. **阈值来自本项目实测，不照搬通用值。** `LAYA_Q_ACCEPT=0.95`、`LAYA_PAGE_ACCEPT=0.80`。

### 只有 choice 类参与采信判定

这是实测逼出来的设计。Laya 的 `confidence` 字段在不同原语上表现完全不同：

| 原语 | 实测 confidence | 判定 |
| --- | --- | --- |
| `choice` | 1.000 / 0.962 / 0.642，有区分度 | **参与采信** |
| `score` | `helpfulness` 置信度 0.075，但概率峰值落在正确答案 | 只记录，不参与 |
| `noul` | `noul=0.297`（判否）却报 confidence 0.703，方向相反 | 只记录，不参与 |

早期版本把三类都纳入计算，结果节省率恒为 0%——score 题把整页拉到了阈值以下。

### 特殊分流

| 任务 | 引擎 | 原因 |
| --- | --- | --- |
| 页面配对（内容重叠） | **强制 Jev** | Laya 在该任务上置信度不可靠，不适用闸门 |
| state 超 2000 token | **强制升级 Jev** | Laya 会截断输入，截断后得分不可信 |
| Jev 因配额被拒 | **退回 Laya 兜底** | 宁可给标注为代理判断的低置信度结果，也不留空 |

### 送入 Laya 的 state 会裁剪

Laya 上下文约 1024 token，Jev 宽松得多。实测中文真实页面在 6000 字符下估算
1000–1546 token，会被全部拦下导致节省率恒为 0。因此送 Laya 的 state 正文截到
1800 字符、outline 截 12 项、CTA 截 8 项（`cli.py:_shrink_for_laya`）。

---

## 供应商兼容性

`TYPESAFE_API_KEY` 对应的端点与模型名**可配置**，因为官方端点与中转站不同：

```bash
# .env 或环境变量
JEV_API_BASE=https://tokendance.space/gateway/typesafe/v1/systemone
JEV_MODEL=bocha-jev-v1
```

留空则用官方 `https://api.typesafe.ai/v1/systemone` + `jev-latest`。

### 中转站的账号级配额（重要）

实测中转站（tokendance.space）返回 `HTTP 422 token_budget_exceeded`：

| 题目数 | 结果 |
| --- | --- |
| 1 题 | OK |
| **2 题** | **OK**（input_tokens 32629） |
| 3 题起 | 422 |

且 `counted_tokens` 恒为 34417，**与本次发送多少题无关** —— 说明限额来自账号侧
累计配额，而非单次请求体。因此：

- `DEFAULT_MAX_QUESTIONS = 2`，按 2 题一批串行发送，批次间隔 1.1 秒；
- 页面级并发降到 2，避免多页同时挤占配额；
- 仍失败时退回 Laya 兜底，报告 Engine 列标 `Laya (fallback)`。

换回官方 key 后可调大 `DEFAULT_MAX_QUESTIONS`。

---

## 实测表现

`qinlinkeji.com`（中文站，6 页，2026-10-04）：

```
Laya 本地定案 3-4 页，其余升级 Jev —— 省去 50-67% 的 Jev 调用
Jev 10-17 次请求，$0.0043-0.0077
Laya 单次推理约 2 秒（RTX 4050，CUDA）
overall 86-88 / 100，18 个 action
```

6 页全部完成判定，`not_judged` 为空。引擎分布可从 XLSX 的 Engine 列逐条核对
（实测样本：Laya local 38 / Jev cloud 31 / Laya 兜底 13 / code 1）。

**尚未验证**：60 页规模下的节省比例。上面的数字来自 6 页样本，
`digest.md` 里的 `laya_savings_ratio` 是每次运行的实际值。

---

## 安装（Windows）

前置：Python 3.13、MSYS2（仅为 PDF 渲染提供 Pango）。

```bat
:: 1. 依赖
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install laya            :: 会一并装 torch（CUDA 版自动生效）

:: 2. Laya 权重（615 MB，与 PA_Agent 共用同一份）
::    没有则跑 D:\PA_Agent\tools\download_laya.py

:: 3. PDF 渲染所需的 Pango（可选 —— Markdown 与 XLSX 不需要它）
::    见本文末尾「PDF 渲染」一节

:: 4. 配置
copy .env.example .env
```

### 用法

```bat
bin\layaseo.cmd doctor                     :: 体检：依赖、权重、CUDA、密钥，绝不打印密钥值
bin\layaseo.cmd run https://example.com    :: 默认 laya-first 级联
bin\layaseo.cmd audit https://example.com --cascade offline   :: 纯 Laya，零 API 费用
bin\layaseo.cmd audit https://example.com --no-laya           :: 退回纯 Jev 模式
bin\layaseo.cmd render <dir> --formats md,xlsx                :: 只重出报告，零网络零花费
```

报告输出到 `./laya-seo-reports/<domain>-<stamp>/`，格式与原项目相同（PDF / XLSX / MD）。

---

## 双语报告（--lang）

同一份 `audit.json` 可以渲染出中英两个版本。**不需要重新爬站，不需要重新调用 API，零额外花费。**

```bat
:: 只出英文（默认）
bin\layaseo.cmd render <dir> --formats md,xlsx --lang en

:: 只出中文
bin\layaseo.cmd render <dir> --formats md,xlsx --lang zh

:: 一次出两套（推荐）
bin\layaseo.cmd render <dir> --formats md,xlsx --lang both
```

`--lang both` 产出：

| 文件 | 内容 |
|---| --- |
| `report.md` | 英文版 |
| `report.zh.md` | 中文版 |
| `report.xlsx` | 英文工作簿 |
| `report.zh.xlsx` | 中文工作簿 |
| `charts/*.png` | 英文图表 |
| `charts/*.zh.png` | 中文图表（图例文字已汉化） |

### 设计要点

**翻译发生在渲染层，不在采集层。** 这是一次审计、两份报告的关键——数据和
数字在两版中天然一致，不存在「翻译导致数字对不上」的可能。

**工作表名保持英文。** Summary 表里有 `COUNTIF(Actions!$E:$E, ...)` 这类公式，
若表名含中文，Excel 要求写成 `'行动项（Actions）'!$E:$E`（带单引号），
否则**公式静默失效**——用户看到的只是数字变成 0。表头是中文的，够用。

**状态值保持英文。** `to_do` / `in_progress` 等值参与下拉校验与 COUNTIF 匹配，
只有显示标签换成中文（待办 / 进行中 / …）。

**图表按语言隔离。** 图例文字在渲染时已烧进 PNG，中文图表存为 `*.zh.png`，
避免双语渲染时后一轮覆盖前一轮。

**中文字体自动探测。** 依次尝试微软雅黑 / 黑体 / 苹方 / 思源 / 文泉驿，
都没有则退回默认字体（文字仍可显示，只是不够美观）。
字体回退必须写在 `font.sans-serif` 列表里——设 `font.family=['雅黑','Inter']`
会让 matplotlib 跳过候选列表，仍报 132 条 Glyph missing 警告。

### 词条表

全部中文在 `jevseo/i18n.py`：

| 分区 | 内容 |
| --- | --- |
| `CATEGORIES_ZH` | 9 个评分区域名 |
| `SEVERITY_ZH` / `PRIORITY_ZH` / `EFFORT_ZH` | 严重度、优先级、成本档 |
| `ORIGIN_ZH` | 引擎来源（代码 / 规则 / Jev / Laya / Laya 兜底） |
| `RULES_ZH` | 72 条规则的 title 与 fix 建议 |
| `VOCAB_ZH` | 表头、章节名、字段标签等通用词汇 |

词条键做大小写与分隔符归一（`Searches/mo` → `searches_mo`），
带括号补充说明的表头会退化到主词查找（`Answer (0 to 1 or option)` → `answer`）。

**英文是原文，中文是补充。** 任何词条缺失都会回退到英文而不是留空——
报告永远可读。

### 关键参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--lang` | `en` | `en` / `zh` / `both` |
| `--cascade` | `laya-first` | `laya-first` 省费用；`jev-first` 仅调试对照；`offline` 零 API |
| `--laya-page-accept` | `0.80` | 整页采信阈值。**调高更保守但省钱更少** |
| `--laya-q-accept` | `0.95` | 单题参考阈值（记录用，不单独决定采信） |
| `--laya-device` | `auto` | `auto` / `cpu` / `cuda` |
| `--laya-model-dir` | `$LAYA_MODEL_DIR` | 权重目录 |
| `--no-laya` | — | 禁用 Laya，等价于原项目 |
| `--jev-budget` | `0.25` | Jev 花费硬上限（每次请求前检查） |

---

## PDF 渲染

Markdown 与 XLSX **不需要任何系统依赖**。PDF 需要 WeasyPrint，而它依赖 Pango
这个 C 库，pip 装不了。

**Markdown / XLSX 已经够用**：XLSX 是可编辑的行动追踪表（含 Engine 列），
Markdown 可直接进 Obsidian。只有需要给客户看打印件时才需要 PDF。

装 Pango（MSYS2 路径是 `C:\msys64`，不是 `C:\tools\msys64`）：

```bat
winget install --id MSYS2.MSYS2 --source winget
"C:\msys64\usr\bin\bash.exe" -lc "pacman-key --init"
"C:\msys64\usr\bin\bash.exe" -lc "pacman -S --needed mingw-w64-x86_64-pango mingw-w64-x86_64-pangoft2"
```

装完必须让 Python 进程启动前就能看到 DLL：

```bat
set "PATH=C:\msys64\mingw64\bin;%PATH%"
```

`bin\layaseo.cmd` 已内置这条 PATH。

**注意**：`pacman-key --init` 在 Windows 上可能跑几十分钟且看似卡住
（`pubring.gpg` 长时间为 0 字节）。若超过半小时仍无进展，
直接下载官方 GTK3 Runtime 替代：`https://github.com/nickvdyck/weasyprint-win/releases`。

验证：

```bat
set "PATH=C:\msys64\mingw64\bin;%PATH%"
.venv\Scripts\python -c "import weasyprint; print('ok')"
```

---

## 诚实的局限

**必须知道的四件事：**

1. **Laya 未在 SEO 语料上微调。** 现有的 `calibration.json` 是金融域 91 对样本训练的，
   **不适用于 SEO**。Laya 在 SEO 域的零样本准确率实测 2/4。
2. **省费比例只在 6 页样本上验证过。** 实测 50–67%，但样本小；
   `digest.md` 里的 `laya_savings_ratio` 是每次运行的实际值，不要引用本文的数字当保证。
3. **纯离线模式（`--cascade offline`）下**，页面配对判断与关键词判断不可用
   （这两项必须调 Jev），且报告会带 `PARTIAL AUDIT` 标记，说明语义判断是代理结果。
4. **PDF 需要额外的系统依赖。** 见上方「PDF 渲染」。未装 Pango 时
   `--formats pdf` 会报错，但 md 与 xlsx 正常。

**关于中转站配额**：默认的 `DEFAULT_MAX_QUESTIONS = 2` 是为 tokendance.space 的
账号级实测配额定的。用官方 TypeSafe key 时这个限制不存在，应调大该值以减少请求数
（当前设置会让 60 页的站点产生近 200 次请求）。

**要真正提升 Laya 在 SEO 域的可用性**，需复用 PA_Agent 已有的微调闭环
（收集标注 → 补标签 → 训练），需 ≥500 条/类样本。路线见
[references/cascade.md](references/cascade.md) 第五节。

---

## 测试

```bat
.venv\Scripts\python -m unittest discover -s tests -v
```

`tests/test_cascade.py` 覆盖全部决策逻辑，**52 个用例全部离线**，不加载权重、
不需要密钥、不产生费用：

- 级联决策：高置信度采信、低置信度升级、Laya 失败升级、state 超长升级、
  Jev 被拒时退回 Laya 兜底
- 置信度计算：choice 计入、score/noul 排除、`intent` 权重减半
- state 裁剪：正文截断、列表封顶、裁剪后落在限额内
- Jev 拆批：2 题一批、串行加间隔、单批失败整调用失败、422 分类可重试
- 口径披露：引擎标签随实际 origin 改写，`code` 不算引擎

`tests/test_jevseo.py` 是原项目测试。**其中 5 个渲染测试在未修改的上游仓库中同样失败**，
根因是 WeasyPrint 缺 Pango 运行时，不是本分叉引入的问题。

当前状态：`Ran 90 tests, 85 passed, 5 errors`（5 个错误即上述 Pango 问题）。

---

## 许可

MIT，与上游一致。Laya 是
[Convai Innovations](https://huggingface.co/convaiinnovations/laya) 的产品，
遵循其自身条款；Jev 是 TypeSafe AI 的产品，DataForSEO 与 PageSpeed Insights 为第三方服务。
