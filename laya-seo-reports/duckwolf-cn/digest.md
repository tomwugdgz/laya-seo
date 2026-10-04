# Digest: duckwolf.cn
Audited 2026-10-04T16:08:23+00:00. Pages fetched: 13; HTML pages: 7.
Overall 78 (B). Crawl and indexing 81, On-page 76, Content quality 57, Links and architecture 91, Structured data and sharing 91, AI search readiness 71, Performance 93, Security and trust 94, Search visibility and authority n/a
Caps: none. Completeness: {'categories_scored': 8, 'categories_total': 9, 'jev': True, 'jev_pages_not_judged': 0, 'pagespeed': False, 'dataforseo': False}
PARTIAL AUDIT: PageSpeed Insights unavailable, so performance used crawl timings only. Say so in the narrative.
Semantic engine: Laya 本地定案 0 页，5 页因置信度不足升级 Jev（省去 0% 的 Jev 调用）.
Engine split: Laya decided 0 pages, Jev answered 5 pages; Laya averaged 1513.8 ms per call on cuda.
MANDATORY in the narrative: state which engine judged which pages, and do not present Laya's output as authoritative where the digest marks band=review.
Site view (copy these numbers exactly):
- business_model: personal_or_portfolio, confidence 0.88, band act, engine jev
- value_prop: 0.36, confidence 0.91, band act, engine jev
- entity_clarity: 0.57, band review, engine jev
- topical_focus: 0.42, confidence 0.57, band review, engine jev
- serves_local_area: 0.56, band review, engine jev
Homepage: title='duckwolf.cn - Tom Wu 的 AI 商业化与社区媒体智能投放站 - Powered by Discuz!'; h1=[]; meta='duckwolf.cn 是 Tom Wu（亲邻科技，22 年户外广告行业经验）的个人站，主导开发 AIAdPlacer 多 Agent 协同社区媒体 AI 投放系统，覆盖 230+ 城市、7 万+ 社区，投放成本降低 60%、ROI 提升 40%，并分享 GEO 生成式引擎优化、Web4 与 RWA 研究。'

## Actions (id, priority, impact, effort, count, title, evidence, review flags)
- JEV-001 P1 impact 100 effort 2 [jev/content/high] Homepage does not make the offer clear x1: Jev value proposition 0.36 (confidence 0.91)
  URLs: /
- JEV-002 P1 impact 66 effort 1 [rule/onpage/high] No mobile viewport meta tag x1: 1 page
  URLs: /
- JEV-003 P1 impact 66 effort 2 [rule/links/high] Internal links pointing to broken URLs x1: 1 broken targets: 403 https://duckwolf.cn/forum.php?mobile=yes (linked from /)
  URLs: /
- JEV-004 P1 impact 64 effort 1 [rule/crawl/high] Canonical target redirects or returns an error x2: http://duckwolf.cn/aiadplacer.html; http://duckwolf.cn/brandcn.html
  URLs: /aiadplacer.html, /brandcn.html
- JEV-005 P2 impact 50 effort 2 [jev/structured/medium] Local business without LocalBusiness structured data x1: Serves a local area P(yes) 0.56; homepage schema: offer organization person postaladdress propertyvalue softwareapplication webpage website (needs review: 1)
  URLs: /
- JEV-006 P2 impact 47 effort 3 [rule/performance/medium] Slow server response (TTFB above 0.8 s) x6: /: 2045 ms; /claw.html: 2758 ms; /pdooh.html: 2806 ms; /wifi.html: 1299 ms; /aiadplacer.html: 2584 ms; /brandcn.html: 1146 ms
  URLs: /, /claw.html, /pdooh.html, /wifi.html, /aiadplacer.html, /brandcn.html
- JEV-007 P2 impact 44 effort 3 [jev/content/medium] Pages Jev would rewrite or consolidate x5: 5 pages: / (rewrite); /q.html (merge or remove); /claw.html (merge or remove); /pdooh.html (rewrite); /wifi.html (rewrite) (needs review: 3)
  URLs: /, /q.html, /claw.html, /pdooh.html, /wifi.html
- JEV-008 P2 impact 41 effort 1 [rule/onpage/medium] Pages without a meta description x4: 4 indexable pages
  URLs: /q.html, /claw.html, /pdooh.html, /wifi.html
- JEV-009 P2 impact 39 effort 2 [jev/content/medium] Key pages show little evidence of expertise or trust x3: Jev trust averaged 0.39 (0 worst, 1 best) on 3 pages: /, /pdooh.html, /wifi.html (needs review: 2)
  URLs: /, /pdooh.html, /wifi.html
- JEV-010 P2 impact 38 effort 3 [rule/content/medium] Pages with very little main content x3: /q.html: 30 words; /claw.html: 19 words; /wifi.html: 134 words
  URLs: /q.html, /claw.html, /wifi.html
- JEV-011 P2 impact 36 effort 1 [rule/onpage/medium] Pages without an H1 heading x2: 2 indexable pages
  URLs: /, /claw.html
- JEV-012 P2 impact 32 effort 1 [rule/crawl/medium] Canonical points to a different URL x2: https://duckwolf.cn/aiadplacer.html -> http://duckwolf.cn/aiadplacer.html; https://duckwolf.cn/brandcn.html -> http://duckwolf.cn/brandcn.html
  URLs: /aiadplacer.html, /brandcn.html
- JEV-013 P2 impact 32 effort 2 [rule/crawl/medium] Sitemap lists URLs that redirect, fail or are noindex x2: 2 of the crawled sitemap URLs are not final indexable pages
  URLs: /aiadplacer.html, /brandcn.html
- JEV-014 P3 impact 26 effort 1 [jev/onpage/medium] Titles that do not describe the page well x2: Jev title fit averaged 0.32 (0 worst, 1 best) on 2 pages: /q.html, /claw.html (needs review: 1)
  URLs: /q.html, /claw.html
- JEV-015 P3 impact 24 effort 2 [jev/ai/medium] Few self-contained, quotable facts x1: Jev citability averaged 0.24 (0 worst, 1 best) on 1 page: /claw.html (needs review: 1)
  URLs: /claw.html
- JEV-016 P3 impact 17 effort 1 [rule/security/low] No Strict-Transport-Security header x1: Homepage response has no HSTS header
  URLs: /
- JEV-017 P3 impact 17 effort 1 [rule/security/low] Common security headers missing x1: Missing on the homepage response: x-content-type-options, referrer-policy, x-frame-options or CSP frame-ancestors
  URLs: /
- JEV-018 P3 impact 17 effort 1 [rule/security/low] No favicon declared x1: No link rel=icon on the homepage
  URLs: /
- JEV-019 P3 impact 15 effort 1 [rule/crawl/low] Indexable pages missing from the sitemap x5: 5 crawled indexable pages are not listed
  URLs: /, /q.html, /claw.html, /pdooh.html, /wifi.html
- JEV-020 P3 impact 15 effort 1 [rule/crawl/low] Pages without a canonical link x5: 5 of 7 pages
  URLs: /, /q.html, /claw.html, /pdooh.html, /wifi.html
- JEV-021 P3 impact 15 effort 1 [rule/structured/low] Open Graph title or image missing x5: 5 pages lack og:title or og:image
  URLs: /, /q.html, /claw.html, /pdooh.html, /wifi.html
- JEV-022 P3 impact 13 effort 1 [rule/onpage/low] Heading levels skipped x3: 3 pages skip a heading level
  URLs: /, /pdooh.html, /wifi.html
- JEV-023 P3 impact 12 effort 1 [rule/links/low] Internal links that go through a redirect x2: / links to /aiadplacer.html (redirects to /aiadplacer.html); / links to /brandcn.html (redirects to /brandcn.html); / links to /claw.html (redirects to /claw.html); / links to /pdooh.html (redirects to /pdooh.html); / links to /q.html (redirects to /q.html); and 2 more
  URLs: /, /aiadplacer.html
- JEV-024 P3 impact 12 effort 1 [rule/structured/low] Structured data missing properties Google requires for rich results x2: SoftwareApplication on / lacks aggregateRating or review; SoftwareApplication on /aiadplacer.html lacks aggregateRating or review
  URLs: /, /aiadplacer.html
- JEV-025 P3 impact 11 effort 1 [rule/onpage/low] HTML lang attribute missing x1: 1 page
  URLs: /
- JEV-026 P3 impact 11 effort 1 [rule/performance/low] Images without width and height x1: 10 images without explicit size
  URLs: /
- JEV-027 P3 impact 11 effort 1 [rule/links/low] External links returning errors x2: 2 of 15 sampled outbound links
  URLs: moltlist.onrender.com/, wpa.qq.com/msgrd
- JEV-028 P3 impact 11 effort 1 [jev/onpage/low] Weak meta descriptions x1: Jev meta description fit averaged 0.28 (0 worst, 1 best) on 1 page: /
  URLs: /
- JEV-029 P3 impact 9 effort 1 [jev/ai/low] Pages that bury the main point x2: Jev P(opens with the point) averaged 0.32 (0 worst, 1 best) on 2 pages: /q.html, /claw.html (needs review: 1)
  URLs: /q.html, /claw.html
- JEV-030 P3 impact 6 effort 1 [rule/onpage/low] Very short or very long titles x1: 4 chars
  URLs: /q.html

Robots: search bots {'Googlebot': True, 'Bingbot': True}; AI bots checked (10): {'GPTBot': True, 'OAI-SearchBot': True, 'ChatGPT-User': True, 'ClaudeBot': True, 'Claude-SearchBot': True, 'PerplexityBot': True, 'Google-Extended': True, 'Applebot-Extended': True, 'CCBot': True, 'Bytespider': True}

## No issue detected by rule
robots_missing, robots_blocks_site, sitemap_missing, sitemap_errors, http_errors, redirect_chains, noindex, soft_404, host_temporary_redirect, host_variant, no_https, deep_pages, orphan_pages, js_dependent, title_missing, title_duplicate, multiple_titles, meta_duplicate, h1_multiple, duplicate_content, images_alt, no_structured_data, jsonld_errors, faq_rich_result_limited, hreflang_issues, ai_bots_blocked, llms_txt_missing, mixed_content, heavy_html, generic_anchors

Jev ledger: {'cascade': 'laya-first', 'laya_available': True, 'laya_reason': None, 'jev_available': True, 'laya_pages': 0, 'jev_pages': 5, 'laya_calls': 5, 'jev_calls': 6, 'laya_ms': 7569, 'laya_skipped_error': 0, 'promoted': 5, 'accepted_by_laya': 0, 'thresholds': {'laya_q_accept': 0.95, 'laya_page_accept': 0.8, 'jev_act': 0.8}, 'laya_device': 'cuda', 'laya_load_ms': 38950.8, 'laya_q_excluded': 9, 'laya_fallback_pages': 3, 'cost_usd': 0.005397, 'usd_per_mtok': 0.042, 'jev_api': {'model_requested': 'bocha-jev-v1', 'model_returned': 'bocha-jev-v1', 'requests': 15, 'failed': 4, 'input_tokens': 128511, 'output_tokens': 0, 'est_reserved_tokens': 0, 'skipped_budget': 0, 'errors': ['RuntimeError: HTTP 422: {"detail":{"code":"token_budget_exceeded","budget":"expanded_input_tokens","counted_tokens":34041,"limit_tokens":32768,"count_complete":false,"message":"expanded_input_to', 'RuntimeError: HTTP 422: {"detail":{"code":"token_budget_exceeded","budget":"expanded_input_tokens","counted_tokens":33644,"limit_tokens":32768,"count_complete":false,"message":"expanded_input_to', 'RuntimeError: HTTP 422: {"detail":{"code":"token_budget_exceeded","budget":"expanded_input_tokens","counted_tokens":33933,"limit_tokens":32768,"count_complete":false,"message":"expanded_input_to', 'RuntimeError: HTTP 422: {"detail":{"code":"token_budget_exceeded","budget":"expanded_input_tokens","counted_tokens":33517,"limit_tokens":32768,"count_complete":false,"message":"expanded_input_to'], 'batches': 15, 'budget_retries': 4}, 'jev_max_questions_per_request': 2}
