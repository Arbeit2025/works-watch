# -*- coding: utf-8 -*-
"""
works-watch（Works見守りボード）

公開中の自作作品サイト（固定リスト16件）について、死活（HTTPステータス）と
応答時間を一括チェックして表で見せるツール。単一ファイル Flask、DB なし。

目次
  1. 監視対象（定数）
  2. チェック処理（取得・分類・並行実行）
  3. 画面テンプレート
  4. ルート
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, render_template_string

app = Flask(__name__)

JST = ZoneInfo("Asia/Tokyo")
USER_AGENT = "works-watch/1.0 (+https://github.com/Arbeit2025/works-watch)"
TIMEOUT_SECONDS = 30

# ==============================
# 1. 監視対象（定数）
# ==============================

TARGETS = [
    ("Studylog", "https://studylog1.onrender.com/"),
    ("自作ミニゲーム集", "https://minigame-b1qp.onrender.com/"),
    ("Coco's Letter", "https://cocoletter2.onrender.com/"),
    ("Cocoa Button", "https://cocobutton.onrender.com/"),
    ("Cocoa Mascot", "https://cocoweb.onrender.com/"),
    ("cocotime", "https://cocotime.onrender.com/"),
    ("speedpicture", "https://speedpicture.onrender.com/"),
    ("accountnamemaker", "https://accountnamemaker.onrender.com/"),
    ("videodownloader", "https://videodownloader-ycw2.onrender.com/"),
    ("voice8bit", "https://voice8bit.onrender.com/"),
    ("subtitletranslate", "https://subtitletranslate.onrender.com/"),
    ("linesmaker", "https://linesmaker.onrender.com/"),
    ("studystats", "https://studystats-wxrk.onrender.com/"),
    ("passcheck", "https://passcheck-8e93.onrender.com/"),
    ("githubreport", "https://githubreport.onrender.com/"),
    ("mywebsite", "https://arbeit2025.github.io/mywebsite/"),
]

# ==============================
# 2. チェック処理（取得・分類・並行実行）
# ==============================


def fetch_status(url: str, timeout: int = TIMEOUT_SECONDS) -> tuple[int | None, int, str | None]:
    """URL を取得し、(HTTPコード, 応答ミリ秒, エラー文字列) を返す。

    到達できない場合は HTTPコード=None とし、エラー文字列に理由を入れる。
    HTTPエラーレスポンス（4xx/5xx）はコードとして返す（到達はしている）。
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1024)
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # タイムアウト・接続エラー・DNS失敗など
        elapsed = int((time.monotonic() - start) * 1000)
        return None, elapsed, f"{type(e).__name__}: {e}"
    elapsed = int((time.monotonic() - start) * 1000)
    return code, elapsed, None


def classify(code: int | None, error: str | None) -> str:
    """HTTPコードとエラーから状態ラベルを返す。"""
    if error is not None or code is None:
        return "到達不可"
    if 200 <= code < 400:
        return "OK"
    return "異常"


def check_one(target: tuple[str, str], fetcher=fetch_status, now: datetime | None = None) -> dict:
    """1件分のチェック結果 dict を返す。fetcher は差し替え可能（テスト用）。"""
    name, url = target
    code, elapsed_ms, error = fetcher(url)
    checked = (now if now is not None else datetime.now(JST)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "name": name,
        "url": url,
        "status": classify(code, error),
        "code": code,
        "elapsed_ms": elapsed_ms,
        "error": error,
        "checked_at": checked,
    }


def run_checks(targets=TARGETS, fetcher=fetch_status, now: datetime | None = None) -> list[dict]:
    """全対象を並行チェックし、対象リストの順序どおりに結果を返す。"""
    checked_now = now if now is not None else datetime.now(JST)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda t: check_one(t, fetcher=fetcher, now=checked_now), targets))
    return results


# ==============================
# 3. 画面テンプレート
# ==============================

PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Works見守りボード｜works-watch</title>
<style>
  body { font-family: "Hiragino Sans", sans-serif; background: #f4f7fb;
         color: #2d3748; margin: 0; padding: 24px 12px 48px; }
  .card { max-width: 880px; margin: 0 auto 20px; background: #fff; border-radius: 14px;
          box-shadow: 0 2px 10px rgba(60,90,140,.12); padding: 20px 22px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #718096; font-size: 13px; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { border-bottom: 1px solid #e2e8f0; padding: 8px 6px; text-align: left;
           vertical-align: top; }
  th { color: #4a6fa5; font-size: 12px; }
  a { color: #2b6cb0; }
  button { font-size: 15px; padding: 10px 22px; border: 0; border-radius: 999px;
           background: #2b6cb0; color: #fff; cursor: pointer; margin-top: 14px; }
  .ok { color: #22733c; font-weight: bold; }
  .ng { color: #b7791f; font-weight: bold; }
  .down { color: #c53030; font-weight: bold; }
  .note { font-size: 12px; color: #718096; margin-top: 12px; line-height: 1.7; }
  .err { font-size: 11px; color: #a0aec0; }
</style>
</head>
<body>
  <div class="card">
    <h1>🛰️ Works見守りボード</h1>
    <div class="sub">公開中の作品サイト {{ targets|length }} 件の死活と応答時間をまとめて確認できます。</div>
    <table>
      <tr><th>名前</th><th>URL</th></tr>
      {% for name, url in targets %}
      <tr><td>{{ name }}</td><td><a href="{{ url }}" target="_blank" rel="noopener">{{ url }}</a></td></tr>
      {% endfor %}
    </table>
    <form method="post" action="/check">
      <button type="submit">✅ チェック実行</button>
    </form>
    <div class="note">
      ※ Render Free プランは無通信時にスリープし、初回応答が遅くなったり、
      一時的に「到達不可」になったりすることがあります。少し待ってから開き直すと
      起動して表示される場合があります。「到達不可」が即障害とは限りません。
    </div>
  </div>
  {% if results is not none %}
  <div class="card">
    <h1 style="font-size:18px;">チェック結果</h1>
    <table>
      <tr><th>名前</th><th>状態</th><th>HTTP</th><th>応答時間</th><th>チェック時刻（JST）</th></tr>
      {% for r in results %}
      <tr>
        <td><a href="{{ r.url }}" target="_blank" rel="noopener">{{ r.name }}</a></td>
        <td class="{{ 'ok' if r.status == 'OK' else ('ng' if r.status == '異常' else 'down') }}">{{ r.status }}{% if r.error %}<div class="err">{{ r.error }}</div>{% endif %}</td>
        <td>{{ r.code if r.code is not none else '—' }}</td>
        <td>{{ r.elapsed_ms }} ms</td>
        <td>{{ r.checked_at }}</td>
      </tr>
      {% endfor %}
    </table>
    <div class="note">OK = 2xx・3xx ／ 異常 = それ以外のコード ／ 到達不可 = タイムアウト・接続エラー（Render Free のスリープの可能性あり）</div>
  </div>
  {% endif %}
</body>
</html>
"""

# ==============================
# 4. ルート
# ==============================


@app.route("/", methods=["GET"])
def index():
    return render_template_string(PAGE, targets=TARGETS, results=None)


@app.route("/check", methods=["POST"])
def check():
    results = run_checks(fetcher=fetch_status)
    return render_template_string(PAGE, targets=TARGETS, results=results)


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
