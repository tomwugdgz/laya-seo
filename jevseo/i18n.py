"""Localisation for every user-facing string in the reports.

Design constraint: the audit must be able to emit an English report and a
Chinese one from the same run, without re-crawling and without spending a cent.
That rules out translating at write time only — the translation has to be
available wherever a string is produced (rule titles, fix advice, sheet
headers, chart labels, narrative fragments).

So the approach is a lookup table plus one helper. `T("key")` returns the
current language, falling back to English when a key is missing. English is
the source of truth and lives in the rule tables themselves; this module only
holds the Chinese side plus the shared vocabulary (labels, headers, phrases).

Set the language with `set_lang()`; the CLI `--lang` flag does it, and
`render_both()` switches twice to emit `report.md` + `report.zh.md` from one
audit.
"""
from __future__ import annotations

import re
# ── categories ──────────────────────────────────────────────────────────────
CATEGORIES_ZH = {
    "crawl": "抓取与索引",
    "onpage": "页面内优化",
    "content": "内容质量",
    "links": "链接与结构",
    "structured": "结构化数据与分享",
    "ai": "AI 搜索就绪度",
    "performance": "性能",
    "security": "安全与信任",
    "visibility": "搜索可见性与权威度",
}

# ── severity / priority / band ──────────────────────────────────────────────
SEVERITY_ZH = {"critical": "严重", "high": "高", "medium": "中", "low": "低", "info": "提示"}
PRIORITY_ZH = {"P1": "P1 最优先", "P2": "P2 重要", "P3": "P3 可做", "P4": "P4 有余力再做"}
BAND_ZH = {"act": "可信", "review": "需人工复核", "yes": "是", "no": "否"}
EFFORT_ZH = {1: "很小", 2: "小", 3: "中", 4: "大"}
ORIGIN_ZH = {"code": "代码判定", "rule": "规则检查", "jev": "Jev 云端", "laya": "Laya 本地",
             "laya-fallback": "Laya 兜底",
             # view model 的 action["by"] 用的是这几个显示名而非 origin 键
             "Jev judged": "引擎判定", "DataForSEO": "DataForSEO"}

# ── rule titles and fixes ───────────────────────────────────────────────────
# Keys match jevseo.checks.RULES, jevseo.score.JEV_RULES and DFS_RULES.
RULES_ZH: dict[str, dict[str, str]] = {
    "ai_bots_blocked": {"title": "robots.txt 屏蔽了 AI 爬虫",
                       "fix": "若希望内容进入 AI 回答，允许 GPTBot、ClaudeBot 等主流 AI 爬虫。此项影响 AI 搜索可见性。"},
    "alt_redundant": {"title": "图片 alt 重复了周边文字",
                       "fix": "让 alt 补充图片本身的信息，不要重复标题。"},
    "broken_external_links": {"title": "外部链接返回错误",
                       "fix": "核实这些外链是否仍有效，更新或移除失效链接。"},
    "broken_internal_links": {"title": "内部链接指向无法访问的地址",
                       "fix": "修正或移除这些链接，并更新指向它们的页面。注意：跳转目标是正常设计，需确认为误报还是真死链。"},
    "canonical_broken": {"title": "canonical 目标发生跳转或返回错误",
                       "fix": "把 canonical 改为最终可访问的规范地址。注意：若站点用 http 的 canonical 而实际服务是 https，canonical 自身会跳转，等于告诉搜索引擎「规范版本不存在」。"},
    "canonical_elsewhere": {"title": "canonical 指向其他 URL",
                       "fix": "确认是否有意合并页面；若非有意，把 canonical 改为自身。"},
    "canonical_missing": {"title": "页面没有 canonical 标签",
                       "fix": "为可索引页面加上指向自身的 canonical。"},
    "clay": {"title": "累积布局偏移偏大",
                       "fix": "为图片与广告位预留尺寸，减少布局跳动。"},
    "deep_pages": {"title": "存在距首页超过三次点击的页面",
                       "fix": "通过导航或内链把重要页面提到三层以内，或从站点地图中移除低价值页面。"},
    "dfs_aio_not_cited": {"title": "AI Overview 未引用本站",
                       "fix": "研究当前被引用的来源，确保页面直接回答该搜索。Google 明确表示进入 AI Overview 无需满足 Search 之外的额外要求。"},
    "dfs_backlink_gap": {"title": "外链引用域名远少于同词排名的网站",
                       "fix": "从目标受众已在阅读的网站争取链接：原创数据、工具、专家投稿与合作页。"},
    "dfs_broken_backlinks": {"title": "存在指向失效页面的外链",
                       "fix": "把每个失效目标跳转到最接近的可用页面，让链接重新生效。"},
    "dfs_existing_page": {"title": "相关关键词可由现有页面争取",
                       "fix": "扩展指定页面以覆盖该关键词的搜索需求，并从相关页链入。"},
    "dfs_new_page": {"title": "相关关键词没有对应页面可排名",
                       "fix": "按不同搜索需求规划页面，从高搜索量、低难度的词开始。"},
    "dfs_striking": {"title": "相关关键词已接近首页位置",
                       "fix": "加强对应排名页：更完整地回答搜索问题、补内链、收紧标题。"},
    "duplicate_content": {"title": "多个页面正文完全相同",
                       "fix": "合并重复页面，或改写为各自视角的独立内容。"},
    "duplicate_meta": {"title": "多个页面使用相同 meta description",
                       "fix": "为每个页面写独特的描述。"},
    "duplicate_title": {"title": "多个页面使用相同标题",
                       "fix": "为每个页面写独特的标题，体现各自的主题。"},
    "faq_rich_result_limited": {"title": "FAQPage 标记仅对政府与医疗站点生效",
                       "fix": "非政府或医疗站点不会被 Google 当作 FAQ 富媒体结果展示，但仍可作为 AI 理解结构保留。"},
    "favicon_missing": {"title": "没有声明 favicon",
                       "fix": "添加 <link rel=\"icon\"> 指向站点图标，改善浏览器标签页与收藏的辨识度。"},
    "few_backlinks": {"title": "外链引用域名偏少",
                       "fix": "通过原创数据、工具与合作页争取更多外部链接。"},
    "generic_anchors": {"title": "使用了「点击这里」这类泛化锚文本",
                       "fix": "把锚文本改成能描述目标页面的具体文字。"},
    "h1_empty": {"title": "H1 标题为空",
                       "fix": "把 H1 填成能说明页面主题的文字。"},
    "h1_missing": {"title": "页面没有 H1 主标题",
                       "fix": "为每个页面加一个说明主题的 H1。"},
    "h1_multiple": {"title": "页面有多个 H1",
                       "fix": "保留一个 H1 说明页面主题，其余改为 H2/H3。"},
    "headers": {"title": "缺少安全响应头",
                       "fix": "补充 HSTS、X-Content-Type-Options 等安全响应头。"},
    "heading_order": {"title": "标题层级顺序有误",
                       "fix": "按层级顺序使用 H1 到 H6，不要跳级。"},
    "heading_skips": {"title": "标题层级跳级",
                       "fix": "例如从 H2 直接跳到 H4。按顺序使用标题层级，有助于无障碍阅读与结构解析。"},
    "heavy_html": {"title": "HTML 文档体积过大（超过 500KB）",
                       "fix": "精简 HTML 体积：去掉冗余标记、内联重复数据与过长的内联脚本。"},
    "host_temporary_redirect": {"title": "主机名或 HTTPS 跳转是临时跳转（302/307）",
                       "fix": "改成 301 永久跳转，避免每次抓取都多跳一步。"},
    "host_variant": {"title": "www 与非 www 均可访问同一站点",
                       "fix": "选定一个主机名，把另一版本 301 到该版本。"},
    "hreflang_issues": {"title": "hreflang 标注不完整",
                       "fix": "确保互相指向的语言版本成对配置 hreflang 与 x-default。"},
    "hsts_missing": {"title": "没有 Strict-Transport-Security 响应头",
                       "fix": "在 HTTPS 站点上添加 Strict-Transport-Security 响应头。"},
    "http_errors": {"title": "存在返回 HTTP 错误的页面",
                       "fix": "恢复这些 URL，或跳转到最接近的可用等价页，并更新站内链接。"},
    "http_to_https": {"title": "HTTP 未跳转到 HTTPS",
                       "fix": "让 HTTP 永久跳转到 HTTPS 版本。"},
    "images_alt": {"title": "图片缺少 alt 属性",
                       "fix": "为有信息量的图片补上描述性 alt，纯装饰图留空即可。"},
    "images_dimensions": {"title": "图片未声明宽高",
                       "fix": "为图片补上 width 与 height 属性，避免加载时布局跳动。"},
    "img_missing_alt": {"title": "图片缺少 alt 文本",
                       "fix": "为有信息量的图片补上描述性 alt，纯装饰图留空即可。"},
    "jev_answer_first": {"title": "页面把重点埋在后面",
                       "fix": "开头一到两句直接给出答案或产品说明，不要铺垫。属编辑经验，面向读者与回答引擎，非 Google 要求。"},
    "jev_cannibalization": {"title": "多个页面竞争同一批搜索词",
                       "fix": "为每个搜索需求确定唯一页面：合并、差异化，或把弱页规范化到强页。"},
    "jev_citable": {"title": "缺少可独立引用的完整事实",
                       "fix": "补充脱离上下文也能看懂的事实陈述、定义与数字。属编辑经验，非 Google 要求。"},
    "jev_entity_clarity": {"title": "首页没有 plainly 说明「是谁、做什么、在哪里」",
                       "fix": "在靠前位置用直白的话说明机构名称、业务与市场范围。属编辑经验：Google 明确表示其 AI 功能无需特殊优化。"},
    "jev_h1_fit": {"title": "H1 没有点明页面主题",
                       "fix": "让 H1 说明页面主题，而不是口号。"},
    "jev_helpfulness": {"title": "重要页面没有满足访客需求",
                       "fix": "补充访客真正需要的内容：答案、具体细节、示例与下一步。"},
    "jev_local_schema": {"title": "本地业务但缺少 LocalBusiness 结构化数据",
                       "fix": "添加与页面一致的 LocalBusiness JSON-LD，含名称、地址、电话与营业时间。"},
    "jev_meta_fit": {"title": "meta description 质量偏弱",
                       "fix": "把描述改为具体概括页面交付内容。"},
    "jev_next_step": {"title": "商业页面缺少明确的下一步",
                       "fix": "为每个商业页面给出一个明显且相关的行动入口。"},
    "jev_rewrite": {"title": "建议重写或合并的页面",
                       "fix": "逐页对照建议动作处理。这是引擎的编辑判断，不是搜索引擎规则。"},
    "jev_specificity": {"title": "内容空泛，竞争对手也能写出来",
                       "fix": "加入第一手细节：自己的数据、流程、案例、地点、名称与成果。"},
    "jev_title_fit": {"title": "标题没有准确描述页面内容",
                       "fix": "用搜索者的表达方式重写标题，说清页面提供什么。"},
    "jev_trust": {"title": "关键页面缺少专业度与可信度证据",
                       "fix": "在有助于读者理解处补充具名人员、资质、评价、来源、成果与联系方式。"},
    "jev_value_prop": {"title": "首页没有清楚说明所提供的产品",
                       "fix": "在首页首屏写清楚：你提供什么、面向谁、为什么选你。"},
    "noindex": {"title": "页面被 noindex 排除在搜索之外",
                "fix": "逐个确认 noindex 是否为有意设置；若这些页面应当参与排名，移除 noindex。"},
    "js_dependent": {"title": "内容只有在 JavaScript 执行后才出现",
                       "fix": "确认关键内容与链接在服务端渲染的 HTML 里就存在，否则搜索引擎可能抓不到。"},
    "jsonld_errors": {"title": "结构化数据解析失败",
                       "fix": "按 schema.org 规范修正 JSON-LD 结构，确保能被解析器读懂。"},
    "lang_missing": {"title": "页面没有声明语言",
                       "fix": "在 html 标签上设置 lang 属性。"},
    "lang_wrong": {"title": "页面声明的语言与实际内容不符",
                       "fix": "把 lang 属性改成页面实际使用的语言。"},
    "lcp": {"title": "最大内容绘制偏慢",
                       "fix": "优化首屏大图的加载：预加载、压缩并减少阻塞资源。"},
    "links_to_redirects": {"title": "内部链接经过重定向才到达目标",
                       "fix": "把链接直接指向最终 URL，省去一跳跳转。"},
    "llms_txt_missing": {"title": "没有 llms.txt 文件",
                       "fix": "在站点根目录增加 llms.txt，用纯文本说明站点主题与可引用内容，方便 AI 抓取。"},
    "meta_duplicate": {"title": "多个页面使用相同 meta description",
                       "fix": "为每个页面写独特的描述。"},
    "meta_length": {"title": "meta description 长度不合适",
                       "fix": "把描述调整为能完整表达页面价值的长度。"},
    "meta_missing": {"title": "页面没有 meta description",
                       "fix": "为每个可索引页面写一段能准确概括内容的描述。"},
    "meta_redundant": {"title": "meta description 与正文重复",
                       "fix": "改写成能补充正文价值的概括，而不是照抄第一句。"},
    "missing_h1": {"title": "页面没有 H1 主标题",
                       "fix": "为每个页面加一个说明主题的 H1。"},
    "mixed_content": {"title": "页面存在混合内容",
                       "fix": "把 http 资源统一改为 https。"},
    "multiple_titles": {"title": "页面存在多个 title 元素",
                       "fix": "只保留一个 title 元素。"},
    "no_cta": {"title": "页面没有明确的行动引导",
                       "fix": "给每个商业页面一个明确且相关的行动入口。"},
    "no_https": {"title": "站点未通过 HTTPS 提供服务，或 HTTP 未跳转到 HTTPS",
                       "fix": "为全站启用 HTTPS，并把 HTTP 301 到 HTTPS 版本。"},
    "no_internal_links": {"title": "页面没有内部链接",
                       "fix": "建立指向相关页面与核心转化页的内链。"},
    "no_og": {"title": "缺少 Open Graph 标签",
                       "fix": "补上 og:title、og:description、og:image 等分享标签。"},
    "no_structured_data": {"title": "页面没有结构化数据",
                       "fix": "按页面类型添加对应的 JSON-LD 结构化数据。"},
    "not_in_sitemap": {"title": "可索引页面未出现在站点地图中",
                       "fix": "把这些规范页面补进站点地图。"},
    "og_image_missing": {"title": "缺少分享预览图",
                       "fix": "提供一张 1200x630 的 og:image。"},
    "og_image_small": {"title": "分享预览图尺寸偏小",
                       "fix": "改用至少 1200x630 的图片。"},
    "og_missing": {"title": "Open Graph 标题或图片缺失",
                       "fix": "补上 og:title 与 og:image，让分享链接有标题与预览图。"},
    "og_url_mismatch": {"title": "Open Graph url 与规范地址不一致",
                       "fix": "把 og:url 设为与 canonical 相同的地址。"},
    "open_bury": {"title": "正文开头没有直接给出结论",
                       "fix": "把答案或核心信息放在开头一到两句内。"},
    "orphan": {"title": "站点地图中列出的页面没有内链指向",
                       "fix": "从相关页面建立指向这些页面的内链。"},
    "orphan_pages": {"title": "页面没有内链指向",
                       "fix": "从导航或相关内容页建立指向这些页面的链接。"},
    "redirect_chains": {"title": "存在多跳重定向链",
                       "fix": "把重定向压缩为一次，直接指向最终页面。"},
    "redirect_loops": {"title": "存在重定向循环",
                       "fix": "修正跳转目标，消除循环。"},
    "robots_blocks_site": {"title": "robots.txt 对全站屏蔽了搜索引擎爬虫",
                       "fix": "移除对搜索引擎 user agent 的全站 Disallow。"},
    "robots_missing": {"title": "没有 robots.txt 文件",
                       "fix": "在站点根目录发布 robots.txt，允许抓取并列出站点地图。"},
    "schema_required": {"title": "结构化数据缺少 Google 富媒体结果所需字段",
                       "fix": "补齐该类型对应的必填属性，例如 Article 的 headline 与 datePublished。"},
    "security_headers": {"title": "缺少常见安全响应头",
                       "fix": "补充 Strict-Transport-Security、X-Content-Type-Options、X-Frame-Options 等响应头。"},
    "sitemap_bad_urls": {"title": "站点地图中列出的 URL 存在跳转、错误或 noindex",
                       "fix": "站点地图中只保留最终、可索引、返回 HTTP 200 的 URL。"},
    "sitemap_errors": {"title": "站点地图文件无法访问或格式无效",
                       "fix": "修正 sitemap 地址，使其返回 HTTP 200 且 XML 合法。"},
    "sitemap_missing": {"title": "没有找到 XML 站点地图",
                       "fix": "生成一份包含规范、可索引 URL 的 XML sitemap，并在 robots.txt 中引用。"},
    "slow_ttfb": {"title": "服务端响应偏慢（TTFB 超过 0.8 秒）",
                       "fix": "优化服务端响应时间：开启缓存、减少数据库查询、必要时加 CDN。Discuz 站点常见原因是 PHP 未启用 OPcache。"},
    "soft_404": {"title": "缺失页面返回 HTTP 200（软 404）",
                       "fix": "对不存在的页面返回真正的 404，不要返回带错误文案的 200。"},
    "thin_content": {"title": "页面正文内容过少",
                       "fix": "补充能回答用户问题的实质内容。若这是有意精简的落地页，考虑改用其他页面类型。"},
    "title_duplicate": {"title": "多个页面使用相同标题",
                       "fix": "为每个页面写独特的标题，体现各自的主题。"},
    "title_length": {"title": "标题过短或过长",
                       "fix": "把标题调整到能准确概括页面主题的长度。"},
    "title_mismatch": {"title": "标题与页面实际内容不符",
                       "fix": "让标题准确描述页面内容，避免点击后落差。"},
    "title_missing": {"title": "页面没有标题",
                       "fix": "为每个可索引页面写一个能描述其内容的标题。"},
    "title_rewrite": {"title": "建议重写的标题",
                       "fix": "用搜索者的表达方式重写标题，说清页面提供什么。"},
    "too_many_links": {"title": "页面链接数量异常",
                       "fix": "删掉与主题无关的链接，保持导航聚焦。"},
    "ttfb": {"title": "首字节时间偏慢",
                       "fix": "优化服务端响应时间：缓存、数据库查询与边缘计算。"},
    "twitter_card": {"title": "缺少 Twitter Card 标签",
                       "fix": "补上 twitter:card 等分享卡片标签。"},
    "viewport_missing": {"title": "没有移动端 viewport meta 标签",
                       "fix": "添加 &lt;meta name=viewport content=\"width=device-width, initial-scale=1.0\"&gt;。这是移动端排版正常的前提，也是移动优先索引的基线要求。"},
}
# ── shared vocabulary ───────────────────────────────────────────────────────
VOCAB_ZH = {
    # report scaffolding
    "audit_title": "Laya SEO 审计报告",
    "audited_on": "审计时间",
    "urls_crawled": "已抓取 URL",
    "html_pages": "HTML 页面",
    "semantic_judgments": "条语义判断",
    "engine_cost": "引擎费用",
    "overall_score": "总分",
    "grade": "等级",
    "partial_audit": "部分审计",
    "partial_note": "总分仅覆盖已评估的区域。",
    "area": "区域",
    "score": "得分",
    "weight": "权重",
    "how_scored": "评分方式",
    "na": "未评估",
    # narrative
    "executive_summary": "执行摘要",
    "how_this_audit": "审计方法",
    "priority_actions": "优先行动",
    "search_visibility": "搜索可见性（DataForSEO）",
    "what_crawl_found": "抓取发现",
    "how_engines_read": "各引擎如何判读本站",
    "findings_by_area": "各区域发现",
    "robots_access": "Robots 与访问",
    "page_inventory": "页面清单",
    "method_and_limits": "方法与局限",
    "strongest": "最强",
    "weakest": "最弱",
    "actions_produced": "个行动项",
    "marked_fix_first": "个标记为优先修",
    "quick_wins": "个快速见效项",
    "directory_contents": "目录",
    "ranking_keywords": "排名关键词",
    "page_a": "页面 A",
    "page_b": "页面 B",
    "title_overlap": "标题重合度",
    "compete": "竞争",
    "competing_pages": "可能竞争同一批搜索词的页面",
    "affected": "受影响",
    "user_agent": "User agent",
    "access": "访问",
    "user_agent_allowed": "允许",
    "user_agent_blocked": "屏蔽",
    "core_web_vitals": "Core Web Vitals 真实数据",
    "lighthouse_scores": "Lighthouse 评分",
    "to_verify": "项待复核",
    "and_more": "另有",
    "no_actions_found": "无需行动项",
    "written_by": "撰写",
    # XLSX Summary
    "semantic_engine_cost": "语义引擎费用（美元）",
    "dataforseo_cost": "DataForSEO 费用（美元）",
    "not_used": "未使用",
    "engine_split": "引擎分工",
    "status_counts": "各状态的实时数量（取自行动项工作表）",
    "open_by_priority": "按优先级统计的未完成项",
    "total_actions": "行动项总数",
    "action_status": "行动项状态",
    "id": "编号",
    "owner": "负责人",
    "due": "截止",
    "notes": "备注",
    "quick_win": "快速见效",
    "judged_by": "判定方",
    "needs_human_check": "需人工核对",
    "domain": "域名",
    "shared_keywords": "共同关键词",
    "avg_position": "平均位置",
    "serp_features": "SERP 特性",
    "cites_site": "引用本站",
    "ai_overview_sources": "AI Overview 来源",
    "top_10": "前十",
    "platform": "平台",
    "model": "模型",
    "sources_cited": "被引来源",
    "topic": "主题",
    "field_data_level": "真实数据级别",
    "value": "数值",
    "title_chars": "标题字数",
    "meta_chars": "描述字数",
    "h1_count": "H1 数量",
    "html_kb": "HTML 体积(KB)",
    "ttfb": "首字节时间",
    "rendered": "已渲染",
    "best_practices": "最佳实践",
    "accessibility": "无障碍",
    "device": "设备",
    "other_brand": "其他品牌",
    "kept_by_filter": "筛选后保留",
    "rankings": "排名",
    "opportunities": "机会",
    "competitors": "竞争对手",
    "serps": "搜索结果页",
    "ai_mentions": "AI 提及",
    "status": "状态码",
    "answer_0_to_1_or_option": "答案（0-1 或选项）",
    "side_probability": "半侧概率（Score）",
    "side_probability_score": "半侧概率（Score）",
    "searches_mo": "月搜索量",
    "page_to_own_it": "应争取该词的页面",
    "page_to_own": "应争取该词的页面",
    # tables
    "action": "行动项",
    "actions": "行动项",
    "priority": "优先级",
    "impact": "影响",
    "effort": "成本",
    "category": "类别",
    "severity": "严重度",
    "title": "标题",
    "fix": "修法",
    "evidence": "证据",
    "affected_urls": "涉及 URL",
    "check": "检查项",
    "source": "依据",
    "heuristic": "编辑经验（非搜索引擎规则）",
    "needs_review": "需人工复核",
    "page": "页面",
    "question": "问题",
    "primitive": "原语",
    "answer": "答案",
    "confidence": "置信度",
    "side_probability": "半侧概率（Score）",
    "band": "判带",
    "top_probabilities": "主要概率",
    "engine": "引擎",
    "detail": "明细",
    "status": "状态",
    "depth": "深度",
    "words": "词数",
    "inlinks": "内链",
    "outlinks": "出链",
    "images": "图片",
    "no_alt": "缺 alt",
    "indexable": "可索引",
    "in_sitemap": "在 sitemap",
    "canonical": "canonical",
    "schema": "结构化数据",
    "device": "设备",
    "domain": "域名",
    "url": "URL",
    "generated_by": "由 {} 生成",
    # robots
    "search_bots": "搜索引擎爬虫",
    "ai_bots_checked": "已检查的 AI 爬虫",
    # charts
    "overall": "总分",
    "by_area": "各区域得分",
    "depth_chart": "抓取深度分布",
    "page_types": "页面类型",
    "intents": "搜索意图",
    "page_quality_heatmap": "页面质量热力图",
    "how_sure": "引擎有多确定",
    "importance_vs_quality": "重要度与质量",
    "impact_effort": "影响与成本",
    "opportunities": "值得争取的关键词",
    "where_to_invest": "投入方向",
    "funnel": "从发现 URL 到完成判定",
    "site_map": "站点结构图",
    "status_chart": "状态码分布",
    "severity_by_category": "各类别的严重度",
    "page_actions": "页面行动量",
    "title_len": "标题长度",
    "positions": "排名位置",
    "referring_domains": "引用域名",
    "words_chart": "页面字数",
    "lighthouse": "Lighthouse",
    "from_discovered": "从发现的 URL 到判定的页面",
    "important_but_weak": "重要但薄弱",
    "importance": "重要度",
    "quality": "质量",
    "suggests": "引擎建议",
    "best_practices": "最佳实践",
    "method": "方法",
    "area_score": "区域得分",
    "how_scored_short": "评分方式",
    # scoring method prose
    "pipeline_desc": "流水线",
    "area_score_desc": "区域得分",
    "impact_desc": "影响",
    "effort_desc": "成本",
    "confidence_desc": "置信度",
    "band_desc": "判带",
    # method/limits table
    "stage": "阶段",
    "source_of_data": "数据来源",
    "note": "说明",
    # rules sheet
    "check_name": "检查项",
    "what_it_checks": "检查内容",
    "best_practice": "最佳实践",
    # audit log
    "generated": "生成时间",
    "run": "运行",
    "options": "选项",
    "timings": "耗时",
    "target": "目标",
    # pagespeed
    "performance": "性能",
    "lcp": "最大内容绘制",
    "cls": "累积布局偏移",
    "tbt": "总阻塞时间",
    "fcp": "首屏绘制",
    "si": "速度指数",
    "ttfb": "首字节时间",
    "passed": "通过",
    "opportunities_found": "发现的问题",
    # dataforseo
    "keyword": "关键词",
    "position": "位置",
    "searches_month": "月搜索量",
    "difficulty": "难度",
    "cpc": "CPC（美元）",
    "est_visits": "预估访问（ETV）",
    "ranking_url": "排名 URL",
    "relevance": "相关度",
    "source_col": "来源",
    "page_to_own": "应争取该词的页面",
    "kept_by_filter": "筛选后保留",
    "competitors": "竞争对手",
    "shared_keywords": "共同关键词",
    "backlinks": "外链",
    "broken_backlinks": "失效外链",
    "ai_overview": "AI Overview",
    "cites_site": "引用本站",
    "ai_mentions": "AI 提及",
    "ai_search_volume": "AI 搜索量",
    "own_position": "本站位置",
    "top_competitors": "前 3 名",
    "sampled": "抽样",
    "referring": "引用来源",
    # accessibility / misc
    "accessibility": "无障碍",
    "rating": "评级",
    "cited_by": "被引用于",
    "detected": "检测到",
    "not_detected": "未检测到",
    "clear_next_step": "明确下一步",
    "answer_first": "开头给结论",
    "citability": "可引用性",
    "title_fit": "标题匹配",
    "meta_fit": "描述匹配",
    "h1_fit": "H1 匹配",
    "helpfulness": "有用性",
    "specificity": "具体性",
    "trust": "可信度",
    "business_model": "商业模式",
    "value_prop": "价值主张",
    "entity_clarity": "主体清晰度",
    "topical_focus": "主题聚焦",
    "serves_local_area": "服务本地区域",
    "what_kind_of_business": "这是什么类型的业务",
    "page_kind": "页面类型",
    "search_intent": "搜索意图",
}

# ── sentence fragments ──────────────────────────────────────────────────────
PHRASE_ZH = {
    "not_assessed": "未评估",
    "rules_only": "仅规则",
    "rules_plus": "规则 + 引擎判断",
    "crawl_obs_only": "仅抓取观测",
    "no_issue_by_rule": "规则未发现问题",
    "robots_search_bots": "搜索引擎爬虫",
    "words_unit": "词",
    "pages_unit": "页",
    "fix_first": "优先修",
    "quick_win": "快速见效",
    "important_but_weak_col": "重要但薄弱",
    "generated_at": "生成于",
    "score_unit": "分",
    "of_100": "/100",
    "audited_at": "审计于",
    "no_actions": "无需行动",
    "verified_pass": "规则通过",
    "lighthouse_note": "移动端与桌面端各测一次，取移动端计入总分",
    "crawl_timing_note": "未跑 PageSpeed Insights，性能仅用抓取计时估算",
    "semantic_from_laya_only": "语义判断全部来自本地 Laya 模型。它是判别式模型，在已知答案的页面类型测试中只答对 2/4，且不生成文本。请把内容与 AI 就绪度评分视为暂定，动手前务必人工核对。",
    "cascade_note": "语义判断来自级联：",
    "pages_decided_locally": "页由本地 Laya 判定",
    "pages_escalated": "页升级到云端 Jev",
    "jev_calls_avoided": "的 Jev 调用被省去",
    "read_as_engine_column": "下方图表或表格中标「Jev」的地方，请读作「Semantic judgments 工作表的 Engine 列所指的引擎」。",
    "laya_model_note": "Laya 是判别式 System One 模型，运行在本机 GPU 上",
}


class _Lang:
    """当前语言。默认英文——英文是原文，缺失词条回退到它。"""

    def __init__(self) -> None:
        self.code = "en"

    def set(self, code: str) -> str:
        code = (code or "en").lower()
        if code not in ("en", "zh"):
            code = "en"
        self.code = code
        return self.code

    @property
    def is_zh(self) -> bool:
        return self.code == "zh"


LANG = _Lang()


def set_lang(code: str) -> str:
    """切换报告语言。返回规范化后的代码。"""
    return LANG.set(code)


def get_lang() -> str:
    return LANG.code


def is_zh() -> bool:
    return LANG.is_zh


def T(key: str, default: str | None = None) -> str:
    """查词条。英文模式直接返回 default（调用处的原文）。

    键做小写归一：词条表用 snake_case 小写键（`affected_urls`），
    而 XLSX 表头传入的是 `Affected URLs` 这类展示文本，大小写不一致。
    """
    if not LANG.is_zh:
        return default if default is not None else key
    table = VOCAB_ZH
    norm = key.strip().lower()
    # 归一：空格/斜杠/连字符都当分隔符，这样 "Searches/mo" 与
    # "affected urls" 都能命中同一条词条。
    norm = norm.replace("/", "_").replace("-", "_").replace(" ", "_")
    norm = re.sub(r"_+", "_", norm).strip("_")
    if norm in table:
        return table[norm]
    # 表头常带括号补充说明，如 "Answer (0 to 1 or option)"：查整体后
    # 退化到括号前的主词（"answer"），最后才回退英文。
    if "(" in key:
        head = key.split("(")[0].strip().lower().replace("/", "_").replace(" ", "_")
        if head in table:
            return table[head]
    return default if default is not None else key


def category(key: str, default: str | None = None) -> str:
    if not LANG.is_zh:
        return default if default is not None else key
    return CATEGORIES_ZH.get(key.strip().lower(), default if default is not None else key)


def severity(key: str, default: str | None = None) -> str:
    if not LANG.is_zh:
        return default if default is not None else key
    return SEVERITY_ZH.get(key.strip().lower(), default if default is not None else key)


def rule(key: str, field: str, default: str | None = None) -> str:
    """取规则的中文 title 或 fix。field 为 'title' 或 'fix'。"""
    if not LANG.is_zh:
        return default if default is not None else key
    entry = RULES_ZH.get(key)
    if entry and field in entry:
        return entry[field]
    return default if default is not None else key


def vocab(key: str, default: str | None = None) -> str:
    return T(key, default)


def phrase(key: str, default: str | None = None) -> str:
    return T(key, default)


def suffix_zh(en: str) -> str:
    """把英文分类名换成中文（用于 CATEGORIES 字典整体替换）。"""
    return CATEGORIES_ZH.get(en, en)
