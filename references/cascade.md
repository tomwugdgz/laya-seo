# 级联方法论：Laya → Jev → 人工

> 创建：2026-10-04 · 实测基础，非理论推断
> 关联：[[insight-jev-laya-cascade-methodology-2026-09-22]]（金融域实测）、本文件为 **SEO 域** 实测

---

## 一、为什么是级联，不是替换

原始诉求是「把 jev-seo 的 Jev 内核换成 Laya」。实测证明字面替换会产出**高置信度的错误结论**，比不做更糟。

### 关键事实

| 引擎 | 类型 | 成本 | 接口 | page_type 实测 |
| --- | --- | --- | --- | --- |
| **Laya** | 本地非自回归判别模型 | $0，离线 | `predict(state, questions, lang)` | **2/4** |
| **Jev** | 云端生成式 LLM | $0.042/Mtok | `POST /v1/systemone` | 经 A/B 调优 |

两者共用 System One 原语（`choice` / `noul` / `score`），**接口签名相同**，因此级联在工程上可行。

Laya 返回结构与 Jev 几乎逐字段一致，并额外携带 `action.act_probability` 与 `usage`。

## 二、致命发现：错误与高置信度正相关

4 个已知答案的中文 SEO 页面（2026-10-04 实测）：

| 页面 | 期望 | Laya 判断 | 置信度 | 对 |
| --- | --- | --- | --- | --- |
| 价格页 | pricing | pricing | 1.000 | ✓ |
| 文章页 | article_or_guide | **homepage** | **0.962** | ✗ |
| 产品页 | product_or_service | **homepage** | 0.642 | ✗ |
| 联系页 | contact_or_location | contact_or_location | 1.000 | ✓ |

**准确率 2/4。** 文章页被误判为 homepage 时置信度高达 **0.962**，会稳稳越过 `jev.ACT = 0.80` 阈值。

这印证了 [[insight-jev-laya-cascade-methodology-2026-09-22]] 中记录的「自信地错」失败模式：**级联可降「不确定导致的错」，不可降「自信导致的错」**。

Laya 权重训练于金融交易语料，state 上限约 1024 token，套到 SEO 语义上属于跨域迁移，零样本不可信。

### 置信度分布

- `page_type`：均值 **0.901**，但含两个错误的高置信度值
- `intent`：均值 **0.413**，几乎全部落入 review 带

## 三、级联策略

```
Laya 本地先判（$0，毫秒级）
  ↓
整页加权置信度 ≥ 0.80 ?  ── 是 ──> Laya 定案，跳过 Jev
  ↓ 否
Jev 云端权威（$0.042/Mtok）
  ↓
仍不确定 → 标记 needs_review，人工兜底
```

### 三条铁律

1. **单题置信度达标不直接采信。** 必须该页语义题的加权平均同时达标。
   实测证明 Laya 单题 0.962 可能是错的，逐题 AND 无法防住。
2. **所有答案带 `origin` 标记**（`laya` / `jev` / `code`），报告层必须可区分。
3. **阈值可调、不照搬。** `LAYA_Q_ACCEPT=0.95` / `LAYA_PAGE_ACCEPT=0.80`
   均由本项目实测得出，不是通用值。

### 权重调整

`intent` 这类本质模糊的题在加权平均中**权重降为 0.5**。原因是实测其置信度系统性偏低
（均值 0.413），若与 `page_type` 同权会把整页拉低到永远不够阈值。

### 特殊分流

- **页面配对（内容重叠）强制走 Jev**：Laya 在该任务上置信度不可靠，不适用闸门。
- **state 超长（>900 token）直接升级 Jev**：Laya 会截断输入，截断后的得分不可信。

## 四、预期收益与实测表现

`qinlinkeji.com`（中文站，6 页，2026-10-04 实测）：

```
Laya 本地定案 3-4 页，其余升级 Jev —— 省去 50-67% 的 Jev 调用
Jev 10-17 次请求，$0.0043-0.0077
Laya 单次推理约 2 秒（RTX 4050 Laptop，CUDA）
overall 86-88 / 100
```

6 页全部完成判定，`not_judged` 为空。

**尚未验证**：60 页规模下的节省比例。上述数字来自 6 页样本，
`digest.md` 里的 `laya_savings_ratio` 是每次运行的实际值。

## 五、踩过的坑（都是实测逼出来的设计）

### 坑 1：score / noul 的 confidence 不可用于采信

| 原语 | 实测 confidence | 实际判断 |
| --- | --- | --- |
| `choice` | 1.000 / 0.962 / 0.642 | 有区分度，可用 |
| `score` | `helpfulness` 0.075 | 概率峰值却在正确答案，**不可用** |
| `noul` | `answer_first` 0.703 | 而 `noul=0.297` 即判否，**方向相反** |

早期版本三类都纳入加权平均，结果节省率恒为 0%——score 题把整页拉到阈值以下。
现在只有 `choice` 参与采信，score/noul 照常记录进报告供人工参考。

### 坑 2：state 超长会拦掉所有真实页面

最初设 900 token 上限，实测中文真实页面估算 1000–1546 token，**全部被拦**，
节省率恒为 0。两个修法缺一不可：

1. 上限放宽到 2000（Laya 自己会截断，截断风险由 confidence 机制兜住）；
2. 送 Laya 的 state 单独裁剪：正文 1800 字符、outline 12 项、CTA 8 项。

### 坑 3：首页去掉 page_type 后没有可决策的题

原逻辑对首页移除 `page_type`（code 已知答案），剩下 `intent`（实测置信度均值
0.41，权重 0.5）几乎不可能让整页达阈值 → **首页永远升级 Jev**。
现在首页也问 `page_type` 作为决策依据，问完仍由 code 覆盖为确定答案。

### 坑 4：中转站的 422 是账号级配额，不是单次请求限制

| 题目数 | 结果 |
| --- | --- |
| 1 题 | OK |
| 2 题 | OK（input_tokens 32629） |
| 3 题起 | 422 |

关键：`counted_tokens` **恒为 34417，与本次题目数无关**。裁剪正文无效
（甚至题目全删仍报同一数字），说明限额来自账号累计配额。
因此：2 题一批串行、批次间隔 1.1 秒、页面并发降到 2、失败退回 Laya 兜底。

官方 TypeSafe 端点无此限制，换回官方 key 应调大 `DEFAULT_MAX_QUESTIONS`。

### 坑 5：Jev 端点与模型名需可配置

原代码硬编码 `https://api.typesafe.ai/v1/systemone` + `jev-latest`，
换中转站会 401。现在支持 `JEV_API_BASE` / `JEV_MODEL` 环境变量或 `.env`。

## 六、局限（必须随报告一起披露）

1. **零样本跨域**：Laya 未在 SEO 语料上微调。当前 `min_confidence` 类校准文件
   （`calibration.json`）是金融域 91 对样本训练的，**不适用于 SEO**。
2. **未做 SEO 域微调**：PA_Agent 已有微调闭环（收集标注 → 补标签 → 训练），
   若要真正提升 Laya 在 SEO 域的可用性，需复用该闭环，需 ≥500 条/类样本。
3. **配对判断与关键词判断仍完全依赖 Jev**，离线模式（`--cascade offline`）下不可用。
4. **PDF 依赖系统 Pango**，未安装时只能出 md 与 xlsx。

## 七、相关文件

| 文件 | 作用 |
| --- | --- |
| `jevseo/laya.py` | Laya 引擎封装（离线守卫、权重校验、单例加载） |
| `jevseo/cascade.py` | 级联编排（阈值、加权置信度、升级判定、账本） |
| `jevseo/jev.py` | 端点可配置、2 题一批串行、422 退避 |
| `jevseo/cli.py` | `judge_cascade()` / `_judge_laya_only()` / `_shrink_for_laya()` |
| `jevseo/score.py` | `_engine_label()` 报告口径如实标注引擎来源 |
| `tests/test_cascade.py` | 55 个离线用例，覆盖上述全部决策逻辑 |
