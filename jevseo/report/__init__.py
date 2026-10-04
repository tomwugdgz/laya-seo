"""Build report.pdf, report.xlsx and report.md from one audit.json (and optional narrative.json).

All three exports read the same view model, so a number cannot differ between them.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from urllib.parse import urlparse

from jevseo import i18n
from jevseo.report import charts

PRIORITY_TEXT = {"P1": "Fix first", "P2": "Plan next", "P3": "When convenient"}
EFFORT_TEXT = {1: "Hours", 2: "About a day", 3: "Several days", 4: "A project"}
JEV_COLUMNS = [("helpfulness", "helpful"), ("specificity", "specific"), ("trust", "trust"), ("citable", "citable"), ("answer_first", "answer 1st"), ("title_fit", "title"), ("meta_fit", "meta"), ("clear_next_step", "next step")]
NARRATIVE_KEYS = {"executive_summary", "strengths", "risks", "plan"}

#: 评分口径说明的中文版。键是 score.py 写入 notes 的键。
_ZH_NOTES = {
    "crawl": "仅规则",
    "onpage": "规则 + 引擎判断",
    "content": "70% 语义判断（有用性、具体性、可信度），30% 规则",
    "links": "仅规则",
    "structured": "仅规则",
    "ai": "70% 语义判断（可引用性、开头给结论、主体清晰度），30% 规则；属编辑经验，Google 明确表示其 AI 功能无需特殊优化",
    "performance": "50% Lighthouse 移动端 + 50% 抓取观测",
    "security": "仅规则",
    "visibility": "未评估：加 --full 启用 DataForSEO",
    "not_assessed_content": "未评估：无语义判断",
    "not_assessed_ai": "仅规则：无语义判断",
    "rules_only_ai": "仅规则：无语义判断",
    "rules_only_visibility": "未评估：加 --full 启用 DataForSEO",
}

#: 评分封顶说明的中文版
_ZH_CAPS = {
    "Capped at 60: the site is not reliably served over HTTPS": "封顶 60 分：站点未稳定通过 HTTPS 提供服务",
    "Capped at 60: PageSpeed Insights unavailable": "封顶 60 分：PageSpeed Insights 不可用",
    "Capped at 60: too many pages failed to fetch": "封顶 60 分：过多页面抓取失败",
    "Capped at 60: crawl budget or time budget hit": "封顶 60 分：触达抓取预算或时间预算",
}

#: partial 标记的中文版。键是 score.py 写入的完整英文句子。
_ZH_PARTIAL = {
    "no semantic judgments available, so content quality was not assessed":
        "无语义判断可用，内容质量未评估",
    "PageSpeed Insights unavailable, so performance used crawl timings only":
        "PageSpeed Insights 不可用，性能仅用抓取计时估算",
    "semantic judgments came from the local Laya discriminative model, which scored 2/4 on "
    "a known-answer page-type check; treat content and AI readiness as provisional":
        "语义判断来自本地 Laya 判别式模型（已知答案的页面类型测试只答对 2/4），"
        "内容与 AI 就绪度评分仅为暂定值",
}




def short(url: str, site: str = "") -> str:
    p = urlparse(url)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    host = p.netloc.removeprefix("www.")
    return path if not site or host == site else f"{host}{path}"


def load_narrative(folder: Path, data: dict) -> dict:
    path = folder / "narrative.json"
    ids = {a["action_id"] for a in data["actions"]}
    if path.is_file():
        n = json.loads(path.read_text())
        missing = NARRATIVE_KEYS - set(n)
        if missing:
            raise SystemExit(f"narrative.json is missing {sorted(missing)}")
        text = json.dumps(n)
        unknown = sorted(set(re.findall(r"JEV-\d{3}", text)) - ids)
        if unknown:
            raise SystemExit(f"narrative.json cites action IDs that do not exist: {unknown}")
        n.setdefault("author", "Claude, from the audit evidence")
        n["automatic"] = False
        n["unverified_numbers"] = unverified_numbers(text, data)
        n["effort_mismatches"] = effort_mismatches(n, data)
        return n
    return auto_narrative(data)


def effort_mismatches(n: dict, data: dict) -> list[str]:
    """Plan items that state an effort band different from every action they cite."""
    effort = {a["action_id"]: EFFORT_TEXT[a["effort"]].lower() for a in data["actions"]}
    bad = []
    for block in n.get("plan", []):
        for item in block.get("items", []):
            ids = re.findall(r"JEV-\d{3}", item)
            stated = re.search(r"\((hours|about a day|several days|a project)\)\s*$", item.strip(), re.I)
            if ids and stated and stated.group(1).lower() not in {effort.get(i) for i in ids}:
                bad.append(f"{'/'.join(ids)} says '{stated.group(1)}' but the action table says '{', '.join(effort.get(i, '?') for i in ids)}'")
    return bad


def unverified_numbers(text: str, data: dict) -> list[str]:
    """Numbers in the narrative that match nothing in the audit, allowing rounding and ms to seconds."""
    text = re.sub(r"JEV-\d{3}", "", text)
    text = re.sub(r"(https?://|/|@)[\w@./%-]*", " ", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}(?:T[\d:.+-]+)?", " ", text)  # ISO dates and timestamps  # digits inside URLs, paths and handles are not claims
    known: set[float] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            known.add(float(v))
        elif isinstance(v, str):
            known.update(float(x) for x in re.findall(r"\d+(?:\.\d+)?", v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
            for k in v:
                walk(k if isinstance(k, str) else None)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    # Only citable facts count; per-page probabilities are too numerous to prove anything.
    sc = data["scores"]
    walk([sc["overall"], list(sc["categories"].values()), sc["weights"]])
    walk([[a["impact"], a["count"], a["evidence"], a["title"]] for a in data["actions"]])
    for a in (data["jev"].get("site") or {}).values():
        walk([a["value"], a.get("confidence")])
    walk({k: v for k, v in (data["jev"].get("ledger") or {}).items() if k != "errors"})
    for r in (data.get("performance") or {}).get("runs", []):
        walk([r.get("scores"), [m["p75"] for f in (r.get("field_url"), r.get("field_origin")) if f for m in f["metrics"].values()]])
    walk([[p.get("word_count"), p.get("inlinks"), p.get("depth")] for p in data["pages"]])
    walk([data["site"]["sitemaps"]["total_urls"], data["site"]["requests"], len(data["site"]["robots"]["ai_bots"]), data["site"]["probes"]["not_found_status"], data["site"]["probes"]["host_variant"]["status"]])
    home = next((p for p in data["pages"] if p.get("url") == data["site"]["final_url"]), {})
    walk([home.get("title"), home.get("h1"), home.get("meta_description")])
    x = data.get("dataforseo") or {}
    if x.get("available"):
        walk([x.get("overview"), x.get("backlinks"), x.get("referring_domains"), x.get("competitors"), x.get("ranked_total")])
        walk([[k.get("volume"), k.get("position"), k.get("difficulty")] for k in (x.get("ranked") or []) + (x.get("opportunities") or [])])
        walk([[sp.get("own_position")] for sp in x.get("serps") or []] + [(x.get("mentions") or {}).get("total"), x["ledger"].get("cost_usd"), x["ledger"].get("requests")])
    for a in (data["jev"].get("keywords") or {}).values():
        if a:
            walk([a["relevance"]["value"], a["relevance"].get("confidence")])
    known.update({float(len(data["actions"])), float(len(data["pages"])), float(sum(1 for p in data["pages"] if p.get("kind") == "page" and p.get("status") == 200))})
    loose = set()
    for k in known:
        for scale in (1, 100, 0.001):
            for digits in (0, 1, 2):
                loose.add(round(k * scale, digits))
    bad = []
    for tok in re.findall(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.,])\d+(?:\.\d+)?", text):
        v = float(tok.replace(",", ""))
        if v <= 10 and "." not in tok:
            continue  # small counts are too common to check mechanically
        if v not in known and v not in loose:
            bad.append(tok)
    return sorted(set(bad))


def lower(name: str) -> str:
    """Lower-case an area name for running text, keeping acronyms such as AI."""
    return " ".join(w if w.isupper() else w.lower() for w in name.split())


def auto_narrative(d: dict) -> dict:
    """Evidence-only fallback used when no lead-agent narrative exists.

    Renders in the active language (see jevseo.i18n). Chinese is generated
    from the same template rather than translated afterwards, so the numbers
    and action IDs are identical in both versions by construction.
    """
    s = d["scores"]
    cats = {c: v for c, v in s["categories"].items() if v is not None}
    best = sorted(cats, key=lambda c: -cats[c])[:3]
    worst = sorted(cats, key=lambda c: cats[c])[:3]
    acts = d["actions"]
    p1 = [a for a in acts if a["priority"] == "P1"]
    quick = [a for a in acts if a["quick_win"]]
    names = s["category_names"]
    # 中文模式下区域名已在 localize_vm 里换过；这里只取首句主体
    item = lambda a: f"{a['action_id']} {a['title']}"  # noqa: E731

    if i18n.is_zh():
        summary = (
            f"{d['site']['domain']} 在 {len(cats)} 个已评分区域中拿到 {s['overall']} 分（等级 {s['grade']}）。"
            f"最强的是{'、'.join(names[c] for c in best)}；最弱的是{'、'.join(names[c] for c in worst)}。"
            f"本次审计共产出 {len(acts)} 个行动项，其中 {len(p1)} 个标记为优先修，{len(quick)} 个为快速见效项。"
        )
        return {
            "executive_summary": [summary],
            "strengths": [f"{names[c]} 得分 {cats[c]}。" for c in best],
            # evidence 是运行时拼出来的事实串（含规则名、数字、URL）。
            # 逐句翻译它容易把数字或代码改错，因此中文版保留原文，
            # 只把开头加上「证据：」标记，读者知道这段是技术证据而非正文。
            "risks": [f"{a['action_id']}：{a['title']}〔证据〕{a['evidence']}"
                      for a in (p1 or acts)[:4]],
            "plan": [
                {"horizon": "本周", "items": [item(a) for a in (quick or acts)[:4]]},
                {"horizon": "本月", "items": [item(a) for a in acts if a["priority"] in ("P1", "P2") and a not in quick][:5]},
                {"horizon": "本季度", "items": [item(a) for a in acts if a["priority"] == "P3"][:5]},
            ],
            "author": "自动摘要（未撰写人工叙述）",
            "automatic": True,
        }

    summary = (
        f"{d['site']['domain']} scores {s['overall']} out of 100 (grade {s['grade']}) across {len(cats)} scored areas. "
        f"The strongest areas are {', '.join(lower(names[c]) for c in best)}; the weakest are {', '.join(lower(names[c]) for c in worst)}. "
        f"The audit produced {len(acts)} actions, {len(p1)} of them marked fix first and {len(quick)} quick wins."
    )
    return {
        "executive_summary": [summary],
        "strengths": [f"{names[c]} scores {cats[c]}." for c in best],
        "risks": [f"{a['action_id']}: {a['title']} ({a['evidence']})" for a in (p1 or acts)[:4]],
        "plan": [
            {"horizon": "This week", "items": [item(a) for a in (quick or acts)[:4]]},
            {"horizon": "This month", "items": [item(a) for a in acts if a["priority"] in ("P1", "P2") and a not in quick][:5]},
            {"horizon": "This quarter", "items": [item(a) for a in acts if a["priority"] == "P3"][:5]},
        ],
        "author": "Automatic summary (no lead-agent narrative was written)",
        "automatic": True,
    }


def view_model(d: dict, folder: Path) -> dict:
    site = d["site"]
    domain = site["domain"]
    pages = [p for p in d["pages"] if p.get("kind") == "page" and p.get("status") == 200 and "word_count" in p]
    jp = d["jev"].get("pages") or {}
    acts = d["actions"]
    for a in acts:
        a["priority_text"] = PRIORITY_TEXT[a["priority"]]
        a["effort_text"] = EFFORT_TEXT[a["effort"]]
        a["short_urls"] = [short(u, domain) for u in a["urls"][:6]]
        a["by"] = {"jev": "Jev judged", "dataforseo": "DataForSEO"}.get(a["origin"], "rule")
        a["by_class"] = {"jev": "tag-jev", "dataforseo": "tag-dfs"}.get(a["origin"], "tag-rule")

    status_counts = Counter(str(p.get("status") or "error") for p in d["pages"] if p.get("kind") != "redirect")
    redirects = sum(1 for p in d["pages"] if p.get("kind") == "redirect")
    depth_counts = Counter(p.get("depth") if p.get("depth", 99) < 99 else "not linked" for p in pages)
    types = Counter(a["page_type"]["value"] for a in jp.values() if a)
    intents = Counter(a["intent"]["value"] for a in jp.values() if a)
    page_actions = Counter(a["action"]["value"] for a in jp.values() if a)

    # Jev heatmap: most important pages first
    ranked = sorted((u for u in jp if jp[u]), key=lambda u: -jp[u]["importance"]["value"])[:18]
    matrix = [[jp[u][k]["value"] if k in jp[u] else None for k, _ in JEV_COLUMNS] for u in ranked]
    conf_rows = []
    for key, label in [("page_type", "page type"), ("intent", "intent"), ("importance", "importance"), ("action", "action")] + JEV_COLUMNS + [("h1_fit", "h1")]:
        answers = [a[key] for a in jp.values() if a and key in a]
        if answers:
            decisive = sum(1 for x in answers if x["band"] in ("act", "yes", "no"))
            conf_rows.append((label, decisive, len(answers) - decisive))

    perf = d.get("performance") or {}
    runs = [r for r in perf.get("runs", []) if "error" not in r]
    home_mobile = next((r for r in runs if r["url"] == site["final_url"] and r["strategy"] == "mobile"), None)
    home_desktop = next((r for r in runs if r["url"] == site["final_url"] and r["strategy"] == "desktop"), None)
    field = (home_mobile or {}).get("field_url") or (home_mobile or {}).get("field_origin")

    cs = charts.ChartSet(folder / "charts", lang=i18n.get_lang())
    s = d["scores"]
    charts.gauge(cs, s["overall"], s["grade"], bool(s.get("partial")))
    charts.category_bars(cs, s, s["category_names"])
    sev = Counter(a["severity"] for a in acts)
    charts.donut(cs, "severity", [(k, sev.get(k, 0)) for k in ("critical", "high", "medium", "low")], [charts.STATUS[k] for k in ("critical", "high", "medium", "low") if sev.get(k)], "actions")
    charts.severity_by_category(cs, acts, s["category_names"])
    charts.impact_effort(cs, acts)
    charts.donut(cs, "page_types", types.most_common(), center="pages judged")
    charts.donut(cs, "intents", intents.most_common(), center="pages judged")
    charts.donut(cs, "page_actions", page_actions.most_common(), center="Jev verdicts")
    charts.bars(cs, "status", list(status_counts), list(status_counts.values()) , "HTTP status", highlight={"200"})
    dk = sorted(depth_counts, key=lambda k: 99 if k == "not linked" else k)
    charts.bars(cs, "depth", [str(k) for k in dk], [depth_counts[k] for k in dk], "clicks from homepage")
    edges = [(0, 150, "<150"), (150, 300, "150+"), (300, 600, "300+"), (600, 1000, "600+"), (1000, 2000, "1k+"), (2000, 10**9, "2k+")]
    charts.bars(cs, "words", [e[2] for e in edges], [sum(1 for p in pages if e[0] <= p["word_count"] < e[1]) for e in edges], "words of main content", highlight={"150+", "300+", "600+", "1k+", "2k+"})
    charts.histogram(cs, "title_len", [len(p["title"]) for p in pages if p.get("title")], list(range(0, 121, 10)), 65, "title length (characters)")
    charts.heatmap(cs, [short(u, domain)[:42] for u in ranked], [label for _, label in JEV_COLUMNS], matrix)
    charts.confidence_bars(cs, conf_rows)
    charts.lighthouse(cs, home_mobile, home_desktop)
    charts.cwv_bullets(cs, field)

    urls = {p["url"] for p in pages}
    nodes = [{"url": p["url"], "label": short(p["url"], domain), "depth": p.get("depth"), "importance": (jp.get(p["url"]) or {}).get("importance", {}).get("value"),
              "type": (jp.get(p["url"]) or {}).get("page_type", {}).get("value")} for p in pages]
    edges = sorted({(p["url"], l["url"]) for p in pages for l in p.get("links_internal", []) if l["url"] in urls})
    charts.site_map(cs, nodes, edges, site["final_url"])
    discovered = set(site["sitemaps"]["urls"]) | {l["url"] for p in d["pages"] for l in p.get("links_internal", [])} | {p["url"] for p in d["pages"]}
    indexable_n = sum(1 for p in pages if "noindex" not in f"{p.get('meta_robots') or ''} {p.get('x_robots') or ''}" and (not p.get("canonical") or p["canonical"] == p["url"]))
    charts.funnel(cs, [("URLs discovered", len(discovered)), ("URLs crawled", len(d["pages"])), ("HTML pages (200)", len(pages)), ("Indexable", indexable_n), ("Judged by Jev", sum(1 for a in jp.values() if a))])
    invest = [{"label": short(u, domain), "importance": a["importance"]["value"], "quality": mean([a[k]["value"] for k in ("helpfulness", "specificity", "trust") if k in a])} for u, a in jp.items() if a]
    charts.invest_matrix(cs, invest)

    # Full mode: DataForSEO views, with Jev relevance and page mapping attached
    x = d.get("dataforseo") if (d.get("dataforseo") or {}).get("available") else None
    kj = d["jev"].get("keywords") or {}
    dfs_vm = None
    if x:
        from jevseo.dfs import norm_kw

        def kjv(kw, key):
            a = kj.get(kw) or {}
            return (a.get(key) or {}).get("value")

        ranked_rows = [k | {"relevance": kjv(k["keyword"], "relevance"), "page": short(k.get("url") or "", domain)} for k in (x.get("ranked") or [])[:25]]
        opp_actions = {a["id"]: a for a in d["findings"] if a["id"] in ("dfs_existing_page", "dfs_new_page")}
        opp_rows = []
        for fid, f in opp_actions.items():
            for k in f["detail"].get("keywords", []):
                opp_rows.append(k | {"relevance": kjv(k["keyword"], "relevance"), "new_page": fid == "dfs_new_page", "target": "new page" if fid == "dfs_new_page" else short(k.get("page_url") or "", domain)})
        from jevseo.score import opportunity_key

        opp_rows.sort(key=opportunity_key, reverse=True)
        charts.positions(cs, x.get("overview"))
        charts.referring_domains(cs, x.get("referring_domains") or [], domain)
        charts.opportunities(cs, opp_rows)
        ment = x.get("mentions") or {}
        plat = Counter(m.get("platform") or "unknown" for m in ment.get("items") or [])
        charts.donut(cs, "mention_platforms", plat.most_common(), center="sampled mentions")
        dfs_vm = {
            "overview": x.get("overview") or {}, "backlinks": x.get("backlinks") or {}, "ranked": ranked_rows, "ranked_total": x.get("ranked_total"),
            "opportunities": opp_rows[:15], "n_opportunities": len(opp_rows), "serps": x.get("serps") or [], "competitors": x.get("competitors") or [],
            "referring_domains": x.get("referring_domains") or [], "mentions": ment, "ledger": x["ledger"], "reused_from": x.get("reused_from"),
            "location_code": x["location_code"], "language_code": x["language_code"],
        }

    page_rows = []
    for p in sorted(pages, key=lambda p: (p.get("depth", 99), p["url"])):
        j = jp.get(p["url"]) or {}
        page_rows.append({
            "url": p["url"], "short": short(p["url"], domain), "status": p["status"], "depth": p.get("depth"), "title": p.get("title"), "title_len": len(p.get("title") or ""),
            "meta_len": len(p.get("meta_description") or ""), "h1": (p.get("h1") or [""])[0], "h1_count": len(p.get("h1") or []), "words": p["word_count"],
            "inlinks": p.get("inlinks", 0), "outlinks": len(p.get("links_internal", [])), "images": p["images"]["total"], "missing_alt": p["images"]["missing_alt"],
            "schema": ", ".join(p.get("schema_types") or []), "canonical": p.get("canonical"), "indexable": "noindex" not in f"{p.get('meta_robots') or ''} {p.get('x_robots') or ''}", "in_sitemap": p.get("in_sitemap"),
            "ttfb": p.get("ttfb_ms"), "kb": round((p.get("bytes") or 0) / 1024), "rendered": p.get("rendered"),
            "page_type": j.get("page_type", {}).get("value"), "intent": j.get("intent", {}).get("value"), "importance": j.get("importance", {}).get("value"), "action": j.get("action", {}).get("value"),
            **{k: j.get(k, {}).get("value") for k, _ in JEV_COLUMNS},
        })

    ledger = d["jev"].get("ledger") or {}
    jev_site = d["jev"].get("site")
    site_cards = []
    if jev_site:
        labels = {"business_model": "What kind of business is this?", "value_prop": "How clear is the offer on the homepage?", "entity_clarity": "Does the homepage say who, what and where?", "topical_focus": "How focused is the site's topic set?", "serves_local_area": "Does it serve a specific local area?"}
        for key, question in labels.items():
            a = jev_site[key]
            card = {"key": key, "question": question, "type": a["type"], "band": a["band"]}
            if a["type"] == "choice":
                top = sorted(a["probabilities"].items(), key=lambda kv: -kv[1])[:3]
                card |= {"answer": a["value"].replace("_", " "), "confidence": a["confidence"], "bars": [(k.replace("_", " "), v) for k, v in top]}
            elif a["type"] == "score":
                levels = ((d["jev"].get("questions") or {}).get("site") or {}).get(key, {}).get("criteria") or []
                name = lambda k: levels[int(k)][:34] if int(k) < len(levels) else f"level {k}"  # noqa: E731
                card |= {"answer": f"{a['value']:.2f}", "confidence": a["confidence"], "bars": [(name(k), v) for k, v in sorted(a["probabilities"].items(), key=lambda kv: int(kv[0]))]}
            else:
                card |= {"answer": f"P(yes) {a['value']:.2f}", "bars": [("yes", a["value"]), ("no", 1 - a["value"])]}
            site_cards.append(card)

    robots = site["robots"]
    return {
        "d": d,
        "domain": domain,
        "site": site,
        "scores": s,
        "actions": acts,
        "top_actions": acts[:10],
        "quick_wins": [a for a in acts if a["quick_win"]][:8],
        "pages": page_rows,
        "n_pages": len(pages),
        "n_fetched": len(d["pages"]),
        "redirects": redirects,
        "status_counts": dict(status_counts),
        "charts": cs,
        "narrative": load_narrative(folder, d),
        "ledger": ledger,
        "site_cards": site_cards,
        "dfs": dfs_vm,
        "jev_available": any(jp.values()),
        "not_judged": [u for u, a in jp.items() if a is None],
        "p1_count": sum(1 for a in acts if a["priority"] == "P1"),
        "invest_pages": sorted(
            [{"short": short(u, domain), "importance": a["importance"]["value"], "quality": mean([a[k]["value"] for k in ("helpfulness", "specificity", "trust") if k in a]), "action": a["action"]["value"]}
             for u, a in jp.items() if a and a["importance"]["value"] >= 0.5 and mean([a[k]["value"] for k in ("helpfulness", "specificity", "trust") if k in a]) < 0.5],
            key=lambda r: -r["importance"],
        )[:8],
        "jev_pairs": sorted((p for p in d["jev"].get("pairs", []) if p.get("judgment")), key=lambda p: -p["judgment"]["value"]),
        "questions": d["jev"].get("questions") or {},
        "perf_runs": runs,
        "perf_errors": [r for r in perf.get("runs", []) if "error" in r],
        "field": field,
        "home_mobile": home_mobile,
        "ai_bots": robots["ai_bots"],
        "search_bots": robots["search_bots"],
        "findings_by_cat": {c: [a for a in acts if a["category"] == c] for c in s["category_names"]},
        "passed": d["passed_rules"],
        "sev_counts": dict(sev),
        "avg_words": round(mean([p["word_count"] for p in pages])) if pages else 0,
        "decisive_share": round(100 * sum(r[1] for r in conf_rows) / max(1, sum(r[1] + r[2] for r in conf_rows))),
        "n_judgments": sum(r[1] + r[2] for r in conf_rows) + (5 if jev_site else 0) + len([p for p in d["jev"].get("pairs", []) if p.get("judgment")]),
    }


def localize_vm(vm: dict) -> dict:
    """把 view model 里的用户可见英文字段换成当前语言。

    在渲染层翻译而不是在采集层翻译，这样英文版与中文版共享同一份
    audit.json —— 一次审计，两份报告，零额外网络请求、零额外 API 花费。

    只翻「给人看的」字段：URL、数字、原始判定值一律不动。
    """
    if not i18n.is_zh():
        return vm

    # action / finding 的标题与修法。规则 ID 存在 `id` 字段（不是 rule_id）。
    for a in vm.get("actions", []):
        rule_id = a.get("id") or a.get("rule_id")
        if rule_id:
            a["title"] = i18n.rule(rule_id, "title", a.get("title"))
            a["fix"] = i18n.rule(rule_id, "fix", a.get("fix"))
        a["severity"] = i18n.severity(a.get("severity"), a.get("severity"))
        a["by"] = i18n.ORIGIN_ZH.get(a.get("by"), a.get("by"))
        if a.get("priority_text"):
            a["priority_text"] = i18n.PRIORITY_ZH.get(a["priority"], a["priority_text"]) \
                if a["priority"] in i18n.PRIORITY_ZH else a["priority_text"]
        if a.get("effort_text"):
            a["effort_text"] = i18n.EFFORT_ZH.get(a["effort"], a["effort_text"])

    # 区域名与评分口径说明
    s = vm["scores"]
    s["category_names"] = {k: i18n.category(k, v) for k, v in s["category_names"].items()}
    s["notes"] = {k: _ZH_NOTES.get(k, v) for k, v in s["notes"].items()}
    s["caps"] = [_ZH_CAPS.get(c, c) for c in s.get("caps") or []]
    s["partial"] = [_ZH_PARTIAL.get(p, p) for p in s.get("partial") or []]

    # 站点级判断卡片
    for c in vm.get("site_cards", []):
        c["question"] = i18n.VOCAB_ZH.get(c.get("question"), c.get("question"))
        if c.get("answer") in i18n.VOCAB_ZH:
            c["answer"] = i18n.VOCAB_ZH[c["answer"]]

    # 页面清单里的枚举值
    for p in vm.get("pages", []):
        for f in ("page_type", "intent", "action"):
            v = p.get(f)
            if isinstance(v, str):
                p[f] = i18n.VOCAB_ZH.get(v, v).replace("_", " ") if v in i18n.VOCAB_ZH else v
    for r in vm.get("invest_pages", []):
        v = r.get("action")
        if isinstance(v, str):
            r["action"] = i18n.VOCAB_ZH.get(v, v.replace("_", " "))

    # 自动摘要按当前语言重新生成：它的文案是模板拼出来的，
    # 直接生成中文比事后逐句翻译更可靠，数字与 action_id 天然一致。
    if vm.get("narrative", {}).get("automatic"):
        vm["narrative"] = auto_narrative(vm["d"])

    return vm


def build(folder: Path, formats: list[str], log=print) -> dict:
    """渲染报告。

    默认输出英文。传 --lang both（或 formats 里含 "both"）时，同一次审计
    同时产出 report.md / report.zh.md（xlsx 因工作表名冲突，仍为单份英文版
    加中文列，见 xlsx.py）。
    """
    data = json.loads((folder / "audit.json").read_text())

    def render(tag: str, lang: str) -> dict:
        i18n.set_lang(lang)
        # 图表要按当前语言重画：图例文字在渲染时已烧进 PNG，
        # 复用英文那一份会让中文版出现中英混排的图。
        vm = localize_vm(view_model(data, folder))
        suffix = "" if tag == "" else f".{tag}"
        out = {}
        if "pdf" in formats:
            from jevseo.report.pdf import write_pdf
            log(f"rendering PDF ({lang})")
            out["pdf" + suffix] = write_pdf(vm, folder / f"report{suffix}.pdf")
        if "xlsx" in formats:
            from jevseo.report.xlsx import write_xlsx
            log(f"writing workbook ({lang})")
            out["xlsx" + suffix] = write_xlsx(vm, folder / f"report{suffix}.xlsx")
        if "md" in formats:
            from jevseo.report.md import write_md
            out["md" + suffix] = write_md(vm, folder / f"report{suffix}.md")
        return out

    written: dict = {}
    lang = getattr(formats, "lang", None) or "en"
    if lang == "both":
        written.update(render("", "en"))
        written.update(render("zh", "zh"))
    else:
        written.update(render("", lang))

    i18n.set_lang("en")  # 复位，避免污染同进程内后续调用
    log("building charts")
    for k, v in written.items():
        log(f"{k}: {v}")
    # 用英文视图做叙述一致性检查（与语言无关）
    i18n.set_lang("en")
    vm = view_model(data, folder)
    for issue in vm["narrative"].get("effort_mismatches") or []:
        log(f"WARNING narrative effort mismatch: {issue}")
    if vm["narrative"].get("unverified_numbers"):
        log("WARNING narrative.json contains numbers not found in the audit: " + ", ".join(vm["narrative"]["unverified_numbers"]) + ". Check them against digest.md and re-render.")
    return written
