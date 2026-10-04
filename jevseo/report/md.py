"""Markdown report: readable anywhere, with chart images and Mermaid pies for GitHub and Obsidian.

Renders in English or Chinese from the same audit — see jevseo.i18n. Set the
language with i18n.set_lang() before calling write_md.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from jevseo import i18n
from jevseo.i18n import T, is_zh


def cell(v) -> str:
    return str("" if v is None else v).replace("|", "\\|").replace("\n", " ")


def label(v) -> str:
    """下划线枚举转可读文本；中文模式下经词表翻译。"""
    key = (v or "").replace("_", " ")
    if is_zh():
        return T(key.replace(" ", "_"), key)
    return key


# 引擎标签的中文名
def _origin(name: str) -> str:
    return i18n.ORIGIN_ZH.get(name, name) if is_zh() else name


WIDTH = {"gauge": 220, "severity": 320, "page_types": 360, "intents": 360, "positions": 380, "referring_domains": 380}


def img(vm: dict, name: str, alt: str) -> str:
    """HTML image tags so GitHub and Obsidian show charts at a readable size."""
    p = vm["charts"].png.get(name)
    return f'<img src="charts/{p.name}" alt="{alt}" width="{WIDTH.get(name, 640)}">\n' if p else ""


def pie(title: str, counts: dict) -> str:
    if not counts:
        return ""
    body = "\n".join(f'    "{k.replace("_", " ")}" : {v}' for k, v in counts.items() if v)
    return f"```mermaid\npie showData title {title}\n{body}\n```\n"


def write_md(vm: dict, path: Path) -> Path:
    d, s, n = vm["d"], vm["scores"], vm["narrative"]
    z = is_zh()
    L = []
    add = L.append
    add(f"# {T('audit_title', 'Laya SEO audit')}: {vm['domain']}\n")
    cas_head = (d['jev'].get('cascade') or {})
    if cas_head.get('mode') == 'cascade':
        split = (f" · {cas_head.get('accepted_by_laya', 0)} 页由本地 Laya 判定，"
                 f"{cas_head.get('jev_pages', 0)} 页由 Jev 判定") if z else (
                f" · {cas_head.get('accepted_by_laya', 0)} pages judged locally by Laya, "
                f"{cas_head.get('jev_pages', 0)} by Jev")
    else:
        split = ""
    cost = (vm['ledger'].get('cost_usd') or 0)
    head = (f"{T('audited_on', 'Audited')} {d['run']['finished_at']} · "
            f"{vm['n_fetched']} {T('urls_crawled', 'URLs crawled')} · "
            f"{vm['n_pages']} {T('html_pages', 'HTML pages')} · "
            f"{vm['n_judgments']} {T('semantic_judgments', 'semantic judgments')}"
            f"{split} · {T('engine_cost', 'engine cost')} ${cost:.4f}\n")
    add(head)
    add(f"**{T('overall_score', 'Overall score')}: {s['overall']}{T('of_100', '/100')} "
        f"({T('grade', 'grade')} {s['grade']})**"
        + (f". {'; '.join(s['caps'])}" if s["caps"] else "") + "\n")
    if s.get("partial"):
        add(f"> **{T('partial_audit', 'Partial audit')}:** {'; '.join(s['partial'])}. "
            f"{T('partial_note', 'The overall score covers only the areas that were assessed.')}\n")
    add(img(vm, "gauge", T("overall", "Overall score")))
    add(f"| {T('area', 'Area')} | {T('score', 'Score')} | {T('weight', 'Weight')} | {T('how_scored', 'How it is scored')} |\n|---|---:|---:|---|")
    for c, name in s["category_names"].items():
        v = s["categories"][c]
        shown = i18n.category(c, name) if z else name
        add(f"| {shown} | {v if v is not None else T('na', 'n/a')} | {s['weights'][c]} | {s['notes'][c]} |")
    add("")
    add(img(vm, "categories", T("by_area", "Score by area")))

    h_exec = T("executive_summary", "Executive summary")
    h_how = T("how_this_audit", "How this audit was made")
    h_pri = T("priority_actions", "Priority actions")
    h_crawl = T("what_crawl_found", "What the crawl found")
    h_eng = T("how_engines_read", "How the engines read the site")
    toc = [h_exec, h_how, h_pri] + ([T("search_visibility", "Search visibility (DataForSEO)")] if vm.get("dfs") else []) + [h_crawl] + ([h_eng] if vm["jev_available"] else []) + [T("findings_by_area", "Findings by area"), T("robots_access", "Robots access"), T("page_inventory", "Page inventory"), T("method_and_limits", "Method and limits")]
    anchor = lambda h: "#" + "".join(c for c in h.lower().replace(" ", "-") if c.isalnum() or c == "-")  # noqa: E731
    add("**目录 / Contents:** " + " · ".join(f"[{h}]({anchor(h)})" for h in toc) + "\n")

    add(f"## {h_exec}\n")
    for para in n["executive_summary"]:
        add(para + "\n")
    add(f"**{T('strongest', 'What is working')}**\n" if z else "**What is working**\n")
    add("\n".join(f"- {x}" for x in n["strengths"]) + "\n")
    add(f"**{T('weakest', 'What is holding the site back')}**\n" if z else "**What is holding the site back**\n")
    add("\n".join(f"- {x}" for x in n["risks"]) + "\n")
    add(f"### {T('method', 'Plan') if z else 'Plan'}\n")
    for block in n["plan"]:
        add(f"**{block['horizon']}**\n")
        add("\n".join(f"- {x}" for x in block["items"]) + "\n")
    if n.get("closing"):
        add(n["closing"] + "\n")
    add(f"_{'撰写' if z else 'Written by'}: {n['author']}._\n")

    add(f"## {h_how}\n")
    if z:
        add("源码负责发现，代码负责计算，引擎负责判读，助手负责撰写。代码负责抓取、计数与打分；"
            "语义引擎对「含义」回答有类型的窄问题，并保留概率。缺失的数据就显示为缺失。\n")
    else:
        add("A source finds, code decides, Jev judges, Claude writes. Code crawls, counts and scores. "
            "Jev (TypeSafe's System One model) answers narrow typed questions about meaning, with "
            "probabilities. Missing data is shown as missing.\n")
    add("```mermaid\nflowchart LR\n  A[Crawl<br/>" + f"{vm['n_fetched']} URLs" + "] --> B[Rules<br/>"
        + f"{sum(1 for f in d['findings'] if f['origin'] == 'rule')} findings" + "] --> C["
        + ("引擎判读<br/>" if z else "Jev judges<br/>") + f"{vm['n_judgments']} judgments" + "] --> D[PageSpeed<br/>"
        + f"{len(vm['perf_runs'])} runs" + "] --> E[" + ("打分与撰写<br/>" if z else "Score and write<br/>")
        + f"{len(vm['actions'])} actions" + "]\n  style C fill:#d45bb6,color:#fff\n```\n")

    add(f"## {h_pri}\n")
    add(img(vm, "impact_effort", T("impact_effort", "Impact versus effort")))
    add(f"| ID | {T('action', 'Action')} | {T('priority', 'Priority')} | {T('impact', 'Impact')} | "
        f"{T('effort', 'Effort')} | {T('pages_unit', 'Pages')} | {T('check', 'By')} | "
        f"{T('needs_review', 'Verify')} |\n|---|---|---|---:|---|---:|---|---:|")
    for a in vm["actions"]:
        qw = ("（快速见效）" if z else " (quick win)") if a['quick_win'] else ""
        add(f"| {a['action_id']} | {cell(a['title'])}{qw} | {a['priority']} {a['priority_text']} | "
            f"{a['impact']} | {a['effort_text']} | {a['count']} | {_origin(a['by'])} | {a['needs_review'] or ''} |")
    add("")
    add(pie(T("severity", "Actions by severity"), {k: vm["sev_counts"].get(k, 0) for k in ("critical", "high", "medium", "low")}))
    add(img(vm, "severity_by_category", T("severity_by_category", "Actions by area and severity")))

    x = vm.get("dfs")
    if x:
        ov, bl = x["overview"], x["backlinks"]
        add(f"## {T('search_visibility', 'Search visibility (DataForSEO)')}\n")
        if z:
            add(f"地区 {x['location_code']}，语言 {x['language_code']}。流量（ETV）是 DataForSEO 的估算值，不是实测访问。\n")
        else:
            add(f"Location {x['location_code']}, language {x['language_code']}. Traffic (ETV) is DataForSEO's estimate, not measured visits.\n")
        add(f"| {T('ranking_keywords', 'Ranking keywords')} | {T('est_visits', 'Est. monthly visits')} | "
            f"{T('referring_domains', 'Referring domains')} | {T('backlinks', 'Backlinks')} | "
            f"{T('ai_mentions', 'AI answer mentions')} |\n|---:|---:|---:|---:|---:|\n"
            f"| {ov.get('count')} | {round(ov['etv']) if ov.get('etv') is not None else T('na','n/a')} | "
            f"{bl.get('referring_domains')} | {bl.get('backlinks')} | {(x['mentions'] or {}).get('total')} |\n")
        add(img(vm, "positions", T("positions", "Ranking keywords by position")))
        add(img(vm, "referring_domains", T("referring_domains", "Referring domains compared")))
        add(f"| {T('keyword','Keyword')} | {T('position','Position')} | {T('searches_month','Searches/mo')} | "
            f"{T('ranking_url','Ranking page')} | {T('relevance','Jev relevance')} |\n|---|---:|---:|---|---:|")
        for k in x["ranked"][:20]:
            add(f"| {cell(k['keyword'])} | {k.get('position')} | {k.get('volume')} | {k['page']} | "
                f"{'' if k['relevance'] is None else format(k['relevance'], '.2f')} |")
        add(f"\n### {T('opportunities','Keywords worth winning')}\n")
        add(img(vm, "opportunities", T("opportunities", "Keyword opportunities")))
        add(f"| {T('keyword','Keyword')} | {T('searches_month','Searches/mo')} | {T('difficulty','Difficulty')} | "
            f"{T('search_intent','Intent')} | {T('relevance','Jev relevance')} | {T('page_to_own','Page to own it')} |\n"
            f"|---|---:|---:|---|---:|---|")
        for k in x["opportunities"]:
            rel = "" if k.get("relevance") is None else f"{k['relevance']:.2f}"
            add(f"| {cell(k['keyword'])} | {k.get('volume')} | "
                f"{k.get('difficulty') if k.get('difficulty') is not None else T('na','n/a')} | "
                f"{cell(k.get('intent'))} | {rel} | {k['target']} |")
        add("")
        if x["serps"]:
            add(f"| {T('keyword','Keyword')} | {T('own_position','Site position')} | "
                f"{T('ai_overview','AI Overview')} | {T('top_competitors','Top 3')} |\n|---|---:|---|---|")
            for sp in x["serps"]:
                if sp["ai_overview"]:
                    aio = ("是，引用本站" if z else "yes, cites the site") if sp["ai_overview_cites_site"] \
                        else ("是，未引用本站" if z else "yes, site not cited")
                else:
                    aio = "无" if z else "none"
                add(f"| {cell(sp['keyword'])} | {sp['own_position'] or ('未进前十' if z else 'not in top 10')} | {aio} | "
                    f"{', '.join(t['domain'] for t in sp['top'][:3])} |")
            add("")

    add(f"## {h_crawl}\n")
    add(img(vm, "funnel", T("from_discovered", "From discovered URLs to judged pages")))
    add(img(vm, "site_map", T("site_map", "Site structure by click depth")))

    if vm["jev_available"]:
        add(f"## {h_eng}\n")
        cas = d["jev"].get("cascade") or {}
        if cas.get("mode") == "cascade" or cas.get("accepted_by_laya") is not None:
            if z:
                add(f"语义判断来自级联：**{cas.get('accepted_by_laya', 0)} 页由本地 Laya 判定**"
                    f"（运行在本机 GPU 上的判别式 System One 模型），"
                    f"**{cas.get('jev_pages', 0)} 页升级到云端 Jev**"
                    + (f" —— 省去 {cas.get('laya_savings_ratio', 0):.0%} 的 Jev 调用"
                       if cas.get("laya_savings_ratio") else "")
                    + "。下方图表或表格中标「Jev」的地方，请读作「Semantic judgments 工作表 Engine 列所指的引擎」。\n")
            else:
                add(f"Semantic judgments came from a cascade: **{cas.get('accepted_by_laya', 0)} pages decided locally by "
                    f"Laya** (a discriminative System One model running on your GPU), "
                    f"**{cas.get('jev_pages', 0)} pages escalated to Jev** in the cloud"
                    + (f" — {cas.get('laya_savings_ratio', 0):.0%} of Jev calls avoided"
                       if cas.get("laya_savings_ratio") else "")
                    + ". Where a chart or table below says \"Jev\", read it as *the engine named in the "
                      "Engine column* of the Semantic judgments sheet.\n")
        elif cas.get("mode") == "laya-only":
            add("> **语义判断全部来自本地 Laya 模型。**它是判别式模型，在已知答案的页面类型测试中"
                "只答对 2/4，且不生成文本。请把内容与 AI 就绪度评分视为暂定，动手前务必人工核对。\n"
                if z else
                "> **Semantic judgments came from the local Laya model only.** It is a discriminative model "
                "that scored 2 out of 4 on a known-answer page-type check, and it does not generate text. "
                "Treat content and AI-readiness scores as provisional and verify anything you act on.\n")
        for c in vm["site_cards"]:
            conf = (f"，置信度 {c['confidence']:.2f}" if z else f", confidence {c['confidence']:.2f}") if "confidence" in c else ""
            flag = "" if c["band"] in ("act", "yes", "no") else (" （需复核）" if z else " _(verify)_")
            q = label(c["question"])
            a = c["answer"]
            if z:
                a = i18n.VOCAB_ZH.get(a, a)
            add(f"- **{q}** {a}{conf}{flag}")
        add("")
        jp = d["jev"]["pages"]
        add(pie(T("page_types", "Page types"), dict(Counter(label(a["page_type"]["value"]) for a in jp.values() if a).most_common())))
        add(pie(T("intents", "Search intent"), dict(Counter(label(a["intent"]["value"]) for a in jp.values() if a).most_common())))
        add(img(vm, "jev_heatmap", T("page_quality_heatmap", "Jev page quality heatmap")))
        add(img(vm, "jev_confidence", T("how_sure", "How sure the engine was")))
        add(f"### {T('where_to_invest', 'Where to invest')}\n")
        add(img(vm, "invest", T("importance_vs_quality", "Importance versus judged quality")))
        if vm["invest_pages"]:
            add(f"| {T('important_but_weak_col','Important but weak')} | {T('importance','Importance')} | "
                f"{T('quality','Quality')} | {T('suggests','Jev suggests')} |\n|---|---:|---:|---|")
            for p in vm["invest_pages"]:
                add(f"| {p['short']} | {p['importance']:.2f} | {p['quality']:.2f} | {cell(label(p['action']))} |")
            add("")
        if vm["jev_pairs"]:
            add(f"**{T('competing_pages','Pages that may compete for the same searches')}**\n")
            add(f"| {T('page_a','Page A')} | {T('page_b','Page B')} | {T('title_overlap','Title overlap')} | "
                f"P({T('compete','compete')}) |\n|---|---|---:|---:|")
            for p in vm["jev_pairs"][:20]:
                add(f"| {p['a']} | {p['b']} | {p['title_overlap']} | {p['judgment']['value']:.2f} |")
            add("")

    add(f"## {T('findings_by_area','Findings by area')}\n")
    for c, name in s["category_names"].items():
        acts = vm["findings_by_cat"][c]
        if not acts:
            continue
        shown = i18n.category(c, name) if z else name
        add(f"### {shown} ({s['categories'][c] if s['categories'][c] is not None else T('na','n/a')})\n")
        if c == "performance":
            add(img(vm, "lighthouse", T("lighthouse", "Lighthouse scores")))
            add(img(vm, "cwv", T("core_web_vitals", "Core Web Vitals field data")))
        for a in acts:
            tags = [a["priority"], i18n.severity(a["severity"], a["severity"]) if z else a["severity"], _origin(a["by"])]
            if a["needs_review"]:
                tags.append(f"{a['needs_review']} {T('to_verify','to verify')}" if z else f"{a['needs_review']} to verify")
            if a["heuristic"]:
                tags.append(T("heuristic", "heuristic") if z else "heuristic")
            add(f"**{a['action_id']} · {a['title']}** `{'` `'.join(tags)}`\n")
            add(f"- {T('evidence','Evidence')}: {a['count']} {T('affected','affected')} · {a['evidence']}")
            add(f"- {T('fix','Fix')}: {a['fix']} ([{T('source','source')}]({a['source']}))")
            add(f"- {T('affected_urls','URLs')}: " + ", ".join(a["urls"][:8])
                + (f" {T('and_more','and')} {a['count'] - 8} {T('more','more')}" if a["count"] > 8 else ""))
            add("")

    add(f"## {T('robots_access','Robots access')}\n")
    add(f"| {T('user_agent','User agent')} | {T('access','Access')} |\n|---|---|")
    for b, ok in {**vm["search_bots"], **vm["ai_bots"]}.items():
        add(f"| {b} | {(('允许' if ok else '屏蔽') if z else ('allowed' if ok else 'blocked'))} |")
    add("")

    add(f"## {T('page_inventory','Page inventory')}\n")
    add(f"| {T('page','Page')} | {T('depth','Depth')} | {T('words','Words')} | {T('inlinks','Inlinks')} | "
        f"{T('page_type','Type (Jev)')} | {T('search_intent','Intent (Jev)')} | {T('importance','Importance')} | "
        f"{T('action','Action (Jev)')} |\n|---|---:|---:|---:|---|---|---:|---|")
    for p in vm["pages"]:
        imp = f"{p['importance']:.2f}" if p["importance"] is not None else ""
        add(f"| {p['url']} | {p['depth'] if p['depth'] != 99 else ''} | {p['words']} | {p['inlinks']} | "
            f"{label(p['page_type'])} | {label(p['intent'])} | {imp} | {label(p['action'])} |")
    add("")

    add(f"## {T('method_and_limits','Method and limits')}\n")
    if z:
        add("- 区域得分：100 减去每条发现的扣分（严重 25、高 12、中 6、低 2）×（0.5 + 0.5 × 受影响页面占比）。"
            "内容与 AI 就绪度按 70% 语义判断 + 30% 规则混合。性能按 50% Lighthouse 移动端 + 50% 抓取观测混合。")
        add("- 总分：已评分区域的加权平均；未评分区域被排除，而不是记为 0。")
        add("- 影响：严重度权重 ×（0.6 + 0.4 × 触达率）×（0.6 + 0.8 × 受影响页面的最高语义重要度），归一到 100。")
        add("- 引擎判断在置信度 0.80（Choice、Score）或 P(yes) ≥ 0.80 / ≤ 0.20（Noul）时才视为确定，其余标记为待复核。")
    else:
        add("- Area score: 100 minus, per finding, severity amount (critical 25, high 12, medium 6, low 2) × (0.5 + 0.5 × share of pages affected). Content and AI readiness blend 70% semantic judgment with 30% rules. Performance blends 50% Lighthouse mobile with 50% crawl observations.")
        add("- Overall: weighted mean of scored areas; unscored areas are excluded, never zero.")
        add("- Impact: severity weight × (0.6 + 0.4 × reach) × (0.6 + 0.8 × highest semantic importance of affected pages), scaled to 100.")
        add("- Engine answers are decisive at confidence 0.80 (Choice, Score) or P(yes) at least 0.80 or at most 0.20 (Noul). Others are flagged to verify.")
    lg = vm["ledger"]
    api = lg.get("jev_api") or {}
    cas_n = lg.get("accepted_by_laya", 0) or 0
    cas_j = lg.get("jev_pages", 0) or 0
    if lg.get("cascade") == "laya-first" and (cas_n or cas_j):
        add(f"- 引擎：Laya 本地定案 {cas_n} 页（RTX GPU，约 {lg.get('laya_avg_ms') or 0} ms/次），"
            f"Jev 云端判定 {cas_j} 页（{api.get('requests', 0)} 次请求，{(api.get('input_tokens') or 0)} 输入 token，"
            f"{api.get('failed', 0)} 次失败，${(api.get('cost_usd') or 0):.4f}）。\n" if z else
            f"- Engines: Laya decided {cas_n} pages locally (~{lg.get('laya_avg_ms') or 0} ms per call on GPU); "
            f"Jev answered {cas_j} pages in the cloud ({api.get('requests', 0)} requests, "
            f"{api.get('input_tokens') or 0} input tokens, {api.get('failed', 0)} failed, "
            f"${(api.get('cost_usd') or 0):.4f}).")
    else:
        add(f"- Jev：模型 {api.get('model_returned') or lg.get('model_returned') or 'n/a'}，"
            f"{api.get('requests', lg.get('requests', 0))} 次请求，"
            f"{(api.get('input_tokens') or lg.get('input_tokens') or 0)} 输入 token，"
            f"{api.get('failed', lg.get('failed', 0))} 次失败，"
            f"${(lg.get('cost_usd') or 0):.4f}。\n" if z else
            f"- Jev: model {api.get('model_returned') or lg.get('model_returned') or 'n/a'}, "
            f"{api.get('requests', lg.get('requests', 0))} requests, "
            f"{(api.get('input_tokens') or lg.get('input_tokens') or 0)} input tokens, "
            f"{api.get('failed', lg.get('failed', 0))} failed, cost ${(lg.get('cost_usd') or 0):.4f}.")
    if vm.get("dfs"):
        x = vm["dfs"]
        add(f"- DataForSEO：{x['ledger']['requests']} 次请求，${x['ledger']['cost_usd']:.4f}"
            + (f"；数据复用于 {x['reused_from']} 的采集结果" if x.get("reused_from") else "")
            + "。排名、搜索量、难度与流量（ETV）均为 DataForSEO 估算。未使用 Search Console 或分析工具数据。\n" if z else
            f"- DataForSEO: {x['ledger']['requests']} requests, ${x['ledger']['cost_usd']:.4f}"
            + (f"; data reused from the collection at {x['reused_from']}" if x.get("reused_from") else "")
            + ". Rankings, volumes, difficulty and traffic (ETV) are DataForSEO estimates. "
              "No Search Console or analytics data was used.")
    else:
        add("- 未使用 Search Console、分析工具、外链或关键词数据（加 --full 可启用 DataForSEO）。\n" if z else
            "- No Search Console, analytics, backlink or keyword data was used (run with --full for DataForSEO).")
    add("- 得分用于排定工作顺序，不预测排名或流量。\n" if z else
        "- Scores rank work; they do not predict rankings or traffic.")
    add(f"\n_{'由 laya-seo 生成' if z else 'Generated by laya-seo'} {d['tool']['version']}._\n")
    path.write_text("\n".join(L))
    return path
