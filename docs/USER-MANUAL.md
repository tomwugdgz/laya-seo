# laya-seo 用户手册

> 这是完整操作手册。README 是门面，这份是说明书。
> 全部命令与参数都在本机（`D:\laya-seo`，Windows + Python 3.13）验证过。

---

## 目录

1. [先建立三个心理模型](#1-先建立三个心理模型)
2. [命令参考](#2-命令参考)
3. [参数全表](#3-参数全表)
4. [六种实战场景](#4-六种实战场景)
5. [怎么读报告](#5-怎么读报告)
6. [双语报告](#6-双语报告)
7. [写人工叙述 narrative.json](#7-写人工叙述-narrativejson)
8. [花多少钱、怎么封顶](#8-花多少钱怎么封顶)
9. [排错矩阵与 FAQ](#9-排错矩阵与-faq)
10. [附录](#10-附录)

---

## 1. 先建立三个心理模型

### 1.1 一次审计 = 一条七段流水线

```
① Crawl → ② Rule checks → ③ DataForSEO(可选) → ④ Laya+Jev → ⑤ PageSpeed → ⑥ Scoring → ⑦ Render
```

前六段产出 **`audit.json`**，第七段把它渲染成人看的报告。
**这两件事是彻底分开的**——这是理解整个工具的关键：

- `audit` / `run` = 采集 + 判断，联网，花钱；
- `render` / `rescore` = 只读 `audit.json`，**不联网、不花钱、不加载模型**。

所以改报告措辞、换语言、调评分逻辑，都不需要重跑一遍站。

### 1.2 分数不是「好坏」，是「九个区的加权平均」

`overall` 由九个分区加权合成。**没数据的区会被摘出去、权重重新归一**——
所以跑 `--full` 和不跑 `--full` 的分数不可直接比较（visibility 权重 15，量级很大）。

### 1.3 每条结论都得能回答「谁说的」

报告里每条判断都带 `origin`：`rule` / `jev` / `laya` / `laya-fallback` / `code`。
看到 `Laya (fallback)` 意味着**云端被拒过**，这条结论是本地兜底，可信度低于 `Jev cloud`。

---

## 2. 命令参考

统一入口是 `layaseo`。Windows 下用 `bin\layaseo.cmd`，它负责三件事：
切到项目根、把 `C:\msys64\mingw64\bin`（Pango）塞进 PATH、把 `.env` 读进环境变量。

也可以直接用 Python：

```bat
set "PYTHONPATH=%CD%"
.venv\Scripts\python -m jevseo doctor
```

> ⚠️ 用 `python -m jevseo` 时 `.env` **不会被自动加载**，
> 必须自己 `set TYPESAFE_API_KEY=...`，或者用 `pip install -e .` 后调 `jevseo` 入口。
> 所以日常推荐 `bin\layaseo.cmd`。

### 2.1 `doctor` —— 体检

```bat
bin\layaseo.cmd doctor
```

检查项：Python 版本、8 个第三方包、Laya 运行时/权重/设备、三个密钥是否存在、
以及**它替你推荐的运行模式**。

- **绝不打印密钥的值**，只说 `present` / `missing`。
- Laya 只探测权重文件是否存在，**不加载那 600MB**，所以秒出结果。
- `recommended` 三个可能值：
  - `laya-first` —— 权重与 API key 都有（最优）
  - `offline` —— 只有权重
  - `no semantic judgment` —— 都没有，语义判断会被整体跳过

典型输出：

```json
{
  "version": "0.1.2",
  "python": "3.13.12",
  "requests": "ok", "bs4": "ok", "lxml": "ok", "matplotlib": "ok",
  "openpyxl": "ok", "playwright": "ok",
  "weasyprint": "broken (OSError: cannot load library 'libgobject-2.0-0': error 0x7e)",
  "pdf": "unavailable: md and xlsx are unaffected",
  "laya": {
    "runtime": "ok", "weights": "ok", "device": "cuda",
    "torch": "2.14.1+cu130", "gpu": "NVIDIA GeForce RTX 4050 Laptop GPU",
    "model_dir": "C:\\Users\\...\\laya-models\\laya"
  },
  "TYPESAFE_API_KEY": "present",
  "PAGESPEED_API_KEY": "missing: PageSpeed runs unkeyed and may be rate limited",
  "DATAFORSEO": "missing: --full mode unavailable",
  "available_modes": ["laya", "jev"],
  "recommended": "laya-first"
}
```

依赖有三档状态，认准了再看 `pdf` 字段：

| 状态 | 含义 | 处理 |
| --- | --- | --- |
| `"ok"` | 可用 | — |
| `"missing (xxx)"` | 包没装 | `pip install` |
| `"broken (OSError: ...)"` | 包装了，但系统缺 DLL（典型是 Pango） | 见 §9.3；**md/xlsx 不受影响** |

> `pdf` 是 0.1.2 新增的衍生字段：`available` 或 `unavailable`。
> 同时修了一个 bug——过去 `doctor` 遇到 WeasyPrint 的 `OSError` 会跟着崩，
> 体检工具自己崩了就没意义了。

**第一次使用请先跑这个。** 90% 的「跑不起来」能在这里一步定位。

### 2.2 `audit <url>` —— 采集 + 判断，产出 `audit.json`

```bat
bin\layaseo.cmd audit https://example.com
```

不渲染报告，只写 `audit.json` + `digest.md`。适合：
先看看数据和花费，满意了再决定怎么出报告。

默认行为：最多 60 个 URL、深度 5、600 秒抓取预算、PageSpeed 测 3 页、
`laya-first` 级联、Jev 花费上限 $0.25。

### 2.3 `render <dir>` —— 只出报告

```bat
bin\layaseo.cmd render laya-seo-reports\example-com-2026-10-05-0930 --formats md,xlsx --lang both
```

- 输入：`audit.json`（必需）+ `narrative.json`（可选）
- **零网络、零费用、不加载 Laya 模型**
- 适用于：换语言、改 `narrative.json` 后重出、只要某个格式

### 2.4 `rescore <dir>` —— 重算分数

```bat
bin\layaseo.cmd rescore laya-seo-reports\example-com-2026-10-05-0930
```

当你**改了规则或评分代码**却不想重新爬站时用。它从存档里重建 findings / scores / actions。

⚠️ 行动项 ID（`JEV-0xx`）是按优先级排序后重排的，**重算后 ID 可能变化**。
如果你写了 `narrative.json` 引用了旧 ID，渲染时会被拒绝并提示。

### 2.5 `run <url>` —— 一步到位

`run` = `audit` + `render`。日常最常用。

```bat
bin\layaseo.cmd run https://example.com --formats md,xlsx --lang zh
```

---

## 3. 参数全表

### 3.1 采集参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--max-pages` | `60` | 爬虫最多抓多少 URL。站点大就调大，但注意 Jev 是按页计费的 |
| `--max-depth` | `5` | 距首页最多几跳。`--max-pages 20 --max-depth 2` 适合快速摸底 |
| `--time-budget` | `600` | 抓取时间预算（秒）。慢站可能会被提前截断 |
| `--render` | `auto` | `auto`：只对疑似 SPA 用 Playwright 渲染；`always`：全部渲染（慢很多，需装 playwright）；`never`：纯 HTTP |
| `--out` | 自动 | 输出目录。默认 `laya-seo-reports/<domain>-<YYYY-MM-DD-HHMM>`，自动去掉 `www.` |

### 3.2 语义判断参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--cascade` | `laya-first` | 见 4.4 的模式对比 |
| `--jev-pages` | `60` | 最多送多少页去做语义判断。大站想省钱就调小（按重要性排序后截断） |
| `--jev-budget` | `0.25` | Jev 花费硬顶，**每次请求前检查**，超了就跳过剩余请求（不会报错） |
| `--no-jev` | — | 彻底关闭语义判断（等价于上游的 `--no-jev`） |
| `--no-laya` | — | 禁用本地模型，退回纯 Jev |

### 3.3 Laya 本地模型参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--laya-model-dir` | `$LAYA_MODEL_DIR` → `~/laya-models/laya` | 权重根目录 |
| `--laya-subfolder` | `multilingual` | 权重子目录。传**空字符串**用英文档：`--laya-subfolder ""` |
| `--laya-device` | `auto` | `auto` / `cpu` / `cuda`。想在笔记本上省电用 `cpu` |
| `--laya-page-accept` | `0.80` | **整页加权置信度 ≥ 此值才本地定案。** 调高 → 更保守、更贵、更准；调低 → 更省钱、更冒险。**不建议低于 0.70** |
| `--laya-q-accept` | `0.95` | 单题参考阈值，仅记录用，不单独决定采信 |

### 3.4 PageSpeed 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--psi-pages` | `3` | 测几页（每页跑 mobile + desktop 两次） |
| `--no-psi` | — | 跳过。性能分会退化为「抓取耗时观测」，报告标 `partial` |

> 网络到不了 Google 时必须加 `--no-psi`，
> 否则会卡到超时然后报 `ProxyError`。先确认：
> `curl -s -o /dev/null -w "%{http_code}" "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://example.com"`

### 3.5 DataForSEO 参数（`--full`）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--full` | — | 开启排名、关键词、竞品、外链、SERP、AI 提及（付费） |
| `--location-code` | `2840` | DataForSEO 国家码。美国 2840，**中国 2156**，英国 2826 |
| `--language` | `en` | 语言码 |
| `--dfs-budget` | `1.0` | DataForSEO 花费硬顶 |
| `--reuse-dfs` | — | 复用上次 `--full` 的付费数据，**零新增花费** |

`--reuse-dfs` 的正确用法（同一站点，第二次以后）：

```bat
bin\layaseo.cmd run https://example.com --full --reuse-dfs laya-seo-reports\example-com-2026-10-05-0930 --lang zh
```

它会校验 domain 一致，不一致就直接退出，不会拿错数据。

### 3.6 渲染参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--formats` | `pdf,xlsx,md` | 逗号分隔，任意组合 |
| `--lang` | `en` | `en` / `zh` / `both` |

> `--lang` 只对 `render` 和 `run` 有效。`audit` 不带这个参数。

---

## 4. 六种实战场景

### 场景 A：第一次给客户做站，要一份能交付的东西

```bat
bin\layaseo.cmd doctor
bin\layaseo.cmd run https://client-site.com --formats md,xlsx --lang both
```

拿到 autosummary 看看数据，然后手动写 `narrative.json`（见第 7 节），再：

```bat
bin\layaseo.cmd render laya-seo-reports\client-site-com-2026-10-05-0930 --formats pdf,md,xlsx --lang both
```

> 手工叙述这一步**不能省**。自动摘要是「证据罗列」，不是「给老板看的结论」，
> 报告里也会老老实实标注 `Automatic summary (no lead-agent narrative was written)`。

### 场景 B：不想花一分钱的本地体检

```bat
bin\layaseo.cmd audit https://example.com --cascade offline --no-psi
bin\layaseo.cmd render laya-seo-reports\... --formats md,xlsx --lang zh
```

$0，但会带三条 `PARTIAL AUDIT` 提示。适合内部排队扫一遍再决定哪些站值得花钱。

### 场景 C：大站排查（控制花费）

```bat
bin\layaseo.cmd run https://big-site.com `
  --max-pages 40 --max-depth 3 `
  --jev-pages 15 --jev-budget 0.15 `
  --no-psi --formats md,xlsx --lang zh
```

要点：**限制 `--jev-pages`**，因为 Jev 是按页送判断的唯一花钱项。
`--max-pages 40` 控制抓取，抓取本身不花钱。

### 场景 D：完整竞争情报（有 DataForSEO 账号）

```bat
bin\layaseo.cmd run https://example.com --full --location-code 2156 --dfs-budget 2.0 --lang zh
```

会多出 visibility 区（权重 15），有关键词排名、估算流量、外链、搜索竞品、
SERP 是否出现 AI Overview、AI 回答里有没有被引。

> `--location-code 2156` 是中国。默认 2840 是美国，别忘改。

### 场景 E：改了规则代码，只想重算

```bat
bin\layaseo.cmd rescore laya-seo-reports\example-com-2026-10-05-0930
bin\layaseo.cmd render  laya-seo-reports\example-com-2026-10-05-0930 --formats md,xlsx --lang zh
```

### 场景 F：批量巡检多个站

```bat
for %%s in (site-a.com site-b.com site-c.com) do (
  bin\layaseo.cmd run https://%%s --max-pages 25 --jev-pages 10 --no-psi --formats md,xlsx --lang zh
)
```

每个站一个独立目录，互不干扰。想汇总就把各站的 `audit.json → scores` 抽出来比。

---

## 5. 怎么读报告

### 5.1 先看综合分，再看为什么被拉下来

`overall` = 九个区的加权平均，**只有有数据的区参与**（权重自动重新归一）。

| 区 | 权重 | 内容与 AI 区由谁得出 |
| --- | --- | --- |
| `crawl` | 20 | 规则 |
| `content` | 20 | **70% 语义判断 + 30% 规则** |
| `onpage` | 15 | 规则 |
| `visibility` | 15 | `--full` 才有（缺 → 不参与） |
| `ai` | 12 | **70% 语义判断 + 30% 规则** |
| `links` | 10 | 规则 |
| `performance` | 10 | 50% Lighthouse + 50% 抓取观测 |
| `structured` | 8 | 规则 |
| `security` | 5 | 规则 |

等级：**A ≥ 90，B ≥ 75，C ≥ 60，D ≥ 40，F < 40。**

**封顶**：分数有两个硬性天花板，看到 `caps` 就直接排除一切解释：

- robots.txt 屏蔽全站 / 首页 `noindex`（critical）→ **封顶 20**
- 站点没走 HTTPS → **封顶 60**

### 5.2 `partial` / `caps` / `completeness` 三个字段比分数重要

```json
"partial": ["PageSpeed Insights unavailable, so performance used crawl timings only"],
"caps": [],
"completeness": {"categories_scored": 8, "categories_total": 9,
                 "jev": true, "jev_pages_not_judged": 0,
                 "pagespeed": false, "dataforseo": false}
```

读法：

- `categories_scored 8/9` —— 有一个区没数据，别把 78 分当成「这个站全面 78 分」；
- `pagespeed: false` —— 性能分区只用了抓取耗时，偏乐观；
- `jev_pages_not_judged: 0` —— 语义判断没有缺口；**非零就说明有些页压根没判**，
  「没发现」不等于「没问题」；
- `offline` 模式还会多一条：内容/AI 区来自本地代理判断，是 provisional 的。

### 5.3 行动项表是真正干活的部分

XLSX 的 `Actions` 表（或 Markdown 的 Priority actions 表）：

| 列 | 怎么理解 |
| --- | --- |
| ID | `JEV-0xx`，写 narrative 时引用它 |
| Severity | critical / high / medium / low，扣分权重 25 / 12 / 6 / 2 |
| Impact | 预期提升幅度 |
| Effort | hours / about a day / several days / a project |
| Priority | 按 (impact, severity, effort) 综合排序的结果 |
| Engine | 见下 |
| Evidence | 具体 URL / 数字 / 状态码 |

**Effort 列怎么用**：`hours` 的先做，`a project` 的放进季度计划，别和日常混在一起。

### 5.4 Engine 列：逐条溯源

| Engine 值 | 含义 | 该怎么信任 |
| --- | --- | --- |
| `Rule` | 确定性规则 | 直接信，但**人工复核有没有重定向误报** |
| `Jev cloud` | 云端 Jev 判定 | 最高可信度 |
| `Laya local` | 本地模型定案 | 加权置信度 ≥ 0.80 才走到这里 |
| `Laya (fallback)` | Jev 被拒后兜底 | **最弱**。配额紧张时会出现，建议人工看一眼 |
| `DataForSEO` | 第三方数据 | 注意是**估算值** |
| `code` | 代码直接判定 | 「这是首页」之类已知答案，绝对可靠 |

### 5.5 已知误报类型

- **重定向被算成坏链。** 工具不跟随重定向，
  `301/302 → 目标页` 会被记为 broken link。
  （例：Discuz 的 `forum.php?mobile=yes` 跳 `/m/`，被 JEV-003 误报。
  Evidence 里会给出原始状态码，据此判断。）
- **AI 可读性是编辑 heuristics。** Google 明确说 AI 功能不需要特殊优化，
  报告里也这么标注。**别当排名因素卖。**

---

## 6. 双语报告

同一份 `audit.json` 出中英两版，**不重爬、不重算、不花钱**。

```bat
:: 只英文
bin\layaseo.cmd render <dir> --formats md,xlsx --lang en

:: 只中文
bin\layaseo.cmd render <dir> --formats md,xlsx --lang zh

:: 两套一起（推荐）
bin\layaseo.cmd render <dir> --formats md,xlsx --lang both
```

| 文件 | 内容 |
| --- | --- |
| `report.md` | 英文 |
| `report.zh.md` | 中文 |
| `report.xlsx` | 英文工作簿 |
| `report.zh.xlsx` | 中文工作簿 |
| `charts/*.png` | 英文图表 |
| `charts/*.zh.png` | 中文图表 |

### 六个不该动的约定

1. **翻译在渲染层。** 采集层保持语言无关，两版数字天然一致。
2. **工作表名必须英文。** Summary 里有 `COUNTIF(Actions!$E:$E,...)`。
   表名改中文后 Excel 要求 `'行动项（Actions）'!$E:$E`，否则**公式静默失效**（显示 0，不报错）。
3. **状态值必须英文。** `to_do` / `in_progress` 参与下拉校验和 COUNTIF 匹配，
   只有显示标签汉化。
4. **图表按语言隔离。** 图例在渲染时就烧进 PNG，中文版另存 `*.zh.png`，否则互相覆盖。
5. **字体回退写在 `font.sans-serif` 列表里。**
   写成 `font.family=['雅黑','Inter']` 会让 matplotlib 跳过候选列表，
   直接得到 132 条 `Glyph missing` + 满屏豆腐块。
6. **缺词条回退英文，不留空。** 英文是原文，中文是补充。

### 改中文词条

全部在 `jevseo/i18n.py`。规则词条 74 条、通用词汇 228 条、分类 9 条。

**规则 key 必须从代码里枚举，不要猜。** 猜错 key 不会报错，
只会让中文报告默默回退英文——曾经有段时间 36/72 的 key 是猜的，
引入排查成本极高。当前覆盖校验：

```bat
.venv\Scripts\python -c "import sys;sys.path.insert(0,'.');from jevseo import checks,score;from jevseo.i18n import RULES_ZH;ids=set(checks.RULES)|set(score.JEV_RULES)|set(score.DFS_RULES)|{'cwv_field','lab_performance'};print('missing:',sorted(i for i in ids if i not in RULES_ZH))"
```

期望输出：`missing: []`

---

## 7. 写人工叙述 `narrative.json`

在审计输出目录放下这个文件，`render` 会把它放进报告的 Executive Summary。
**没有它就退化成证据罗列式的自动摘要**，报告里会明确标注。

### 最小可用模板

```json
{
  "executive_summary": [
    "第一段：总体判断，把分数和主要拉分项说清楚。",
    "第二段：对这个业务最要紧的一两个问题，引用行动项 ID，比如 JEV-003。"
  ],
  "strengths": ["三到五条做得好的地方，每条挂证据。"],
  "risks": ["三到五条拖后腿的，每条引用行动项 ID。"],
  "plan": [
    { "horizon": "This week",   "items": ["JEV-003 修掉失效的内链 (hours)"] },
    { "horizon": "This month",  "items": ["JEV-012 补齐产品页的结构化数据 (about a day)"] },
    { "horizon": "This quarter","items": ["JEV-021 重建内容层级 (a project)"] }
  ],
  "closing": "修完之后看什么指标；或者这次审计没看到什么。",
  "author": "谁写的"
}
```

必需键：`executive_summary`、`strengths`、`risks`、`plan`。缺任何一个直接退出报错。

### 三条硬约束（渲染时会校验）

1. **引用的每个 `JEV-###` 必须真实存在**，否则拒绝渲染并列出不存在的 ID。
2. **plan 里的 effort 档必须和行动项表一致**
   （`hours` / `about a day` / `several days` / `a project`），
   不一致会打 WARNING。
3. **叙述里出现而审计里查不到的数字会被标出来**（允许四舍五入与 ms→s 换算），
   目的就是防止「随口编个 30%」。

### 写作准则

完整合同见 [`references/narrative.md`](../references/narrative.md)，要点：

- 写给站主看，不写给 SEO 同行看。先说**业务后果**（「用户落地后看不到你在卖什么」）再说改法。
- 每个论断都要能追溯到 `digest.md` 或你自己确认过的事实。**不许新增指标、流量估算、排名预测。**
- 明确区分「规则测出来的」和「模型判出来的」。
- 你要是复核时发现误报，简短点出来。
- 篇幅克制：摘要 2–3 段，每个列表 3–5 条，每个 horizon 3–5 项。
- 不用破折号，不用 hype 词，**不许说 canCause（「这限制了」「因为」）审计没测过的因果关系**。
- 绝对词（「所有」「全都」）只能在 digest 显示全量检查时用；抽样就说「抽查的每一页」。
- **AI 搜索那几条是编辑 heuristics，永远不当排名因素写。**

写完之后：

```bat
bin\layaseo.cmd render <dir> --formats md,xlsx --lang both
```

控制台会打印 WARNING，**有 WARNING 就改到干净为止**。

---

## 8. 花多少钱、怎么封顶

### 只有两项真的花钱

| 项目 | 单价 | 触发条件 |
| --- | --- | --- |
| **Jev 语义判断** | **$0.042 / Mtok** | 每送一页就烧 token |
| DataForSEO | 按次 | 只有 `--full` |

抓取、规则检查、Markdown/XLSX 渲染、本地 Laya 推理——**全部 $0**。

### 三道防线

1. `--jev-budget 0.25`（默认）**每次请求前检查**，超了跳过剩余请求，不报错中断；
2. `--dfs-budget 1.0` 同理管 DataForSEO；
3. `--jev-pages N` 限制送审页数。

先看预估，再看账单：

```bat
bin\layaseo.cmd audit https://example.com --jev-pages 10 --jev-budget 0.10
type laya-seo-reports\...\digest.md | findstr /I "cascade Jev ledger cost"
```

真实账单字段在 `audit.json`：

```
jev.ledger.jev_api.requests      请求数
jev.ledger.jev_api.failed        失败数
jev.ledger.jev_api.input_tokens  实际 token
jev.ledger.cost_usd              本次花费
jev.cascade.laya_savings_ratio   Laya 省下的比例
```

### 实测花费参考

| 站点 | 页数 | Jev 花费 | Laya 节省率 |
| --- | --- | --- | --- |
| `qinlinkeji.com` | 6 | $0.0043–0.0077 | 50–67% |
| `duckwolf.cn` | 7 HTML | <$0.01 | **0%** |

**省费率不是承诺。** 取决于站点类型——信息密度高的企业站省得多，
论坛/薄页站可能一页都省不下来（这是闸门在正确工作）。

### 中转站配额（最容易踩的坑）

响应里的 `counted_tokens` **跟你这次发了几题无关**（恒定 34000 上下），
说明限额是**账号级累计**，不是单次请求体。对策已经内建：

- `DEFAULT_MAX_QUESTIONS = 2` —— 2 题一批串行发送，批次间歇 1.1 秒；
- 页面并发降到 2；
- 重试阶梯会逐级缩短正文再试；
- 全败 → tag 成 `Laya (fallback)`，**报告不会缺这页**。

**用官方 TypeSafe key 时请调大 `DEFAULT_MAX_QUESTIONS`**（在 `jevseo/jev.py`），
否则 60 页站点会拆出近 200 次请求，纯粹浪费时间。

---

## 9. 排错矩阵与 FAQ

### 9.1 排错矩阵

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `No module named laya` | 没装 Laya 运行时 | `pip install laya`，或 `--no-laya` 退回纯 Jev |
| `available_modes: []` | 权重和 API key 都没有 | 语义判断整体跳过，报告标 PARTIAL；先补权重或 key |
| torch 版本里没有 `+cu` | pip 装的是 CPU 版 | `pip install torch --index-url https://download.pytorch.org/whl/cu130` |
| 每页都升级 Jev，节省率 0% | 页面太薄，Laya 置信度上不去 | **正确行为**。想更激进可下调 `--laya-page-accept`，但别低于 0.70 |
| `HTTP 422 token_budget_exceeded` | 中转站账号级配额 | 等窗口 / 换官方 key / 调大批量；失败页自动走 Laya 兜底 |
| Engine 列一大片 `Laya (fallback)` | Jev 被拒 | 这些页结论可信度较低，建议人工复核或换个时间重跑 |
| WeasyPrint `could not import some external libraries` | 缺 Pango | 见 9.3。md/xlsx 不受影响 |
| Google PSI 报 `ProxyError` / `HTTP=000` | 本机到不了 Google | 加 `--no-psi` |
| XLSX 的 Status 统计全是 0 | 你把工作表改名成中文了 | 表名必须英文 |
| 中文图表全是豆腐块 | 字体回退写错位置 | 要写在 `font.sans-serif` 列表 |
| `narrative.json is missing [...]` | 缺必需键 | 四个必需键：`executive_summary`/`strengths`/`risks`/`plan` |
| `cites action IDs that do not exist` | 跑过 `rescore` 后 ID 变了 | 按新的 `digest.md` 改 ID |
| 报告标题/修复建议一半是英文 | 中文词条 key 对不上 | 跑第 6 节的覆盖率校验脚本 |
| `.env` 改了没生效 | 直接调 `python -m jevseo` | 用 `bin\layaseo.cmd`，或手动 `set` 环境变量 |

### 9.2 FAQ

**Q：必须先有 Laya 权重才能用吗？**
不用。只有 API key 也能跑（`available_modes: ["jev"]`），等价于上游行为，
只是享受不到省钱和 Engine 列的本地判定部分。反过来只有权重也没问题，会提示用 `offline`。

**Q：为什么中文报告的 visibility 区是空的？**
`--full` 没跑。visibility 需要 DataForSEO 付费数据，缺失时不参与评分（权重自动重分配）。

**Q：`rescore` 会改变 my `narrative.json` 吗？**
不会改文件，但可能让里面的 ID 失效。重算后控制台会提示「Action IDs may have changed; re-check narrative.json」。

**Q：能同时跑多个站吗？**
可以，多个进程各跑各的，输出目录互不冲突。但**不要同时跑两个都调同一个中转站账号的任务**——
账号级配额是共享的，会互相挤。

**Q：`--laya-page-accept` 调到多少合适？**
默认 0.80 是从失败里标定出来的。调到 0.70 会多省一点钱但可能放行错误结论；
调到 0.90 会更准但几乎不省钱。**没有标注数据时，别动它。**

**Q：怎么追溯某条结论是谁给出的？**
看 XLSX 的 `Semantic judgments` 工作表里的 Engine 列，逐条标了 `Jev cloud` / `Laya local` / `Laya (fallback)` / `Rule`。

**Q：PDF 不出来，一定要装吗？**
不一定。Markdown 能直接进 Obsidian/Notion，XLSX 是给客户做行动追踪的。
只有需要打印或发 PDF 给客户时才要 Pango。

### 9.3 PDF 渲染：装 Pango

Windows 上 WeasyPrint 依赖 Pango（C 库，pip 装不了）。

```bat
winget install --id MSYS2.MSYS2 --source winget
"C:\msys64\usr\bin\bash.exe" -lc "pacman-key --init"
"C:\msys64\usr\bin\bash.exe" -lc "pacman -S --needed mingw-w64-x86_64-pango mingw-w64-x86_64-pangoft2"
```

验证（**必须让 Python 启动前就看到 DLL**）：

```bat
set "PATH=C:\msys64\mingw64\bin;%PATH%"
.venv\Scripts\python -c "import weasyprint; print('ok')"
```

`bin\layaseo.cmd` 内置了这个 PATH，所以日常用 cmd 就行。

⚠️ `pacman-key --init` 在 Windows 上可能跑几十分钟且看着像卡死
（`pubring.gpg` 长时间 0 字节）。超过半小时没进展就换路子：
装 [GTK3 Runtime](https://github.com/nickvdyck/weasyprint-win/releases)，
.cmd 脚本也认 `C:\Program Files\GTK3-Runtime Win64\bin`。

---

## 10. 附录

### 10.1 环境变量

| 变量 | 用途 | 谁读 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | Jev 认证 | `jev.py` |
| `JEV_API_BASE` | 覆盖端点（中转站/自部署） | `jev.py` |
| `JEV_MODEL` | 覆盖模型名 | `jev.py` |
| `PAGESPEED_API_KEY` | 提高 PSI 限流额度 | `psi.py` |
| `DATAFORSEO_USERNAME` / `PASSWORD` | `--full` 用 | `dfs.py` |
| `LAYA_MODEL_DIR` | 权重根目录 | `laya.py` |
| `PYTHONPATH` | 用 `python -m jevseo` 时要包含项目根 | — |

### 10.2 一次运行会产出什么

```
<输出目录>\
├── audit.json        所有报告的单一数据源
├── digest.md         给 Agent / 撰写者看的结构化摘要
├── report.md         Markdown（英文）
├── report.zh.md      Markdown（中文，--lang zh/both 时才有）
├── report.xlsx       XLSX，8 张工作表（英文）
├── report.zh.xlsx    中文工作簿
├── report.pdf / .zh.pdf  PDF（需 Pango）
├── charts\*.png      17 张图表（英文）
├── charts\*.zh.png   17 张图表（中文）
└── narrative.json    **你自己写的**，不在默认产出里
```

### 10.3 XLSX 的 8 张工作表

`Summary` · `Actions` · `Findings` · `Pages` · `Semantic judgments` ·
`Overlaps` · `Performance` · `DataForSEO`（`--full` 时出现）

最常用两张：**`Summary`**（分数、行动项状态统计、图表）和 **`Actions`**（可编辑追踪表，带状态下拉）。

### 10.4 术语表

| 术语 | 含义 |
| --- | --- |
| **Laya** | 本地判别式模型。**不生成文本**，对 `state + questions` 输出打分/选择 |
| **Jev** | TypeSafe AI 的云端模型，本项目里的权威裁判 |
| **cascade** | Laya 先判 → 置信度不够升级 Jev 的路由机制 |
| **origin** | 结论来源标记：`rule` / `jev` / `laya` / `laya-fallback` / `code` |
| **band** | `act` = 可直接照做；`review` = 需人工复核 |
| **partial audit** | 语义判断或 PageSpeed 缺一块，报告受限并不可比 |
| **caps** | 分数硬天花板（全站被封 ≤20，无 HTTPS ≤60） |
| **choice / noul / score** | System One 三种原语。**只有 choice 参与采信判定** |
| **ETV** | Estimated Traffic Volume，DataForSEO 的**估算**流量，不是实测 |
| **SERP** | 搜索结果页。`--full` 会看有没有 AI Overview |

### 10.5 命令行总觉得太长？

把常用 invocation 存成 `.bat`。例如 `audit-cn.bat`：

```bat
@echo off
bin\layaseo.cmd run %1 --max-pages 40 --max-depth 3 --jev-pages 15 --no-psi --formats md,xlsx --lang zh
```

用法：`audit-cn.bat https://example.com`

---

<div align="center">

[返回 README](../README.md) ·
[级联实测数据](../references/cascade.md) ·
[narrative 写作合同](../references/narrative.md)

</div>
