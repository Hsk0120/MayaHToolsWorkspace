"""公開前後のQPE文書をブラウザーで確認し、リンク切れ・横溢れ・古い配信を検出する。"""

import argparse
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urljoin, urlsplit

from playwright.sync_api import sync_playwright


PAGES = ("index", "install", "browsing", "files", "maya", "preferences",
         "shortcuts", "development", "troubleshooting")


class Links(HTMLParser):
    """HTML内のローカル参照先とアンカーを集める。"""

    def __init__(self):
        """解析先ごとに状態を分ける。"""
        super().__init__()
        self.targets = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        """リンクと資源のURLを記録する。"""
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for key in ("href", "src"):
            if values.get(key):
                self.targets.append(values[key])


def check_links(directory):
    """生成HTMLの相対参照とアンカーを全件検査する。"""
    parsed = {}
    for path in directory.rglob("*.html"):
        document = Links()
        document.feed(path.read_text(encoding="utf-8"))
        parsed[path.resolve()] = document
    if not parsed:
        raise ValueError("生成済みHTMLがありません。")
    for path, document in parsed.items():
        for target in document.targets:
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            destination = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if destination.is_dir():
                destination /= "index.html"
            if not destination.is_relative_to(directory) or not destination.is_file():
                raise ValueError(f"ローカル参照先がありません: {path.name}: {target}")
            if parts.fragment and destination in parsed and unquote(parts.fragment) not in parsed[destination].ids:
                raise ValueError(f"アンカーがありません: {path.name}: {target}")
    return len(parsed)


def check_browser(base_url, output, sha, channel):
    """PC・タブレット・スマートフォン幅で実ページと検索を確認する。"""
    records = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**({"channel": channel} if channel else {}))
        try:
            for name, width, height in (("desktop", 1440, 1000), ("tablet", 834, 1112), ("mobile", 390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
                page = context.new_page()
                page.set_default_timeout(20000)
                page.set_default_navigation_timeout(20000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                for document in PAGES:
                    print(f"Checking {name}: {document}", flush=True)
                    response = page.goto(urljoin(base_url, document + ".html"), wait_until="networkidle")
                    if response is None or response.status != 200:
                        raise ValueError(f"ページ取得失敗: {page.url}")
                    page.locator("div.body h1").wait_for()
                    if sha and page.locator('meta[name="qpe-build-revision"]').get_attribute("content") != sha:
                        raise ValueError(f"公開コミットが一致しません: {page.url}")
                    if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                        if output:
                            page.screenshot(path=str(output / f"{name}-{document}-overflow.png"), full_page=True)
                        raise ValueError(f"ページ全体が横にはみ出しています: {name}: {page.url}")
                    accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hd-accent').trim()")
                    if accent != "#42bdc7":
                        raise ValueError(f"QPEの配色が読み込まれていません: {page.url}")
                    if document in ("index", "browsing"):
                        asset = "qpe-columns.gif" if document == "index" else "qpe-wide.png"
                        media = page.locator(f'div.body img[src*="{asset}"]')
                        media.wait_for()
                        if not media.evaluate("image => image.complete && image.naturalWidth >= 1400"):
                            raise ValueError(f"ワイドな実画面の画像を読み込めません: {page.url}")
                        if not page.locator(f'div.body a[href*="{asset}"]').count():
                            raise ValueError(f"原寸画像へのリンクがありません: {page.url}")
                    records.append({"viewport": name, "page": document, "status": response.status})
                    if output and document in ("index", "preferences"):
                        page.screenshot(path=str(output / f"{name}-{document}.png"), full_page=True)
                # 実リンクから設定へ移動し、Sphinx検索の索引と結果リンクも使う。
                page.goto(base_url, wait_until="networkidle")
                page.locator('div.body a[href="preferences.html"]').first.click()
                page.wait_for_url("**/preferences.html")
                page.goto(urljoin(base_url, "search.html"), wait_until="networkidle")
                query = page.locator('div.body input[name="q"]')
                query.fill("FBX")
                query.press("Enter")
                page.locator('#search-results a[href*="maya.html"]').first.wait_for(timeout=20000)
                page.locator('#search-results a[href*="maya.html"]').first.click()
                page.wait_for_url("**/maya.html*")
                context.close()
        finally:
            browser.close()
    if errors:
        raise ValueError("ブラウザー例外: " + "; ".join(errors))
    return records


def main():
    """ローカル生成物または公開URLを検証し、必要なら証拠を保存する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--url")
    parser.add_argument("--sha", help="ビルド時のGITHUB_SHAと照合する。ローカルでは省略可")
    parser.add_argument("--output", type=Path, help="スクリーンショットと結果JSONの専用出力先")
    parser.add_argument("--browser-channel", help="ローカル検証で既存Chrome等を使う場合のchannel")
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    server = None
    result = {"status": "failed"}
    try:
        if args.directory:
            directory = args.directory.resolve(strict=True)
            result["checked_html"] = check_links(directory)
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
            Thread(target=server.serve_forever, daemon=True).start()
            base_url = f"http://127.0.0.1:{server.server_port}/"
        else:
            base_url = args.url.rstrip("/") + "/"
            if urlsplit(base_url).scheme not in ("http", "https"):
                raise ValueError("--urlにはHTTPまたはHTTPSの文書URLを指定してください。")
        result["records"] = check_browser(base_url, args.output, args.sha, args.browser_channel)
        result["status"] = "passed"
        print(f"QPE docs: {len(result['records'])} page/viewport checks, navigation and search passed")
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if args.output:
            (args.output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
