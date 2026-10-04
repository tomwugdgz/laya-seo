"""jevseo command line.

  audit  <url>        crawl, check, measure, judge, score -> audit.json + digest.md
  render <dir>        audit.json (+ narrative.json) -> report.pdf, report.xlsx, report.md
  run    <url>        audit then render in one step
  rescore <dir>       rebuild findings and scores from a saved audit (no network, no spend)
  doctor              check dependencies and credentials without printing secrets
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from jevseo import VERSION
from jevseo.cascade import validate_local as _cascade_validate_local
from jevseo.jev import PAGE_TEXT_CHARS_LOCAL


def laya_default_model_dir() -> str:
    """Laya 权重默认位置。与 PA_Agent 保持同一份，避免重复占用 600MB。"""
    from jevseo.laya import DEFAULT_MODEL_DIR

    return str(DEFAULT_MODEL_DIR)


def _shrink_for_laya(state: dict, questions: dict) -> tuple[dict, dict]:
    """把送入 Laya 的 state 裁剪到本地模型的上下文预算。

    Jev 是云端模型，上下文长无妨；Laya 的 state 上限约 1024 token。
    实测中文真实页面在 6000 字符下估算 1000-1546 token，会被判定超长而全部
    升级 Jev，级联节省率恒为 0。裁剪后 Laya 才真正参与判断。

    裁剪策略：正文保留开头 PAGE_TEXT_CHARS_LOCAL 字符（页面开头信息密度最高，
    且 opening 与 H2 结构已单独保留），outline 与 calls_to_action 各保留前若干项。
    """
    page = state.get("page")
    if not isinstance(page, dict):
        return state, questions
    short = dict(page)
    text = short.get("text") or ""
    short["text"] = text[:PAGE_TEXT_CHARS_LOCAL]
    short["text_truncated"] = len(text) > PAGE_TEXT_CHARS_LOCAL
    if isinstance(short.get("outline"), list):
        short["outline"] = short["outline"][:12]
    if isinstance(short.get("calls_to_action"), list):
        short["calls_to_action"] = short["calls_to_action"][:8]
    shrunk = dict(state)
    shrunk["page"] = short
    return shrunk, questions

STAGES = ["Crawl", "Rule checks", "DataForSEO", "Laya+Jev judgments", "PageSpeed", "Scoring", "Render"]
T0 = time.monotonic()


def log(msg: str) -> None:
    """Progress line with elapsed time, flushed immediately so callers see it live."""
    e = int(time.monotonic() - T0)
    print(f"[laya-seo {e // 60:02d}:{e % 60:02d}] {msg}", file=sys.stderr, flush=True)


def stage(n: int, detail: str = "") -> None:
    log(f"== {n}/{len(STAGES)} {STAGES[n - 1]}" + (f": {detail}" if detail else ""))


class _FormatList(list):
    """带 lang 属性的格式列表。

    内置 list 不允许挂属性，而 build() 需要 lang。继承 list 保持与
    既有调用方（测试、脚本）的兼容性——它们照旧可以传普通 list，
    build 会用 getattr 取默认值 'en'。
    """

    lang = "en"


def default_out(url: str) -> Path:
    host = urlparse(url if "://" in url else "https://" + url).netloc.lower().removeprefix("www.")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    return Path.cwd() / "laya-seo-reports" / f"{re.sub(r'[^a-z0-9.-]', '-', host)}-{stamp}"


def judge_cascade(site, pages, args, log=print, dfs=None) -> dict:
    """级联判分：Laya 本地闸门 → Jev 云端权威。

    三种模式（--cascade）：
      laya-first（默认） Laya 先判，整页置信度达标则本地定案，否则升级 Jev。
                       本地零成本，这是唯一真正省 Jev 费用的路径。
      jev-first        先问 Jev，Jev 全部明确则不再跑 Laya。仅供对照调试，不省费用。
      offline          完全不调 Jev，只用 Laya。报告必须标注为代理判断。
      --no-jev         跳过全部语义判断（等价于原项目的 --no-jev）。

    返回结构与原 jev.judge() 完全一致，因此 score / report / xlsx / md
    四层无需改动即可继续工作——这是「输出不变」的实现基础。
    """
    from concurrent.futures import ThreadPoolExecutor

    from jevseo import jev as jev_mod
    from jevseo.cascade import Cascade, summarize

    pages = list(pages)
    empty = {"available": False, "site": None, "pages": {}, "pairs": [], "ledger": {}, "questions": {}}

    # offline 模式：不建 Cascade（它会构造 Jev），直接走 Laya 单引擎
    if args.cascade == "offline":
        return _judge_laya_only(site, pages, args, log=log, dfs=dfs)

    cas = Cascade(
        laya_model_dir=args.laya_model_dir,
        laya_subfolder=args.laya_subfolder,
        laya_device=args.laya_device,
        laya_enabled=not args.no_laya,
        cascade=args.cascade,
        q_accept=args.laya_q_accept,
        page_accept=args.laya_page_accept,
        log=log,
    )

    if not cas.jev.available and not cas.probe():
        log("Laya 与 Jev 均不可用：语义判断整体标记为未评估（partial audit）。")
        empty["skipped"] = "no Laya weights and no TYPESAFE_API_KEY"
        empty["ledger"] = cas.ledger
        return empty

    has_laya = cas.probe()
    if not cas.jev.available:
        log("TYPESAFE_API_KEY 未配置：级联退化为 Laya 单引擎，报告将标注为本地代理判断。")

    home = next((p for p in pages if p["url"] == site["final_url"]), pages[0] if pages else None)
    if home is None:
        return empty

    out = {
        "available": True,
        "cascade": summarize(cas.ledger),
        "site": None,
        "pages": {},
        "pairs": [],
        "ledger": cas.ledger,
        "questions": {},
    }

    site_q = jev_mod.site_questions()
    out["site"] = (cas._run_jev(jev_mod.site_state(home, pages), site_q)
                   if cas.jev.available else cas._run_laya(jev_mod.site_state(home, pages), site_q))
    site_ctx = {
        "name": home.get("title"),
        "homepage_summary": (home.get("meta_description") or "") + " " + (home.get("text_excerpt") or "")[:600],
    }
    out["questions"] = {"site": site_q, "page_example": jev_mod.page_questions(home)}

    done: dict[str, str] = {}
    step = max(1, -(-len(pages) // 5))

    def one(p):
        qs = jev_mod.page_questions(p)
        is_home = p["url"] == home["url"]
        # 首页仍问 page_type：级联需要一个可靠的 choice 类题做决策依据
        # （去掉后首页只剩 intent，实测置信度均值 0.41，几乎必然升级 Jev）。
        # 问完之后仍由 code 用确定答案覆盖它 —— 模型不参与「这是不是首页」的判断。
        ans, engine = cas.judge_page(jev_mod.page_state(p, site_ctx), qs, state_builder=_shrink_for_laya)
        if ans is not None and is_home:
            ans["page_type"] = {"type": "choice", "value": "homepage",
                                "probabilities": {"homepage": 1.0}, "confidence": 1.0,
                                "band": "act", "source": "code", "origin": "code"}
        return p["url"], ans, engine

    # 并发降到 2：Jev 侧的限额来自账号级累计配额（中转站实测 3 题起 422，
    # counted_tokens 与本次题目数无关），多页面同时送审会互相挤占配额。
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, (url, ans, engine) in enumerate(pool.map(one, pages), 1):
            out["pages"][url] = ans
            done[url] = engine
            if i % step == 0 or i == len(pages):
                log(f"级联：{i}/{len(pages)} 页已判"
                    f"（Laya 定案 {cas.ledger['accepted_by_laya']}，"
                    f"升级 Jev {cas.ledger['promoted']}，Jev ${cas.jev.cost():.4f}）")

    out["not_judged"] = [u for u, a in out["pages"].items() if a is None]
    out["page_engine"] = done

    # 页面配对（内容重叠）必须由 Jev 判断：Laya 实测在该任务上置信度不可靠
    pairs = jev_mod.overlap_candidates(pages)
    if pairs and cas.jev.available:
        log(f"级联：{len(pairs)} 组页面配对交由 Jev 判断（该项不用 Laya）")
        for start in range(0, len(pairs), 10):
            chunk = pairs[start : start + 10]
            state = {f"pair_{i}": {"page_a": jev_mod.pair_summary(a), "page_b": jev_mod.pair_summary(b)}
                     for i, (a, b, _) in enumerate(chunk)}
            ans = cas._run_jev(state, {f"pair_{i}": jev_mod.pair_question(f"pair_{i}") for i in range(len(chunk))})
            for i, (a, b, jac) in enumerate(chunk):
                out["pairs"].append({"a": a["url"], "b": b["url"], "title_overlap": jac,
                                     "judgment": ans[f"pair_{i}"] if ans else None})
    elif pairs:
        log("级联：跳过页面配对判断（需 TYPESAFE_API_KEY）")

    cas.ledger["cost_usd"] = cas.jev.cost()
    cas.ledger["usd_per_mtok"] = jev_mod.USD_PER_MTOK
    # 把 Jev 自身的账本并进来，否则失败原因与请求数会丢失
    cas.ledger["jev_api"] = dict(cas.jev.ledger)
    cas.ledger["jev_max_questions_per_request"] = cas.jev.max_questions
    out["cascade"] = summarize(cas.ledger)
    s = out["cascade"]
    api = cas.ledger["jev_api"]
    log(f"级联完成：{s.get('note') or s.get('note')}；Jev {api['requests']} 次请求、"
        f"{api['failed']} 次失败，${cas.jev.cost():.4f}")
    return out


def _judge_laya_only(site, pages, args, log=print, dfs=None) -> dict:
    """offline 模式：只用 Laya，产出与 jev.judge 同构的结果。

    每页答案一律标记 origin=laya，且报告层会写明这是本地判别模型代理判断。
    这是刻意的诚实设计：宁可标注不确定性，也不伪装成生成式语义理解。
    """
    from jevseo import jev as jev_mod
    from jevseo.laya import LayaEngine

    log("offline 模式：仅用 Laya 本地判别模型，语义判断为代理结果，不等同于生成式理解。")
    engine = LayaEngine.get(model_dir=args.laya_model_dir, subfolder=args.laya_subfolder,
                            device=args.laya_device)
    try:
        engine.ensure_loaded(log=log)
    except Exception as err:  # noqa: BLE001
        log(f"Laya 不可用：{err}")
        out = {"available": False, "skipped": f"laya unavailable: {err}",
               "site": None, "pages": {}, "pairs": [], "ledger": {}, "questions": {}}
        return out

    pages = list(pages)
    home = next((p for p in pages if p["url"] == site["final_url"]), pages[0] if pages else None)
    if home is None:
        return {"available": False, "skipped": "no pages", "site": None, "pages": {},
                "pairs": [], "ledger": {}, "questions": {}}

    out = {"available": True, "cascade": {"mode": "laya-only",
                                           "note": "纯 Laya 本地判别模型，语义判断为代理结果，可信度受限"},
           "site": None, "pages": {}, "pairs": [], "questions": {},
           "ledger": {"cascade": "offline", "laya_pages": 0, "jev_pages": 0}}

    site_q = jev_mod.site_questions()
    raw = engine.ask(jev_mod.site_state(home, pages), site_q, log=log)
    if raw:
        out["site"] = {k: dict(validate_local(q, raw[k])) for k, q in site_q.items() if k in raw}

    site_ctx = {"name": home.get("title"),
                "homepage_summary": (home.get("meta_description") or "") + " "
                                    + (home.get("text_excerpt") or "")[:600]}
    out["questions"] = {"site": site_q, "page_example": jev_mod.page_questions(home)}

    for i, p in enumerate(pages, 1):
        qs = jev_mod.page_questions(p)
        is_home = p["url"] == home["url"]
        # 同级联路径：首页也问 page_type 作为决策依据，随后由 code 覆盖
        raw = engine.ask(*_shrink_for_laya(jev_mod.page_state(p, site_ctx), qs), log=log)
        if raw:
            ans = {k: dict(validate_local(q, raw[k]), origin="laya") for k, q in qs.items() if k in raw}
            if is_home:
                ans["page_type"] = {"type": "choice", "value": "homepage",
                                    "probabilities": {"homepage": 1.0}, "confidence": 1.0,
                                    "band": "act", "source": "code", "origin": "code"}
            out["pages"][p["url"]] = ans
        out["ledger"]["laya_pages"] += 1
        if i % max(1, len(pages) // 5) == 0:
            log(f"Laya：{i}/{len(pages)} 页已判（本地推理，无需 API）")

    out["not_judged"] = [u for u, a in out["pages"].items() if a is None]
    out["page_engine"] = {u: "laya" for u in out["pages"]}
    out["ledger"]["cost_usd"] = 0.0
    return out


# validate_local 已移至 jevseo.cascade，与级联路径共用同一份 Laya 口径。
validate_local = _cascade_validate_local


def audit(args) -> Path:
    from jevseo import checks, crawl, dfs as dfs_mod, jev, psi, score

    out = Path(args.out) if args.out else default_out(args.url)
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    timings = {}

    log(f"Auditing {args.url}: up to {args.max_pages} pages{', full mode with DataForSEO' if args.full else ''}. Typical run {'2 to 5' if args.full else '1 to 4'} minutes; progress follows.")
    stage(1, "robots.txt, sitemaps, then pages")
    t = time.monotonic()
    site = crawl.crawl(args.url, max_pages=args.max_pages, max_depth=args.max_depth, render_mode=args.render, time_budget=args.time_budget, log=log)
    timings["crawl"] = round(time.monotonic() - t, 1)

    stage(2)
    t = time.monotonic()
    findings = checks.run_checks(site)
    timings["checks"] = round(time.monotonic() - t, 1)
    log(f"{len(findings)} rule findings from {len(checks.RULES)} rules")

    pages = [p for p in checks.html_pages(site) if checks.indexable(p) or p["url"] == site["final_url"]]
    pages.sort(key=lambda p: (p.get("depth", 99), -p.get("inlinks", 0)))

    dfs = None
    stage(3, f"location {args.location_code}, language {args.language}, budget ${args.dfs_budget:.2f}" if args.full else "skipped (add --full for rankings, keywords and backlinks)")
    t = time.monotonic()
    if args.full and args.reuse_dfs:
        prev = json.loads((Path(args.reuse_dfs) / "audit.json").read_text())
        if prev["site"]["domain"] != site["domain"] or not prev.get("dataforseo"):
            raise SystemExit(f"--reuse-dfs: {args.reuse_dfs} holds no DataForSEO data for {site['domain']}")
        dfs = prev["dataforseo"] | {"reused_from": prev["run"]["finished_at"]}
        log(f"reusing DataForSEO data collected {prev['run']['finished_at']} (no new spend)")
    elif args.full:
        home = next((p for p in pages if p["url"] == site["final_url"]), {})
        dfs = dfs_mod.collect(site["domain"], home, args.location_code, args.language, args.dfs_budget, log=log)
    timings["dataforseo"] = round(time.monotonic() - t, 1)

    mode = "off" if args.no_jev else args.cascade
    stage(4, "skipped (--no-jev)" if args.no_jev else
                 f"级联 {mode}, {min(len(pages), args.jev_pages)} pages, Jev 预算 ${args.jev_budget:.2f}")
    t = time.monotonic()
    if args.no_jev:
        judged = {"available": False, "skipped": "disabled with --no-jev", "site": None, "pages": {}, "pairs": [], "ledger": {}, "questions": {}}
    else:
        judged = judge_cascade(site, pages[: args.jev_pages], args, log=log, dfs=dfs)
    timings["jev"] = round(time.monotonic() - t, 1)
    findings += score.jev_findings(site, judged) + score.dfs_findings(site, judged, dfs)

    stage(5, "skipped (--no-psi)" if args.no_psi else f"{args.psi_pages} pages x mobile and desktop, about 30 to 60 seconds")
    t = time.monotonic()
    perf = None
    if not args.no_psi:
        ranked = sorted(pages[1:], key=lambda p: -(score.importance_of(p["url"], judged) or 0))
        perf = psi.run([site["final_url"]] + [p["url"] for p in ranked[: args.psi_pages - 1]], log=log)
        findings += perf_findings(perf)
    timings["pagespeed"] = round(time.monotonic() - t, 1)

    stage(6)
    scores = score.score(site, findings, judged, perf, dfs)
    acts = score.actions(findings, judged, len(checks.html_pages(site)))
    data = {
        "schema_version": "1.0",
        "tool": {"name": "laya-seo", "version": VERSION},
        "run": {
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "timings_s": timings,
            "options": {k: v for k, v in vars(args).items() if k not in ("func", "out")},
        },
        "site": {k: v for k, v in site.items() if k != "pages"},
        "pages": site["pages"],
        "findings": findings,
        "passed_rules": checks.passed_rules(findings),
        "jev": judged,
        "performance": perf,
        "dataforseo": dfs,
        "scores": scores,
        "actions": acts,
    }
    (out / "audit.json").write_text(json.dumps(data, indent=1, default=str))
    (out / "digest.md").write_text(digest(data))
    log(f"audit written: {out / 'audit.json'}")
    log(f"score {scores['overall']} ({scores['grade']}{', partial' if scores.get('partial') else ''}), {len(acts)} actions, Jev ${judged.get('ledger', {}).get('cost_usd', 0):.4f}" + (f", DataForSEO ${dfs['ledger']['cost_usd']:.4f}" if dfs else ""))
    return out


def perf_findings(perf: dict | None) -> list[dict]:
    """Findings from PageSpeed results: real-user Core Web Vitals and the Lighthouse lab score."""
    from jevseo import checks

    findings: list[dict] = []
    if not perf:
        return findings
    for run in perf["runs"]:
        field = (run.get("field_url") or run.get("field_origin") or {})
        poor = [m for m, v in field.get("metrics", {}).items() if m in ("LCP", "INP", "CLS") and v["rating"] != "good"]
        if run["strategy"] == "mobile" and poor and not any(f["id"] == "cwv_field" for f in findings):
            findings.append({
                "id": "cwv_field", "origin": "rule", "category": "performance",
                "severity": "high" if any(field["metrics"][m]["rating"] == "poor" for m in poor) else "medium",
                "title": "Core Web Vitals not in the good range for real mobile users",
                "fix": "Work through the PageSpeed opportunities for " + ", ".join(poor) + ", starting with the largest savings.",
                "source": checks.SRC["cwv"], "effort": 3, "heuristic": False, "urls": [run["url"]], "count": 1,
                "evidence": "; ".join(f"{m} p75 {field['metrics'][m]['p75']}{field['metrics'][m]['unit']} ({field['metrics'][m]['rating']})" for m in poor) + (" (origin-level field data)" if not run.get("field_url") else ""),
                "detail": {},
            })
        lab = run.get("scores", {}).get("performance")
        if run["strategy"] == "mobile" and lab is not None and lab < 50 and not any(f["id"] == "lab_performance" for f in findings):
            findings.append({
                "id": "lab_performance", "origin": "rule", "category": "performance", "severity": "medium",
                "title": "Low Lighthouse mobile performance score", "fix": "Reduce render-blocking resources, image weight and JavaScript; see the PageSpeed opportunities.",
                "source": checks.SRC["cwv"], "effort": 3, "heuristic": False, "urls": [run["url"]], "count": 1,
                "evidence": f"Lighthouse mobile performance {lab}/100 (one synthetic load)", "detail": {},
            })
    return findings


def digest(d: dict) -> str:
    """Compact, evidence-only brief for the lead agent writing the narrative."""
    s, j = d["scores"], d["jev"]
    pages = [p for p in d["pages"] if p.get("kind") == "page" and p.get("status") == 200]
    lines = [
        f"# Digest: {d['site']['domain']}",
        f"Audited {d['run']['finished_at']}. Pages fetched: {len(d['pages'])}; HTML pages: {len(pages)}.",
        f"Overall {s['overall']} ({s['grade']}). " + ", ".join(f"{s['category_names'][c]} {v if v is not None else 'n/a'}" for c, v in s["categories"].items()),
        f"Caps: {'; '.join(s['caps']) or 'none'}. Completeness: {s['completeness']}",
        f"PARTIAL AUDIT: {'; '.join(s['partial'])}. Say so in the narrative." if s.get("partial") else "Full assessment: semantic judgment and PageSpeed both available.",
    ]
    # 级联披露：让写报告的人一眼看到哪些结论出自本地模型
    cas = j.get("cascade")
    if cas:
        eng = "Laya 本地判别模型" if cas.get("mode") == "laya-only" else "Laya 本地判别模型 + Jev 云端模型"
        lines.append(f"Semantic engine: {cas.get('note') or eng}.")
        if cas.get("laya_pages") is not None:
            lines.append(
                f"Engine split: Laya decided {cas.get('accepted_by_laya', 0)} pages, "
                f"Jev answered {cas.get('jev_pages', 0)} pages"
                + (f"; Laya averaged {cas['laya_avg_ms']} ms per call on {cas.get('device') or 'unknown device'}."
                   if cas.get("laya_avg_ms") else ".")
            )
            lines.append("MANDATORY in the narrative: state which engine judged which pages, "
                         "and do not present Laya's output as authoritative where the digest marks band=review.")
    if j.get("site"):
        site = j["site"]
        lines.append("Site view (copy these numbers exactly):")
        for key, a in site.items():
            conf = f", confidence {a['confidence']:.2f}" if "confidence" in a else ""
            val = a["value"] if isinstance(a["value"], str) else f"{a['value']:.2f}"
            org = f", engine {a['origin']}" if a.get("origin") else ""
            lines.append(f"- {key}: {val}{conf}, band {a['band']}{org}")
    home = next((p for p in pages if p["url"] == d["site"]["final_url"]), None)
    if home:
        lines.append(f"Homepage: title={home.get('title')!r}; h1={home.get('h1')[:2]!r}; meta={home.get('meta_description')!r}")
    lines.append("\n## Actions (id, priority, impact, effort, count, title, evidence, review flags)")
    for a in d["actions"]:
        lines.append(f"- {a['action_id']} {a['priority']} impact {a['impact']} effort {a['effort']} [{a['origin']}/{a['category']}/{a['severity']}] {a['title']} x{a['count']}: {a['evidence']}" + (f" (needs review: {a['needs_review']})" if a["needs_review"] else ""))
        site_host = urlparse(d["site"]["final_url"]).netloc
        rel = lambda u: (urlparse(u).path or "/") if urlparse(u).netloc == site_host else urlparse(u).netloc + (urlparse(u).path or "/")  # noqa: E731
        lines.append("  URLs: " + ", ".join(rel(u) for u in a["urls"][:8]) + (f" +{a['count'] - 8} more" if a["count"] > 8 else ""))
    robots = d["site"]["robots"]
    lines.append(f"\nRobots: search bots {robots['search_bots']}; AI bots checked ({len(robots['ai_bots'])}): {robots['ai_bots']}")
    lines.append("\n## No issue detected by rule")
    lines.append(", ".join(d["passed_rules"]))
    perf = d.get("performance") or {}
    for r in perf.get("runs", []):
        if "error" in r:
            lines.append(f"- PSI {r['strategy']} {r['url']}: {r['error']}")
        else:
            f = r.get("field_url") or r.get("field_origin") or {}
            level = "URL-level" if r.get("field_url") else "origin-level" if r.get("field_origin") else "no field data"
            metrics = "; ".join(f"{m} {v['p75']}{v['unit']} {v['rating']}" for m, v in f.get("metrics", {}).items()) or "none"
            lines.append(f"- PSI {r['strategy']} {r['url']}: scores {r['scores']}; field ({level}) {metrics}")
    x = d.get("dataforseo")
    if x and x.get("available"):
        ov = x.get("overview") or {}
        kj = j.get("keywords") or {}
        rel = lambda kw: f"{kj[kw]['relevance']['value']:.2f}" if kj.get(kw) else "n/a"  # noqa: E731
        lines.append(f"\n## DataForSEO (location {x['location_code']}, language {x['language_code']}; DataForSEO estimates, not measured traffic)")
        lines.append(f"Ranking keywords: {ov.get('count')}; estimated monthly organic traffic (ETV): {round(ov['etv']) if ov.get('etv') is not None else 'n/a'}; positions: 1: {ov.get('pos_1')}, 2-3: {ov.get('pos_2_3')}, 4-10: {ov.get('pos_4_10')}, 11-20: {ov.get('pos_11_20')}, 21-100: {sum((ov.get(k) or 0) for k in ('pos_21_30','pos_31_40','pos_41_50','pos_51_60','pos_61_70','pos_71_80','pos_81_90','pos_91_100'))}")
        for k in (x.get("ranked") or [])[:15]:
            lines.append(f"- ranks: {k['keyword']} | position {k.get('position')} | {k.get('volume')}/mo | {urlparse(k.get('url') or '').path or '/'} | Jev relevance {rel(k['keyword'])}")
        bl = x.get("backlinks") or {}
        lines.append(f"Backlinks: {bl.get('backlinks')} from {bl.get('referring_domains')} referring domains; broken backlinks {bl.get('broken_backlinks')}; DataForSEO rank {bl.get('rank')}")
        lines.append("Referring domains, site and search competitors: " + ", ".join(f"{r['domain']} {r['referring_domains']}" for r in x.get("referring_domains") or []))
        lines.append("Search competitors (platforms excluded): " + ", ".join(f"{c['domain']} ({c['shared_keywords']} shared)" for c in x.get("competitors") or []))
        for sp in x.get("serps") or []:
            lines.append(f"- SERP {sp['keyword']}: own position {sp['own_position']}; AI Overview {'yes' if sp['ai_overview'] else 'no'}{' (cites site)' if sp['ai_overview_cites_site'] else ''}; top 3: {', '.join(t['domain'] for t in sp['top'][:3])}")
        m = x.get("mentions") or {}
        lines.append(f"AI answer mentions of the domain (LLM Mentions): {m.get('total')} total")
        lines.append(f"DataForSEO ledger: {x['ledger']['requests']} requests, ${x['ledger']['cost_usd']:.4f}, failed {x['ledger']['failed']}, skipped {x['ledger']['skipped_budget']}")
    if j.get("not_judged"):
        lines.append(f"\nNot judged by any engine (failed or budget cap): {len(j['not_judged'])} pages. Their absence of findings is not a pass.")
    if j.get("ledger"):
        lines.append(f"\nJev ledger: {j['ledger']}")
    return "\n".join(lines) + "\n"


def rescore(args) -> None:
    """Rebuild findings, scores, actions and digest from a saved audit, without network or spend."""
    from jevseo import checks, score

    folder = Path(args.dir)
    d = json.loads((folder / "audit.json").read_text())
    site = dict(d["site"], pages=d["pages"])
    findings = checks.run_checks(site) + score.jev_findings(site, d["jev"]) + score.dfs_findings(site, d["jev"], d.get("dataforseo")) + perf_findings(d.get("performance"))
    d["findings"] = findings
    d["passed_rules"] = checks.passed_rules(findings)
    d["scores"] = score.score(site, findings, d["jev"], d.get("performance"), d.get("dataforseo"))
    d["actions"] = score.actions(findings, d["jev"], len(checks.html_pages(site)))
    d["run"]["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (folder / "audit.json").write_text(json.dumps(d, indent=1, default=str))
    (folder / "digest.md").write_text(digest(d))
    log(f"rescored: {d['scores']['overall']} ({d['scores']['grade']}), {len(d['actions'])} actions. Action IDs may have changed; re-check narrative.json.")


def render(args) -> None:
    from jevseo.report import build

    stage(7, args.formats)
    # build() 需要知道语言；用带 lang 属性的列表传递，
    # 避免改动 build 的签名（它还有别的调用方与测试）。
    fmts = _FormatList(args.formats.split(","))
    fmts.lang = getattr(args, "lang", "en")
    build(Path(args.dir), formats=fmts, log=log)


def run(args) -> None:
    args.out = audit(args)
    args.dir = str(args.out)
    render(args)


def doctor(_args) -> None:
    from jevseo.env import secret
    from jevseo.laya import DEFAULT_MODEL_DIR, DEFAULT_SUBFOLDER, doctor as laya_doctor

    report = {"version": VERSION, "python": sys.version.split()[0], "tool": "laya-seo"}
    for mod in ["requests", "bs4", "lxml", "matplotlib", "jinja2", "weasyprint", "openpyxl", "playwright"]:
        try:
            __import__(mod)
            report[mod] = "ok"
        except ImportError as err:
            report[mod] = f"missing ({err.name})"
        except Exception as err:  # noqa: BLE001
            # WeasyPrint 在缺 Pango/GLib 时会以 OSError 炸在 import 期，
            # 不是 ImportError。doctor 的职责是「报告坏掉」，不是「跟着坏掉」。
            report[mod] = f"broken ({type(err).__name__}: {str(err).strip().splitlines()[-1][:160]})"

    # PDF 是否能出，取决于 WeasyPrint 是否真的可用
    report["pdf"] = "available" if report.get("weasyprint") == "ok" else "unavailable: md and xlsx are unaffected"

    # Laya 只探测运行时与权重，不加载 600MB 权重
    lz = laya_doctor()
    report["laya"] = {
        "runtime": lz["runtime"],
        "weights": lz["weights"],
        "device": lz["device"],
        "torch": lz.get("torch"),
        "gpu": lz.get("gpu"),
        "model_dir": lz["model_dir"],
        "reason": lz["reason"],
    }

    report["TYPESAFE_API_KEY"] = "present" if secret("TYPESAFE_API_KEY") else "missing: cascade will run Laya-only and reports will be labelled proxy judgments"
    report["PAGESPEED_API_KEY"] = "present" if secret("PAGESPEED_API_KEY") else "missing: PageSpeed runs unkeyed and may be rate limited"
    report["DATAFORSEO"] = "present (needed only for --full)" if secret("DATAFORSEO_USERNAME") and secret("DATAFORSEO_PASSWORD") else "missing: --full mode unavailable"

    # 明确给出可用模式，避免误判
    modes = []
    if lz["runtime"] == "ok" and lz["weights"] == "ok":
        modes.append("laya")
    if secret("TYPESAFE_API_KEY"):
        modes.append("jev")
    report["available_modes"] = modes
    report["recommended"] = "laya-first" if len(modes) == 2 else ("offline" if modes == ["laya"] else "no semantic judgment")
    print(json.dumps(report, indent=1, ensure_ascii=False))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="layaseo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True)

    def audit_opts(p):
        p.add_argument("url")
        p.add_argument("--out", help="output directory (default ./laya-seo-reports/<domain>-<stamp>)")
        p.add_argument("--max-pages", type=int, default=60)
        p.add_argument("--max-depth", type=int, default=5)
        p.add_argument("--time-budget", type=int, default=600, help="crawl time budget in seconds")
        p.add_argument("--render", choices=["auto", "always", "never"], default="auto")
        p.add_argument("--jev-pages", type=int, default=60, help="maximum pages sent to semantic judgment")
        p.add_argument("--jev-budget", type=float, default=0.25, help="hard Jev spend cap in USD")
        p.add_argument("--no-jev", action="store_true")
        # ── Laya 级联 ──────────────────────────────────────────────────────
        p.add_argument("--cascade", choices=["laya-first", "jev-first", "offline"], default="laya-first",
                       help="laya-first: 本地闸门优先，置信度不足才升级 Jev（省费用，默认）; "
                            "jev-first: 先问 Jev（仅调试对照，不省费用）; "
                            "offline: 完全不调 Jev，仅 Laya 本地判别（报告标注为代理判断）")
        p.add_argument("--no-laya", action="store_true", help="禁用 Laya，等价于纯 Jev 模式")
        p.add_argument("--laya-model-dir", default=None,
                       help="Laya 权重根目录（默认 $LAYA_MODEL_DIR，其次 %%USERPROFILE%%/laya-models/laya）")
        p.add_argument("--laya-subfolder", default="multilingual", help="Laya 权重子目录（空字符串为英文档）")
        p.add_argument("--laya-device", default="auto", help="auto / cpu / cuda")
        p.add_argument("--laya-page-accept", type=float, default=0.80,
                       help="整页 Laya 加权置信度达到此值才本地定案，否则升级 Jev")
        p.add_argument("--laya-q-accept", type=float, default=0.95,
                       help="单题 Laya 置信度参考阈值（记录用，不单独决定采信）")
        p.add_argument("--psi-pages", type=int, default=3, help="pages measured with PageSpeed Insights")
        p.add_argument("--no-psi", action="store_true")
        p.add_argument("--full", action="store_true", help="add DataForSEO rankings, keywords, competitors, backlinks, SERPs and AI mentions (paid per call)")
        p.add_argument("--location-code", type=int, default=2840, help="DataForSEO location code (2840 = United States)")
        p.add_argument("--language", default="en", help="DataForSEO language code")
        p.add_argument("--dfs-budget", type=float, default=1.0, help="hard DataForSEO spend cap in USD")
        p.add_argument("--reuse-dfs", metavar="DIR", help="with --full: reuse DataForSEO data from an earlier audit folder of the same site (no new spend)")

    p = sub.add_parser("audit")
    audit_opts(p)
    p.set_defaults(func=audit)
    p = sub.add_parser("render")
    p.add_argument("dir")
    p.add_argument("--formats", default="pdf,xlsx,md")
    p.add_argument("--lang", choices=["en", "zh", "both"], default="en",
                   help="report language. en: English (default); zh: Chinese; "
                        "both: emit report.md plus report.zh.md from one audit (no extra spend)")
    p.set_defaults(func=render)
    p = sub.add_parser("run")
    audit_opts(p)
    p.add_argument("--formats", default="pdf,xlsx,md")
    p.add_argument("--lang", choices=["en", "zh", "both"], default="en",
                   help="report language. en: English (default); zh: Chinese; "
                        "both: emit report.md plus report.zh.md from one audit (no extra spend)")
    p.set_defaults(func=run)
    p = sub.add_parser("rescore")
    p.add_argument("dir")
    p.set_defaults(func=rescore)
    p = sub.add_parser("doctor")
    p.set_defaults(func=doctor)
    args = ap.parse_args(argv)
    # Laya 权重目录默认取环境变量，再退回平台默认路径。
    # 注意：只有 audit/run 才有这些参数，doctor / render / rescore 不经过 audit_opts，
    # 所以必须用 hasattr 保护，否则在这些子命令上会 AttributeError。
    if getattr(args, "laya_model_dir", None) is None and hasattr(args, "laya_model_dir"):
        args.laya_model_dir = os.environ.get("LAYA_MODEL_DIR") or laya_default_model_dir()
    args.func(args)
