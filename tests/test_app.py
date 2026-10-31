# -*- coding: utf-8 -*-
"""works-watch のテスト。HTTP取得はモックし、実ネットワークには出ない。"""

import importlib.util
import os
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

BASE = os.path.join(os.path.dirname(__file__), "..")


def load_module():
    spec = importlib.util.spec_from_file_location("works_watch_app", os.path.join(BASE, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = load_module()
JST = ZoneInfo("Asia/Tokyo")


def fake_fetcher_factory(mapping):
    """URLごとの (code, ms, error) を返すフェイク取得関数を作る。"""

    def fake(url, timeout=30):
        return mapping[url]

    return fake


class TestClassify(unittest.TestCase):
    def test_ok_2xx(self):
        self.assertEqual(mod.classify(200, None), "OK")

    def test_ok_3xx(self):
        self.assertEqual(mod.classify(302, None), "OK")

    def test_ng_404(self):
        self.assertEqual(mod.classify(404, None), "異常")

    def test_ng_500(self):
        self.assertEqual(mod.classify(500, None), "異常")

    def test_unreachable_on_error(self):
        self.assertEqual(mod.classify(None, "URLError: timed out"), "到達不可")


class TestCheckFunctions(unittest.TestCase):
    def test_targets_count(self):
        self.assertEqual(len(mod.TARGETS), 16)

    def test_run_checks_with_mock(self):
        mapping = {url: (200, 123, None) for _, url in mod.TARGETS}
        fake = fake_fetcher_factory(mapping)
        now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=JST)
        results = mod.run_checks(fetcher=fake, now=now)
        self.assertEqual(len(results), 16)
        self.assertTrue(all(r["status"] == "OK" for r in results))
        self.assertTrue(all(r["code"] == 200 for r in results))
        self.assertTrue(all(r["elapsed_ms"] == 123 for r in results))
        self.assertEqual(results[0]["checked_at"], "2026-10-31 12:00:00")
        # 対象リストの順序が保たれること
        self.assertEqual([r["name"] for r in results], [n for n, _ in mod.TARGETS])

    def test_run_checks_mixed(self):
        mapping = {url: (200, 10, None) for _, url in mod.TARGETS}
        mapping[mod.TARGETS[0][1]] = (503, 20, None)
        mapping[mod.TARGETS[1][1]] = (None, 30000, "URLError: timed out")
        results = mod.run_checks(fetcher=fake_fetcher_factory(mapping))
        self.assertEqual(results[0]["status"], "異常")
        self.assertEqual(results[1]["status"], "到達不可")
        self.assertIsNone(results[1]["code"])


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.client = mod.app.test_client()

    def test_index_lists_targets(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Works見守りボード", body)
        self.assertIn("チェック実行", body)
        for name, url in mod.TARGETS:
            self.assertIn(url, body)
        self.assertIn("スリープ", body)  # Freeプランの注意書き

    def test_check_results_rendered(self):
        mapping = {url: (200, 42, None) for _, url in mod.TARGETS}
        fake = fake_fetcher_factory(mapping)
        with mock.patch.object(mod, "fetch_status", fake):
            resp = self.client.post("/check")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("チェック結果", body)
        self.assertIn("OK", body)
        self.assertIn("42 ms", body)

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
