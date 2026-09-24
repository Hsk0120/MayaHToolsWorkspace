"""Sphinx生成物と公開済みPagesを、Chromiumで検証するCI用スクリプト。"""

import argparse
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.parse import urljoin

CASES = [
    ("autoapi/hlib/nodes/joint/Joint.html", "hlib.nodes.transform.Transform"),
    ("autoapi/hlib/nodes/animCurve/AnimCurve.html", "hlib.nodes.animCurveTA.AnimCurveTA"),
    ("autoapi/hlib/maths/matrix/Matrix.html", "hlib.maths.matrix.Matrix"),
    ("development.html", "hlib.nodes.node.Node"),
]
ASSETS = ["_static/mermaid.min.js", "_static/mermaid-init.js"]


def stamp(directory, sha):
    paths = sorted({path for path, _ in CASES} | set(ASSETS))
    payload = {"commit": sha, "files": {
        path: hashlib.sha256((directory / path).read_bytes()).hexdigest()
        for path in paths
    }}
    (directory / "build-info.json").write_text(json.dumps(payload), encoding="utf-8")


def wait_for_release(base, sha, timeout):
    """公開反映の遅延を有限時間リトライ。HTML/JSも同じ生成物であることを確認。"""
    deadline = time.monotonic() + timeout
    last_error = None
    while True:
        try:
            def fetch(path):
                url = urljoin(base, path) + f"?revision={sha}&check={time.time_ns()}"
                request = Request(url, headers={"Cache-Control": "no-cache"})
                with urlopen(request, timeout=20) as response:
                    return response.read()
            info = json.loads(fetch("build-info.json"))
            if info["commit"] != sha:
                raise ValueError(f"Expected {sha}, got {info['commit']}")
            for path, digest in info["files"].items():
                if hashlib.sha256(fetch(path)).hexdigest() != digest:
                    raise ValueError(f"Old or inconsistent published file: {path}")
            return
        except Exception as error:
            last_error = error
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Publication verification failed: {last_error}") from error
            print(f"Waiting for publication: {error}", flush=True)
            time.sleep(10)


def check_browser(base, output):
    from playwright.sync_api import sync_playwright, expect

    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for label, options in [
                ("desktop", {"viewport": {"width": 1440, "height": 1000}}),
                ("mobile", {"viewport": {"width": 390, "height": 844},
                            "is_mobile": True, "has_touch": True}),
            ]:
                context = browser.new_context(**options)
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    for index, (source, destination) in enumerate(CASES):
                        response = page.goto(urljoin(base, source), wait_until="networkidle")
                        assert response and response.ok, f"Cannot open {source}"
                        expect(page.locator(".mermaid svg").first).to_be_visible(timeout=30000)
                        # SVGの実リンクをクリックする。テキストソースのURL検査だけでは済ませない。
                        links = page.locator(".mermaid svg a")
                        expect(links.first).to_be_attached(timeout=30000)
                        chosen = None
                        for i in range(links.count()):
                            candidate = links.nth(i)
                            href = candidate.get_attribute("href") or candidate.get_attribute("xlink:href")
                            if href and href.endswith("#" + destination):
                                chosen = candidate
                                break
                        assert chosen is not None, f"Missing SVG link: {source} -> {destination}"
                        chosen.scroll_into_view_if_needed()
                        page.screenshot(path=str(output / f"{label}-{index}.png"))
                        if chosen.get_attribute("target") == "_blank":
                            with page.expect_popup() as popup:
                                chosen.click()
                            landed = popup.value
                            landed.wait_for_load_state()
                        else:
                            chosen.click()
                            landed = page
                        expect(landed).to_have_url(re.compile(re.escape("#" + destination) + "$"))
                        expect(landed.locator('[id="' + destination + '"]')).to_be_visible()
                        if landed is not page:
                            landed.close()
                        assert not errors, errors
                        print(f"PASS {label}: {source} -> {destination}", flush=True)
                except Exception:
                    page.screenshot(path=str(output / f"{label}-failure.png"), full_page=True)
                    raise
                finally:
                    context.tracing.stop(path=str(output / f"{label}-trace.zip"))
                    context.close()
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--directory", type=Path)
    target.add_argument("--url")
    target.add_argument("--stamp-directory", type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path, default=Path(".maya-output/docs-browser"))
    args = parser.parse_args()
    if args.stamp_directory:
        stamp(args.stamp_directory, args.sha)
        return
    server = None
    try:
        if args.directory:
            handler = functools.partial(SimpleHTTPRequestHandler, directory=str(args.directory.resolve()))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}/"
        else:
            base = args.url.rstrip("/") + "/"
        wait_for_release(base, args.sha, args.timeout)
        check_browser(base, args.output)
        message = f"Verified commit {args.sha}: publication files and 8 Chromium click cases passed."
        print(message)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
                summary.write(message + "\n")
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # CIの公開チェックにも原因を残し、ログ権限がない場合にも診断できるようにする。
        message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Documentation browser verification::{message}", flush=True)
        raise
