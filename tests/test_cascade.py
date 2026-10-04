"""Cascade orchestration tests. Offline by default: no keys, no network, no weights loaded.

These cover the decision logic that the audit depends on — the thresholds, the
weighted confidence, and the escalation rules — because those are what turn a
2/4-accurate local model into something safe to run.
"""
import json
import unittest
from unittest import mock

from jevseo import cascade


class TestWeightedConfidence(unittest.TestCase):
    def test_empty_gives_zero(self):
        conf, n, skipped = cascade._page_weighted_confidence({}, ["a", "b"])
        self.assertEqual((conf, n, skipped), (0.0, 0, 0))

    def test_all_present_confidence(self):
        ans = {"page_type": {"type": "choice", "confidence": 1.0},
               "helpfulness": {"type": "choice", "confidence": 0.8}}
        conf, n, _ = cascade._page_weighted_confidence(ans, ["page_type", "helpfulness"])
        self.assertEqual(n, 2)
        self.assertAlmostEqual(conf, 0.9, places=3)

    def test_intent_weight_is_halved(self):
        """A vague question must not drag the whole page below threshold.

        Measured intent confidence averages 0.413 against page_type's 0.901.
        With equal weight the page mean would sit near 0.66 and never clear a
        0.80 threshold, so Laya would never decide anything.
        """
        ans = {"page_type": {"type": "choice", "confidence": 1.0},
               "intent": {"type": "choice", "confidence": 0.4}}
        conf, _, _ = cascade._page_weighted_confidence(ans, ["page_type", "intent"])
        # (1.0*1.0 + 0.4*0.5) / 1.5 = 0.8
        self.assertAlmostEqual(conf, 0.8, places=3)

    def test_missing_key_is_skipped_not_zeroed(self):
        ans = {"page_type": {"type": "choice", "confidence": 1.0}}
        conf, n, _ = cascade._page_weighted_confidence(ans, ["page_type", "title_fit"])
        self.assertEqual(n, 1)
        self.assertAlmostEqual(conf, 1.0)

    def test_score_questions_excluded_from_decision(self):
        """Measured: helpfulness scores confidence 0.075 while its probability
        mass peaks on the right answer. Including it pinned savings at 0%."""
        ans = {"page_type": {"type": "choice", "confidence": 1.0},
               "helpfulness": {"type": "score", "confidence": 0.075}}
        conf, n, skipped = cascade._page_weighted_confidence(ans, ["page_type", "helpfulness"])
        self.assertEqual(n, 1)
        self.assertEqual(skipped, 1)
        self.assertAlmostEqual(conf, 1.0)

    def test_noul_questions_excluded_from_decision(self):
        """Measured: answer_first returns noul=0.297 (a "no") yet reports
        confidence 0.703 — the field points the wrong way."""
        ans = {"page_type": {"type": "choice", "confidence": 1.0},
               "answer_first": {"type": "noul", "confidence": 0.703}}
        conf, n, skipped = cascade._page_weighted_confidence(ans, ["page_type", "answer_first"])
        self.assertEqual((n, skipped), (1, 1))
        self.assertAlmostEqual(conf, 1.0)

    def test_only_score_and_noul_means_no_decision(self):
        ans = {"helpfulness": {"type": "score", "confidence": 0.99},
               "trust": {"type": "score", "confidence": 0.99}}
        conf, n, skipped = cascade._page_weighted_confidence(ans, ["helpfulness", "trust"])
        self.assertEqual((conf, n, skipped), (0.0, 0, 2))


class TestStateTokens(unittest.TestCase):
    def test_cjk_costs_more_than_ascii(self):
        zh = cascade.Cascade._state_tokens({"t": "中" * 300})
        en = cascade.Cascade._state_tokens({"t": "a" * 300})
        self.assertGreater(zh, en)

    def test_limit_detects_oversized_state(self):
        big = {"t": "中" * 4000}
        self.assertGreater(cascade.Cascade._state_tokens(big), cascade.STATE_TOKEN_LIMIT)


def _cascade(**kw):
    """A Cascade with no real engines, for decision-logic tests."""
    with mock.patch.object(cascade, "Jev"), mock.patch.object(cascade, "LayaEngine"):
        cas = cascade.Cascade(laya_enabled=False, **kw)
    return cas


class TestCascadeDecision(unittest.TestCase):
    def setUp(self):
        self.state = {"page": {"title": "t", "text": "x"}}
        self.q = {"page_type": {"type": "choice", "criteria": {"a": "x", "b": "y"}}}

    def _cas(self, laya_answers, page_accept=0.80, jev_answers=None, laya_available=True):
        cas = _cascade(page_accept=page_accept)
        cas.ledger["laya_available"] = laya_available
        cas.laya = mock.Mock()
        cas.laya.ask = mock.Mock(return_value=laya_answers)
        cas.jev = mock.Mock()
        cas.jev.available = jev_answers is not None
        cas.jev.ask = mock.Mock(return_value=jev_answers)
        cas.jev.cost = lambda: 0.0
        return cas

    def test_high_confidence_laya_decides_without_jev(self):
        ans = {"page_type": {"type": "choice", "choice": "a",
                             "probabilities": {"a": 1.0}, "confidence": 1.0}}
        cas = self._cas(ans)
        out, engine = cas.judge_page(self.state, self.q)
        self.assertEqual(engine, "laya")
        cas.jev.ask.assert_not_called()
        self.assertEqual(out["page_type"]["origin"], "laya")
        self.assertEqual(cas.ledger["accepted_by_laya"], 1)

    def test_low_confidence_escalates_to_jev(self):
        ans = {"page_type": {"type": "choice", "choice": "a",
                             "probabilities": {"a": 0.5, "b": 0.5}, "confidence": 0.4}}
        jev_ans = {"page_type": {"type": "choice", "value": "b", "probabilities": {"b": 1.0},
                                 "confidence": 0.95, "band": "act"}}
        cas = self._cas(ans, page_accept=0.80, jev_answers=jev_ans)
        out, engine = cas.judge_page(self.state, self.q)
        self.assertEqual(engine, "jev")
        cas.jev.ask.assert_called_once()
        self.assertEqual(cas.ledger["promoted"], 1)
        self.assertEqual(out["page_type"]["origin"], "jev")

    def test_low_confidence_score_does_not_block_laya(self):
        """Regression: measured helpfulness confidence was 0.075, which pinned
        savings at 0% before score/noul were excluded from the decision."""
        ans = {"page_type": {"type": "choice", "choice": "a",
                             "probabilities": {"a": 1.0}, "confidence": 1.0},
               "helpfulness": {"type": "score", "score": 2.0,
                               "probabilities": {"2": 0.42, "1": 0.30}, "confidence": 0.075}}
        q = {"page_type": {"type": "choice", "criteria": {"a": "x", "b": "y"}},
             "helpfulness": {"type": "score", "criteria": ["x", "y", "z", "w"]}}
        cas = self._cas(ans, page_accept=0.80, jev_answers=None)
        out, engine = cas.judge_page(self.state, q)
        self.assertEqual(engine, "laya")
        cas.jev.ask.assert_not_called()
        # 页级元信息挂在每道题的答案上，供报告层逐题溯源
        self.assertAlmostEqual(out["page_type"]["page_laya_confidence"], 1.0, places=3)
        self.assertEqual(out["page_type"]["laya_questions_considered"], 1)
        # score 题虽被排除出决策，仍应正常记录下来供人工参考
        self.assertIn("helpfulness", out)
        self.assertEqual(out["helpfulness"]["origin"], "laya")

    def test_laya_failure_escalates_without_retry(self):
        cas = self._cas(None, jev_answers={"page_type": {"type": "choice", "value": "a", "band": "act"}})
        _, engine = cas.judge_page(self.state, self.q)
        self.assertEqual(engine, "jev")
        self.assertEqual(cas.laya.ask.call_count, 1)
        self.assertEqual(cas.ledger["laya_skipped_error"], 1)

    def test_laya_absent_uses_jev_only(self):
        cas = self._cas(None, laya_available=False,
                        jev_answers={"page_type": {"type": "choice", "value": "a", "band": "act"}})
        _, engine = cas.judge_page(self.state, self.q)
        self.assertEqual(engine, "jev")
        cas.laya.ask.assert_not_called()

    def test_oversized_state_escalates(self):
        """Truncated input makes Laya's score meaningless, so never trust it."""
        ans = {"page_type": {"type": "choice", "choice": "a",
                             "probabilities": {"a": 1.0}, "confidence": 1.0}}
        cas = self._cas(ans, jev_answers={"page_type": {"type": "choice", "value": "a", "band": "act"}})
        out, engine = cas.judge_page({"page": {"t": "中" * 6000}}, self.q)
        self.assertEqual(engine, "jev")
        self.assertEqual(cas.ledger["promoted"], 1)

    def test_no_engine_available_returns_none(self):
        cas = self._cas(None, laya_available=False, jev_answers=None)
        out, engine = cas.judge_page(self.state, self.q)
        self.assertIsNone(out)
        self.assertEqual(engine, "jev")

    def test_jev_rejection_falls_back_to_laya(self):
        """Jev can be refused by the relay's account-level quota (HTTP 422
        with counted_tokens unrelated to the request). Leaving the page empty
        would erase it from the report; a flagged low-confidence answer is
        better than silence."""
        ans = {"page_type": {"type": "choice", "choice": "a",
                             "probabilities": {"a": 0.55, "b": 0.45}, "confidence": 0.55}}
        cas = self._cas(ans, page_accept=0.99, jev_answers=None)
        out, engine = cas.judge_page(self.state, self.q)
        self.assertEqual(engine, "laya-fallback")
        self.assertIsNotNone(out)
        self.assertTrue(out["page_type"]["laya_fallback"])
        self.assertEqual(cas.ledger["laya_fallback_pages"], 1)

    def test_no_fallback_when_laya_never_ran(self):
        cas = self._cas(None, laya_available=False, jev_answers=None)
        out, engine = cas.judge_page(self.state, self.q)
        self.assertIsNone(out)
        self.assertNotIn(engine, ("laya", "laya-fallback"))

    def test_empty_questions_short_circuits(self):
        cas = self._cas(None)
        out, engine = cas.judge_page(self.state, {})
        self.assertIsNone(out)
        self.assertEqual(engine, "none")


class TestSummary(unittest.TestCase):
    def test_no_laya_reports_jev_only(self):
        s = cascade.summarize({"laya_available": False})
        self.assertEqual(s["mode"], "jev-only")

    def test_savings_ratio(self):
        s = cascade.summarize({"laya_available": True, "accepted_by_laya": 3,
                               "promoted": 1, "laya_calls": 4, "laya_ms": 800, "laya_device": "cuda"})
        self.assertEqual(s["mode"], "cascade")
        self.assertEqual(s["laya_savings_ratio"], 0.75)
        self.assertEqual(s["laya_avg_ms"], 200.0)
        self.assertEqual(s["device"], "cuda")

    def test_zero_pages_does_not_divide_by_zero(self):
        s = cascade.summarize({"laya_available": True, "accepted_by_laya": 0, "promoted": 0,
                               "laya_calls": 0, "laya_ms": 0})
        self.assertEqual(s["laya_savings_ratio"], 0.0)
        self.assertIsNone(s["laya_avg_ms"])


class TestJevTokenBudget(unittest.TestCase):
    """A relay endpoint caps expanded_input_tokens at 32768. Measured 34417
    over 13 questions and still 33794 after batching to 8 — so questions must
    be split AND the body trimmed, with the retry driven by the 422 itself."""

    def _state(self, text_len):
        return {"page": {"text": "中" * text_len, "url": "u"}, "site": {}}

    def _jev(self):
        from jevseo import jev as J

        return J.Jev(budget_usd=0.25)

    def test_shrink_state_trims_text(self):
        from jevseo.jev import _shrink_state

        out = _shrink_state(self._state(6000), 1800)
        self.assertEqual(len(out["page"]["text"]), 1800)
        self.assertTrue(out["page"]["text_truncated"])
        self.assertEqual(out["site"], {})

    def test_shrink_state_keeps_short_text(self):
        from jevseo.jev import _shrink_state

        s = self._state(100)
        self.assertIs(_shrink_state(s, 1800), s)

    def test_shrink_state_passes_through_without_page(self):
        from jevseo.jev import _shrink_state

        s = {"site": {"name": "x"}}
        self.assertIs(_shrink_state(s, 1800), s)

    def test_retries_with_shorter_text_on_422(self):
        from jevseo import jev as J

        j = self._jev()
        j.RETRY_PAUSE_S = 0
        seen = []

        def fake(state, questions, text_chars=None):
            seen.append(text_chars if text_chars is not None else len(state["page"]["text"]))
            if text_chars is None:
                j._last_error_was_budget = True
                return None
            return {"a": {"value": 1}}

        j._ask_once = fake
        out = j._ask_resilient(self._state(6000), {"a": {}})
        self.assertIsNotNone(out)
        self.assertEqual(seen[0], 6000)
        self.assertLessEqual(seen[-1], J.Jev.TEXT_STEPS[-1])

    def test_no_retry_on_non_budget_error(self):
        j = self._jev()
        j.RETRY_PAUSE_S = 0
        calls = []

        def fake(state, questions, text_chars=None):
            calls.append(text_chars)
            j._last_error_was_budget = False
            return None

        j._ask_once = fake
        self.assertIsNone(j._ask_resilient(self._state(6000), {"a": {}}))
        self.assertEqual(len(calls), 1)

    def test_gives_up_after_the_rungs(self):
        from jevseo import jev as J

        j = self._jev()
        j.RETRY_PAUSE_S = 0
        calls = []

        def fake(state, questions, text_chars=None):
            calls.append(text_chars)
            j._last_error_was_budget = True
            return None

        j._ask_once = fake
        self.assertIsNone(j._ask_resilient(self._state(6000), {"a": {}}))
        self.assertEqual(len(calls), len(J.Jev.TEXT_STEPS))

    def test_short_page_is_not_retried_pointlessly(self):
        """A 500-char page has nothing left to trim, so stop after one try."""
        j = self._jev()
        j.RETRY_PAUSE_S = 0
        calls = []

        def fake(state, questions, text_chars=None):
            calls.append(text_chars)
            j._last_error_was_budget = True
            return None

        j._ask_once = fake
        self.assertIsNone(j._ask_resilient(self._state(500), {"a": {}}))
        self.assertEqual(len(calls), 1)

    def test_budget_errors_are_classified_as_retryable(self):
        """Only 422 token errors should trigger the retry ladder. An auth or
        network error must fail fast instead of burning five more requests."""
        from jevseo import jev as J

        j = self._jev()
        j.key = "test"
        seen_budget = []

        def fake_post(url, data=None, headers=None, timeout=None):
            # 让 requests.post 抛一个 422
            raise RuntimeError(
                'HTTP 422: {"detail":{"code":"token_budget_exceeded","limit_tokens":32768}}')

        with mock.patch.object(J.requests, "post", fake_post):
            out = j._ask_once(self._state(100), {"a": {}})
        self.assertIsNone(out)
        seen_budget.append(j._last_error_was_budget)
        self.assertTrue(seen_budget[0])
        self.assertEqual(j.ledger.get("budget_retries"), 1)

    def test_non_budget_errors_are_not_retryable(self):
        from jevseo import jev as J

        j = self._jev()
        j.key = "test"

        def fake_post(url, data=None, headers=None, timeout=None):
            raise RuntimeError('HTTP 401: {"detail":{"error_type":"authentication_error"}}')

        with mock.patch.object(J.requests, "post", fake_post):
            out = j._ask_once(self._state(100), {"a": {}})
        self.assertIsNone(out)
        self.assertFalse(j._last_error_was_budget)
        self.assertIsNone(j.ledger.get("budget_retries"))


class TestJevBatching(unittest.TestCase):
    """Measured against the relay: 2 questions succeed (32629 input tokens),
    3+ fail with 422, and counted_tokens stays 34417 regardless of how many
    questions are sent — the cap is account-level, not per-request. So batches
    are small and serial, with a pause between them."""

    def _jev(self, max_questions):
        from jevseo import jev as J

        with mock.patch.object(J.Jev, "_ask_once", return_value=None):
            j = J.Jev(budget_usd=0.25)
        j.max_questions = max_questions
        j.BATCH_PAUSE_S = 0
        return j

    def test_default_is_two_questions(self):
        """The measured ceiling, not a guess."""
        from jevseo import jev as J

        self.assertEqual(J.Jev.DEFAULT_MAX_QUESTIONS, 2)

    def test_below_limit_makes_one_call(self):
        j = self._jev(max_questions=2)
        j._ask_once = mock.Mock(return_value={"a": 1})
        q = {f"k{i}": {} for i in range(2)}
        self.assertEqual(j.ask({}, q), {"a": 1})
        self.assertEqual(j._ask_once.call_count, 1)

    def test_above_limit_splits_and_merges(self):
        j = self._jev(max_questions=2)
        seen = []

        def fake(state, chunk, text_chars=None):
            seen.append(list(chunk))
            return {k: k for k in chunk}

        j._ask_once = fake
        q = {f"k{i}": {} for i in range(5)}
        out = j.ask({}, q)
        self.assertEqual([len(s) for s in seen], [2, 2, 1])
        self.assertEqual(out, {f"k{i}": f"k{i}" for i in range(5)})

    def test_one_failed_batch_fails_the_whole_call(self):
        j = self._jev(max_questions=2)
        calls = []

        def fake(state, chunk, text_chars=None):
            calls.append(len(chunk))
            j._last_error_was_budget = False
            return None if len(calls) == 2 else {k: 1 for k in chunk}

        j._ask_once = fake
        self.assertIsNone(j.ask({}, {f"k{i}": {} for i in range(4)}))
        self.assertEqual(len(calls), 2)

    def test_batches_are_serial_with_a_pause(self):
        """Concurrent batches compete for the same account quota."""
        import time as _time

        from jevseo import jev as J

        j = self._jev(max_questions=2)
        j.BATCH_PAUSE_S = 0.05
        order = []

        def fake(state, chunk, text_chars=None):
            order.append(("start", tuple(chunk)))
            _time.sleep(0.01)
            order.append(("end", tuple(chunk)))
            return {k: 1 for k in chunk}

        j._ask_once = fake
        j.ask({}, {f"k{i}": {} for i in range(4)})
        starts = [i for i, (kind, _) in enumerate(order) if kind == "start"]
        ends = [i for i, (kind, _) in enumerate(order) if kind == "end"]
        # 每个 start 之前必须已有上一批的 end，证明串行
        self.assertEqual(len(starts), 2)
        self.assertTrue(ends[0] < starts[1])

    def test_batching_disabled_when_zero(self):
        j = self._jev(max_questions=0)
        j._ask_once = mock.Mock(return_value={"a": 1})
        j.ask({}, {f"k{i}": {} for i in range(20)})
        self.assertEqual(j._ask_once.call_count, 1)


class TestShrinkForLaya(unittest.TestCase):
    """Laya's context is ~1024 tokens while Jev's is generous. Without the
    shrink hook every real Chinese page measured 1000-1546 tokens and was
    escalated, pinning the savings ratio at 0%."""

    def _state(self, text_len):
        from jevseo.cli import _shrink_for_laya
        from jevseo.jev import PAGE_TEXT_CHARS_LOCAL

        state = {"site": {"name": "s"},
                 "page": {"text": "中" * text_len, "outline": ["a"] * 40,
                          "calls_to_action": ["b"] * 20, "text_truncated": False}}
        return _shrink_for_laya(state, {"q": 1}), PAGE_TEXT_CHARS_LOCAL

    def test_text_is_trimmed(self):
        (shrunk, _), limit = self._state(6000)
        self.assertEqual(len(shrunk["page"]["text"]), limit)
        self.assertTrue(shrunk["page"]["text_truncated"])

    def test_short_text_is_left_alone(self):
        (shrunk, _), _ = self._state(50)
        self.assertEqual(len(shrunk["page"]["text"]), 50)
        self.assertFalse(shrunk["page"]["text_truncated"])

    def test_lists_are_capped(self):
        (shrunk, _), _ = self._state(100)
        self.assertEqual(len(shrunk["page"]["outline"]), 12)
        self.assertEqual(len(shrunk["page"]["calls_to_action"]), 8)

    def test_other_keys_survive(self):
        from jevseo.cli import _shrink_for_laya

        state = {"site": {"name": "s"}, "page": {"text": "x", "outline": [], "calls_to_action": []}}
        shrunk, questions = _shrink_for_laya(state, {"q": 1})
        self.assertEqual(shrunk["site"], {"name": "s"})
        self.assertEqual(questions, {"q": 1})

    def test_shrunk_state_fits_the_limit(self):
        from jevseo.cascade import STATE_TOKEN_LIMIT, Cascade

        (shrunk, _), _ = self._state(6000)
        self.assertLessEqual(Cascade._state_tokens(shrunk), STATE_TOKEN_LIMIT)

    def test_state_without_page_passes_through(self):
        from jevseo.cli import _shrink_for_laya

        state = {"site": {"name": "s"}}
        self.assertEqual(_shrink_for_laya(state, {}), (state, {}))


class TestValidateLocal(unittest.TestCase):
    """Laya returns continuous scores (measured 1.584 on a 0-3 scale);
    jev.validate rejects out-of-range, so the local path must clamp."""

    def test_continuous_score_is_accepted(self):
        from jevseo.cli import validate_local

        q = {"type": "score", "criteria": ["a", "b", "c", "d"]}
        a = {"score": 1.584, "probabilities": {"1": 0.42, "2": 0.27}, "confidence": 0.07}
        out = validate_local(q, a)
        self.assertEqual(out["score_raw"], 1.584)
        self.assertEqual(out["levels"], 4)
        self.assertGreaterEqual(out["value"], 0.0)
        self.assertLessEqual(out["value"], 1.0)

    def test_out_of_range_score_is_clamped(self):
        from jevseo.cli import validate_local

        q = {"type": "score", "criteria": ["a", "b", "c", "d"]}
        out = validate_local(q, {"score": 9.9, "probabilities": {}, "confidence": 0.5})
        self.assertEqual(out["value"], 1.0)
        self.assertEqual(out["score_raw"], 9.9)

    def test_noul_confidence_is_flagged_unreliable(self):
        """Measured: noul=0.297 (a "no") came back with confidence 0.703.
        The value stays usable; the confidence must be marked untrustworthy."""
        from jevseo.cli import validate_local

        out = validate_local({"type": "noul", "criteria": {"true": "y", "false": "n"}},
                             {"noul": 0.2967, "confidence": 0.7033})
        self.assertEqual(out["value"], 0.2967)
        self.assertTrue(out["laya_confidence_unreliable"])
        # recomputed as distance from 0.5, not the model's own 0.703
        self.assertAlmostEqual(out["confidence"], abs(0.2967 - 0.5) * 2, places=3)

    def test_score_without_probabilities_is_forced_to_review(self):
        from jevseo.cli import validate_local

        out = validate_local({"type": "score", "criteria": ["a", "b", "c", "d"]},
                             {"score": 3.0, "confidence": 0.99})
        self.assertEqual(out["band"], "review")

    def test_origin_is_preserved_through_band_logic(self):
        from jevseo.cli import validate_local

        q = {"type": "score", "criteria": ["a", "b", "c", "d"]}
        out = validate_local(q, {"score": 3.0, "probabilities": {"3": 0.95, "2": 0.05},
                                 "confidence": 0.9})
        self.assertEqual(out["band"], "act")
        out["origin"] = "laya"
        self.assertEqual(out["origin"], "laya")

    def test_noul_and_choice_pass_through(self):
        from jevseo.cli import validate_local

        n = validate_local({"type": "noul", "criteria": {"true": "y", "false": "n"}}, {"noul": 0.85})
        self.assertEqual(n["band"], "yes")
        c = validate_local({"type": "choice", "criteria": {"a": "x", "b": "y"}},
                           {"choice": "a", "probabilities": {"a": 1.0}, "confidence": 1.0})
        self.assertEqual(c["value"], "a")
        self.assertEqual(c["band"], "act")


class TestEngineLabel(unittest.TestCase):
    def test_laya_only_is_disclosed(self):
        from jevseo.score import _engine_label

        judged = {"cascade": {"mode": "laya-only"},
                  "pages": {"u": {"page_type": {"origin": "laya"}}}}
        self.assertIn("Laya", _engine_label(judged))
        self.assertIn("proxy", _engine_label(judged))

    def test_mixed_origins_are_disclosed(self):
        from jevseo.score import _engine_label

        judged = {"cascade": {"mode": "cascade"},
                  "pages": {"u1": {"page_type": {"origin": "laya"}},
                            "u2": {"page_type": {"origin": "jev"}}}}
        self.assertIn("escalation", _engine_label(judged))

    def test_code_origin_is_not_an_engine(self):
        from jevseo.score import _engine_label

        judged = {"cascade": {"mode": "cascade"},
                  "pages": {"u": {"page_type": {"origin": "code"}}}}
        self.assertEqual(_engine_label(judged), "semantic judgment")


if __name__ == "__main__":
    unittest.main()
