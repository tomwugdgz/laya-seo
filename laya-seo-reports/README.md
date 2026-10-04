# 示例报告

`duckwolf-cn/` 是一次真实审计的完整产出，用作样例。

## 这是什么

对 `https://duckwolf.cn`（Discuz 站点）跑的一次完整审计：

```bat
layaseo run https://duckwolf.cn --max-pages 12 --max-depth 3 --no-psi --formats md,xlsx --lang both
```

**结果**：78/100（B 级），30 个行动项，抓取 13 个 URL（7 个 HTML 页面 + 6 个跳转）。
评分分区：content 57 / ai 71 / onpage 76 / crawl 81 / links 91 / structured 91 /
performance 93 / security 94（visibility 未评分，需要 `--full` 的 DataForSEO 数据）。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `report.md` | 英文版报告（Markdown，含 Mermaid 饼图与图表引用） |
| `report.zh.md` | **中文版报告** —— 与英文版来自同一次审计，数字完全一致 |
| `report.xlsx` | 英文工作簿：8 张表，含可编辑的行动项追踪与下拉状态 |
| `report.zh.xlsx` | 中文工作簿：表头汉化，含 Engine 列可逐条溯源判断来源 |
| `audit.json` | 原始审计数据（≈ 660KB），所有报告都由它渲染 |
| `digest.md` | 给写报告的人看的结构化摘要 |
| `charts/*.png` | 17 张图表（英文） |
| `charts/*.zh.png` | 17 张图表（中文，图例文字已汉化） |

## 值得注意的字段

**Engine 列**（在 `Semantic judgments` 工作表里）标出每条判断出自哪个引擎：

- `Jev cloud` —— 云端 Jev 判定
- `Laya local` —— 本地 Laya 判别式模型定案
- `Laya (fallback)` —— Jev 因供应商配额被拒时的兜底
- `code` —— 代码判定（如「这是首页」）

`--lang both` 的一次真实运行里，5 页全部升级 Jev、Laya 定案 0 页
（Discuz 页面普遍偏薄，Laya 置信度不足）。这正是级联设计要防的情况：
**本地模型不够确信时，就交给权威模型。**

这次运行还真实命中了供应商配额问题：Jev 15 次请求中 **4 次被 422
`token_budget_exceeded` 拒绝**，被拒的页面退回 Laya 兜底，
所以 `Engine` 列最终是 `Laya (fallback) 3 / Jev cloud 2`。
这恰好演示了兜底路径的价值——**宁可给标注过的低置信结果，也不留空**。
`audit.json` 的 `jev.ledger.jev_api.errors` 里有完整的 422 原文。

## 为什么没有 PDF

这台机器缺 WeasyPrint 依赖的 Pango 运行时（系统级 C 库，pip 装不了）。
Markdown 与 XLSX 不依赖它，功能完整。详见 README「PDF 渲染」一节。

## 报告里的数据

报告内容是对 `duckwolf.cn` 的公开可见信息做分析得出的：
页面标题、内链结构、HTTP 状态码、robots.txt 内容等。
不包含任何账号、密钥或后台数据。
