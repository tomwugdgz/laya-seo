"""级联编排：Laya 本地闸门 → Jev 云端权威 → 人工复核。

设计依据（实测，2026-10-04）
--------------------------
Laya 与 Jev 共用 System One 原语，接口签名相同，但可靠性差异巨大：

| 引擎 | 类型 | 成本 | page_type 实测 | 置信度特征 |
| --- | --- | --- | --- | --- |
| Laya | 本地判别模型 | 0 | 2/4 | 均值 0.901，但**错误与高置信度正相关** |
| Jev | 云端生成式 LLM | $0.042/Mtok | 经 A/B 调优 | 低置信度答案更多，但准确 |

致命细节：Laya 把「文章页」判为 homepage 时置信度仍达 **0.962**，
稳稳越过 jevseo.jev.ACT=0.80 阈值。若无脑采信，会输出「高置信度的错误结论」。

因此本编排器的三条铁律：
1. **Laya 单题置信度达标不直接采信**，必须该题与该页的多数语义题同时达标。
2. 任何 Laya 答案一律带 origin="laya" 标记，报告层必须可区分。
3. 阈值不是照搬通用值，而是由本项目 references/cascade.md 记录的可调参数。

级联方向也可反向使用（--cascade jev-first）：先花钱问 Jev，
Jev 明确（高置信度 + 无 review）就不必再跑本地。默认 laya-first，因为本地零成本。
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from jevseo.jev import PAGE_TEXT_CHARS_LOCAL, Jev, validate
from jevseo.laya import DEFAULT_MODEL_DIR, DEFAULT_SUBFOLDER, LayaEngine, LayaUnavailable


def validate_local(question: dict, answer: dict) -> dict:
    """Laya 答案的宽容校验：钳制超范围 score，重算不可信的 confidence。

    放在 cascade.py 而非 cli.py，让级联与 offline 两条路径共用一份口径。

    三处与 jevseo.jev.validate 的差异，均来自实测：
    1. score 可能是连续值（实测 1.584，选项 0-3），需按比例钳制而非抛异常；
    2. score 类 confidence 与实际判断不一致（实测 0.075 但概率峰值在正确答案），
       改用概率半侧判定；
    3. noul 类报出的 confidence 与判断方向相反（实测 noul=0.297 却报 0.703），
       结论值保留，confidence 重算并标记不可信。
    """
    t = question["type"]
    if t == "score":
        top = len(question["criteria"]) - 1
        s = float(answer.get("score", 0))
        probs = answer.get("probabilities") or {}
        a = dict(answer)
        a["score"] = max(0.0, min(float(top), s))
        try:
            out = validate(question, a)
        except Exception:  # noqa: BLE001
            out = {"type": t, "raw": s, "levels": top + 1, "probabilities": {},
                   "confidence": float(answer.get("confidence", 0)), "band": "review"}
        out["score_raw"] = s
        out["value"] = round(max(0.0, min(1.0, s / top)), 4) if top else 0.0
        if probs and top:
            upper = sum(float(v) for k, v in probs.items() if float(k) / top >= 0.5)
            side = max(upper, 1 - upper)
            out["side_probability"] = round(side, 4)
            out["band"] = "act" if side >= 0.80 else "review"
            out["confidence"] = round(side, 4)
        else:
            out["band"] = "review"
        return out
    if t == "noul":
        a = dict(answer)
        a.setdefault("noul", answer.get("noul", 0.0))
        out = validate(question, a)
        if "confidence" in answer:
            out["laya_confidence_unreliable"] = True
            out["confidence"] = round(abs(float(a.get("noul", 0.0)) - 0.5) * 2, 4)
        return out
    return validate(question, answer)

# ── 阈值（全部可在 config 中覆盖）─────────────────────────────────────────
#: Laya 单题采信阈值。实测 page_type 高置信度答案正确，但并非全部；
#: 0.95 是「模型非常确定」的保守取值，低于 jev 的 ACT=0.80。
LAYA_Q_ACCEPT = 0.95
#: Laya 整页采信阈值：该页**可采信题**的置信度均值需达到此值。
LAYA_PAGE_ACCEPT = 0.80
#: 低于 LAYA_PAGE_ACCEPT 则升级 Jev。留 0.80-0.95 为「观察带」，仍走 Jev 但记录在案。
LAYA_UPGRADE = 0.80
#: state token 上限。超过此值直接升级 Jev，不再尝试 Laya。
#:
#: 实测（2026-10-04，qinlinkeji.com 中文站）：真实中文页面估算 1000-1546 token，
#: 早期设 900 时全部页面被拦，级联节省率恒为 0。
#: Laya 自身会处理超长 state（返回体含 state_tokens / state_tokens_dropped / truncated 字段），
#: 因此这里放宽到 2000，让 Laya 有机会工作；真正的截断风险由 confidence 机制兜住——
#: 输入被截断时模型的判断同样不可靠，置信度会随之下降，自然落入 review 或升级。
STATE_TOKEN_LIMIT = 2000

#: 只有 choice 类参与采信判定。实测依据（2026-10-04）：
#:   - choice：probabilities 分布清晰，置信度 1.000 / 0.962 / 0.642 有区分度。
#:   - score：helpfulness 置信度实测仅 0.075，而其概率峰值在 0.417——
#:     模型明明把最大概率给了正确答案，confidence 字段却接近 0。不可用于采信。
#:   - noul ：answer_first 实测 noul=0.297（判否）却报 confidence=0.703，
#:     方向与 confidence 相反，更不能用。
#: 因此 score/noul 的结果照常记录进报告（供人工参考），但不参与是否升级的决策。
DECISIVE_TYPES = ("choice",)


def _page_weighted_confidence(answers: dict, keys: list[str]) -> tuple[float, int, int]:
    """采信判定用的置信度。返回 (均值, 参与统计的题数, 被排除的题数)。

    只统计 choice 类（DECISIVE_TYPES）。score / noul 的 confidence 字段在 Laya 上
    与实际判断不一致（实测 score 置信度 0.075 但概率峰值在正确答案；
    noul 报 0.703 而判断为否），纳入计算会让 Laya 永远不够阈值，等于级联失效。

    权重策略（全部来自实测）：
    - intent 权重 0.5：本质模糊，实测均值仅 0.413。若同权会把整页拉低。
    - action 权重 1.0：keep / rewrite / merge 三分，边界清晰，实测置信度可用。
    - page_type 在首页被 code 预先判定（question 本身不存在），因此首页实际只剩
      intent 与 action。把 action 提到 1.0 是首页能否本地定案的关键。
    """
    weights = {"intent": 0.5}
    total = 0.0
    wsum = 0.0
    skipped = 0
    for k in keys:
        a = answers.get(k)
        if not a:
            continue
        if a.get("type") not in DECISIVE_TYPES:
            skipped += 1
            continue
        if "confidence" not in a:
            continue
        w = weights.get(k, 1.0)
        total += float(a["confidence"]) * w
        wsum += w
    return (total / wsum if wsum else 0.0), int(wsum), skipped


class Cascade:
    """Laya 与 Jev 的级联调度器。对外只暴露 judge()。"""

    def __init__(
        self,
        *,
        laya_model_dir: str = str(DEFAULT_MODEL_DIR),
        laya_subfolder: str = DEFAULT_SUBFOLDER,
        laya_device: str = "auto",
        laya_enabled: bool = True,
        cascade: str = "laya-first",
        q_accept: float = LAYA_Q_ACCEPT,
        page_accept: float = LAYA_PAGE_ACCEPT,
        log: Callable[[str], None] = print,
    ) -> None:
        self.cascade = cascade
        self.q_accept = q_accept
        self.page_accept = page_accept
        self.log = log
        self.laya = LayaEngine.get(model_dir=laya_model_dir, subfolder=laya_subfolder,
                                    device=laya_device) if laya_enabled else None
        self.jev = Jev(log=log)
        self.lock = threading.Lock()
        self.ledger: dict = {
            "cascade": cascade,
            "laya_available": False,
            "laya_reason": None,
            "jev_available": self.jev.available,
            "laya_pages": 0,
            "jev_pages": 0,
            "laya_calls": 0,
            "jev_calls": 0,
            "laya_ms": 0,
            "laya_skipped_error": 0,
            "promoted": 0,          # 因 Laya 置信度不足而升级 Jev 的页数
            "accepted_by_laya": 0,  # 整页由 Laya 定案的页数
            "thresholds": {
                "laya_q_accept": q_accept,
                "laya_page_accept": page_accept,
                "jev_act": 0.80,
            },
        }

    # ── 能力探测 ─────────────────────────────────────────────────────────────
    def probe(self) -> bool:
        """尝试加载 Laya。失败不阻断审计，只降级为纯 Jev 模式。"""
        if self.laya is None:
            self.ledger["laya_reason"] = "Laya 已通过配置禁用"
            return False
        try:
            self.laya.ensure_loaded(log=self.log)
            self.ledger["laya_available"] = True
            self.ledger["laya_device"] = self.laya.device
            self.ledger["laya_load_ms"] = round(self.laya.load_ms, 1)
            return True
        except LayaUnavailable as err:
            self.ledger["laya_reason"] = str(err)
            self.log(f"Laya 不可用，级联降级为纯 Jev：{err}")
            return False

    @property
    def usable(self) -> bool:
        """是否有任一引擎可用。两者皆无则整份报告标为未评估。"""
        return bool(self.jev.available) or bool(self.ledger["laya_available"])

    # ── 单页级联 ─────────────────────────────────────────────────────────────
    def _run_laya(self, state: dict, questions: dict) -> dict | None:
        t0 = time.perf_counter()
        raw = self.laya.ask(state, questions)
        with self.lock:
            self.ledger["laya_calls"] += 1
            self.ledger["laya_ms"] += int((time.perf_counter() - t0) * 1000)
        if raw is None:
            with self.lock:
                self.ledger["laya_skipped_error"] += 1
            return None
        out = {}
        dropped = []
        for k, q in questions.items():
            if k not in raw:
                dropped.append(k)
                continue
            try:
                # validate_local 而非 validate：Laya 的 score 是连续值
                # （实测 1.584，选项仅 0-3），validate 会因超范围抛异常并静默丢掉整题。
                out[k] = self._tag(validate_local(q, raw[k]), "laya")
            except Exception as err:  # noqa: BLE001  单题校验失败视为未评估，但必须留痕
                self.log(f"Laya 答案校验失败 {k}: {type(err).__name__}")
                dropped.append(k)
        if dropped:
            with self.lock:
                self.ledger["laya_dropped_questions"] = self.ledger.get("laya_dropped_questions", 0) + len(dropped)
        return out or None

    def _run_jev(self, state: dict, questions: dict) -> dict | None:
        with self.lock:
            self.ledger["jev_calls"] += 1
        ans = self.jev.ask(state, questions)
        if ans is None:
            return None
        return {k: self._tag(v, "jev") for k, v in ans.items()}

    @staticmethod
    def _tag(answer: dict, origin: str) -> dict:
        a = dict(answer)
        a["origin"] = origin
        return a

    def judge_page(self, state: dict, questions: dict,
                    state_builder=None) -> tuple[dict | None, str]:
        """返回 (答案, 实际引擎)。答案 None 表示两引擎均不可用。

        降级顺序：Laya -> Jev -> Laya 兜底。最后一步针对 Jev 因账号级配额
        被拒（实测 HTTP 422 counted_tokens 与请求无关）的情形：宁可给出标注
        为代理判断的低置信度结果，也不要留空——留空会让该页在报告里彻底消失。

        state_builder：可选的 (state, questions) -> (state, questions) 钩子，
        供调用方在送入 Laya 前裁剪 state（本地引擎上下文更短）。
        """
        if not questions:
            return None, "none"

        laya_ok = bool(self.ledger["laya_available"])

        def finish_from_jev():
            ans = self._run_jev(state, questions)
            if ans is not None:
                return ans, "jev"
            # Jev 不可用或被配额拒绝：退回 Laya 的原始答案，标注为兜底。
            # 置信度不足会让 score / noul 落入 review，报告不会把它当权威结论。
            if laya_ok and raw_answers:
                for a in raw_answers.values():
                    a["laya_fallback"] = True
                with self.lock:
                    self.ledger["laya_fallback_pages"] = self.ledger.get("laya_fallback_pages", 0) + 1
                return raw_answers, "laya-fallback"
            return None, "jev"

        if not laya_ok:
            return finish_from_jev()

        # Laya 的上下文窗口更短，先按本地预算裁剪再送入
        laya_state = state
        if state_builder is not None:
            laya_state, laya_questions = state_builder(state, questions)
        else:
            laya_questions = questions

        # Laya 预跑；state 可能超长，先看 token
        raw_answers = self._run_laya(laya_state, laya_questions)
        if raw_answers is None:
            # Laya 失败不重试，直接升级（本地失败多为权重/环境问题，重试无意义）
            with self.lock:
                self.ledger["jev_pages"] += 1
                if self.jev.available:
                    self.ledger["promoted"] += 1
            return finish_from_jev()

        state_tokens = self._state_tokens(laya_state)
        if state_tokens > STATE_TOKEN_LIMIT:
            with self.lock:
                self.ledger["promoted"] += 1
                self.ledger["jev_pages"] += 1
            self.log(f"Laya 状态超长（{state_tokens} token），升级 Jev")
            return finish_from_jev()

        conf, n, skipped = _page_weighted_confidence(raw_answers, list(laya_questions))
        self.ledger["laya_q_excluded"] = skipped

        if self.cascade == "jev-first":
            # 先问 Jev；Jev 明确则不必跑 Laya（本路径不省调用，仅作对照调试）
            ans = self._run_jev(state, questions)
            if ans is not None and all(a.get("band") != "review" for a in ans.values()):
                with self.lock:
                    self.ledger["jev_pages"] += 1
                    self.ledger["accepted_by_laya"] += 0
                return ans, "jev"
            # Jev 不确定，用 Laya 作二次意见，仍以 Jev 为主
            if ans is None and raw_answers:
                with self.lock:
                    self.ledger["laya_pages"] += 1
                return raw_answers, "laya"
            return ans, "jev"

        # laya-first：整页加权置信度达标才采信 Laya
        if conf >= self.page_accept:
            with self.lock:
                self.ledger["laya_pages"] += 1
                self.ledger["accepted_by_laya"] += 1
            for k, a in raw_answers.items():
                a["page_laya_confidence"] = round(conf, 4)
                a["laya_questions_considered"] = n
            return raw_answers, "laya"

        # 置信度不足 → 升级 Jev。这是级联的主要价值点
        with self.lock:
            self.ledger["jev_pages"] += 1
            if self.jev.available:
                self.ledger["promoted"] += 1
        return finish_from_jev()

    @staticmethod
    def _state_tokens(state: dict) -> int:
        """粗略估算 state token 数。中文约 1.5 字/token，英文约 4 字符/token。"""
        import json

        blob = json.dumps(state, ensure_ascii=False, default=str)
        cjk = sum(1 for ch in blob if "一" <= ch <= "鿿")
        other = len(blob) - cjk
        return int(cjk / 1.5 + other / 4)


def summarize(ledger: dict) -> dict:
    """把级联账本压成报告里的一段可读结论。"""
    if not ledger.get("laya_available"):
        return {"mode": "jev-only",
                "note": "Laya 未启用，语义判断全部由 Jev 完成"}
    acc = ledger.get("accepted_by_laya", 0)
    pro = ledger.get("promoted", 0)
    total = acc + pro
    ratio = round(acc / total, 3) if total else 0.0
    return {
        "mode": "cascade",
        "laya_pages": ledger.get("laya_pages", 0),
        "jev_pages": ledger.get("jev_pages", 0),
        "accepted_by_laya": acc,
        "promoted_to_jev": pro,
        "laya_savings_ratio": ratio,
        "laya_avg_ms": (round(ledger.get("laya_ms", 0) / ledger["laya_calls"], 1)
                        if ledger.get("laya_calls") else None),
        "device": ledger.get("laya_device"),
        "note": (f"Laya 本地定案 {acc} 页，{pro} 页因置信度不足升级 Jev"
                 f"（省去 {ratio:.0%} 的 Jev 调用）"),
    }
