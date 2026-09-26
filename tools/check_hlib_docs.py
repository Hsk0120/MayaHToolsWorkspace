"""Sphinx生成物と公開済みPagesを、Chromiumで検証するCI用スクリプト。"""

import argparse
import ast
import base64
import binascii
import functools
import hashlib
from html.parser import HTMLParser
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
ASSETS = ["_static/mermaid-init.js", "_static/custom.css", "_static/mermaid.css"]
# Mermaid本体はリポジトリに同梱せず、版を固定したjsDelivrのURLからSRI付きで読み込む。
# 固定した版とハッシュの正は docs/conf.py の _MERMAID_URL と _MERMAID_SRI。
DOCS_CONF = Path(__file__).resolve().parent.parent / "maya" / "inhouse" / "hlib" / "docs" / "conf.py"
MERMAID_CDN_SCRIPT = re.compile(
    r"^https://cdn\.jsdelivr\.net/npm/mermaid@\d+\.\d+\.\d+/dist/mermaid\.min\.js$"
)
MERMAID_INIT_SCRIPT = "mermaid-init.js"


def _string_constant(node, known):
    """代入の右辺が文字列として確定できればその値を、できなければNoneを返す。

    文字列リテラル、既に読んだ名前、それらだけを埋め込んだf文字列に対応する。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return known.get(node.id)
    if isinstance(node, ast.FormattedValue) and node.conversion == -1 and node.format_spec is None:
        return _string_constant(node.value, known)
    if isinstance(node, ast.JoinedStr):
        parts = [_string_constant(part, known) for part in node.values]
        if None not in parts:
            return "".join(parts)
    return None


def read_mermaid_pin(conf_path=DOCS_CONF):
    """docs/conf.py で固定したMermaid本体のURLとSRIを、conf.pyを実行せずに読み取る。

    conf.py はSphinx拡張をimportするため、ブラウザ検証だけを行う環境
    (公開後の確認ジョブ)でも使えるよう、構文木からモジュール直下の文字列定数だけを求める。

    Returns:
        dict: ``src`` (版を固定したCDNのURL)と ``integrity`` (``sha384-`` で始まるSRI)。
    """
    tree = ast.parse(conf_path.read_text(encoding="utf-8"), filename=str(conf_path))
    known = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                value = _string_constant(statement.value, known)
                if value is not None:
                    known[target.id] = value
    pin = {"src": known.get("_MERMAID_URL"), "integrity": known.get("_MERMAID_SRI")}
    assert pin["src"] and pin["integrity"], f"{conf_path}: _MERMAID_URL / _MERMAID_SRI not found"
    assert MERMAID_CDN_SCRIPT.match(pin["src"]), f"{conf_path}: Mermaid URL is not an exact jsDelivr version: {pin['src']}"
    algorithm, _, digest = pin["integrity"].partition("-")
    try:
        digest_size = len(base64.b64decode(digest, validate=True))
    except binascii.Error:
        digest_size = 0
    assert algorithm == "sha384" and digest_size == hashlib.sha384().digest_size, (
        f"{conf_path}: _MERMAID_SRI must be one sha384 digest in base64: {pin['integrity']}")
    return pin


def _is_mermaid_engine(src):
    """初期化用の mermaid-init.js 以外で、Mermaid を含むscriptを本体とみなす。"""
    return "mermaid" in src and MERMAID_INIT_SCRIPT not in src


def _check_script_list(scripts, pin, source):
    """1ページ分のscript属性の並びが、固定したMermaid本体の読み込み方どおりか確かめる。"""
    engines = [index for index, script in enumerate(scripts) if _is_mermaid_engine(script.get("src") or "")]
    assert len(engines) == 1, f"{source}: expected one Mermaid script, got {[scripts[i] for i in engines]}"
    engine = scripts[engines[0]]
    assert engine.get("src") == pin["src"], f"{source}: Mermaid URL differs from docs/conf.py: {engine.get('src')}"
    assert engine.get("integrity") == pin["integrity"], (
        f"{source}: Mermaid SRI differs from docs/conf.py: {engine.get('integrity')}")
    assert engine.get("crossorigin") == "anonymous", f"{source}: Mermaid script needs crossorigin=anonymous"
    # どちらも defer なので記述順に実行される。初期化が本体より先だと図が描かれない。
    initializers = [index for index, script in enumerate(scripts)
                    if MERMAID_INIT_SCRIPT in (script.get("src") or "")]
    assert initializers and min(initializers) > engines[0], (
        f"{source}: {MERMAID_INIT_SCRIPT} must be loaded after the Mermaid script")


class _ScriptTags(HTMLParser):
    """HTML中のscript要素の属性を、出現順に集める。"""

    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append({name: value for name, value in attrs})


def check_built_html(directory, pin):
    """ビルド済みHTMLを、ブラウザもネットワークも使わずに検査する。

    - Mermaid本体(mermaid.min.js など)がビルド出力に含まれていないこと。
      以前のビルドの残りがあると、同梱をやめた本体を配布してしまうため。
    - Mermaidを使う各ページが、docs/conf.py で固定したURL・SRIどおりに本体を1回だけ読み込み、
      その後に初期化スクリプトを読み込んでいること。

    Returns:
        int: 検査したHTMLページ数。
    """
    directory = Path(directory)
    bundled = sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("mermaid*")
        if path.is_file() and path.suffix in {".js", ".mjs"} and path.name != MERMAID_INIT_SCRIPT
    )
    assert not bundled, f"Mermaid must not be bundled in the build output (stale build?): {bundled}"
    checked = set()
    for path in sorted(directory.rglob("*.html")):
        parser = _ScriptTags()
        parser.feed(path.read_text(encoding="utf-8"))
        source = path.relative_to(directory).as_posix()
        if any("mermaid" in (script.get("src") or "") for script in parser.scripts):
            _check_script_list(parser.scripts, pin, source)
            checked.add(source)
    missing = sorted({source for source, _ in CASES} - checked)
    assert not missing, f"Pages with class diagrams do not load Mermaid: {missing}"
    return len(checked)


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


def check_mermaid_script(page, source, pin):
    """表示中のページが、docs/conf.py で固定したURL・SRIどおりにMermaid本体を読み込んでいるか確かめる。

    ブラウザはintegrityの値と取得したファイルが一致しない場合に実行を拒否するため、
    この後の図の描画確認と合わせて、固定した版・ハッシュどおりに動いていることを保証する。
    """
    scripts = page.evaluate("""() => Array.from(document.scripts, script => ({
        src: script.getAttribute("src"),
        integrity: script.getAttribute("integrity"),
        crossorigin: script.getAttribute("crossorigin"),
    }))""")
    _check_script_list(scripts, pin, source)


def check_browser(base, output, pin):
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
                        check_mermaid_script(page, source, pin)
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
                        # 空のメンバー欄を含むSVG枠の中心ではなく、ユーザーが読むクラス名を押す。
                        # 大きな全体図でも文字の位置を基準にスクロール・クリックする。
                        # (Mermaid 11 ではクラス名が .label-group 内の .nodeLabel に描かれる)
                        label_element = chosen.locator(".label-group .nodeLabel")
                        expect(label_element).to_be_visible()
                        label_element.scroll_into_view_if_needed()
                        page.screenshot(path=str(output / f"{label}-{index}.png"))
                        if chosen.get_attribute("target") == "_blank":
                            with page.expect_popup() as popup:
                                label_element.click()
                            landed = popup.value
                            landed.wait_for_load_state()
                        else:
                            label_element.click()
                            landed = page
                        expect(landed).to_have_url(re.compile(re.escape("#" + destination) + "$"))
                        expect(landed.locator('[id="' + destination + '"]')).to_be_visible()
                        if landed is not page:
                            landed.close()
                        assert not errors, errors
                        print(f"PASS {label}: {source} -> {destination}", flush=True)
                except Exception as error:
                    page.screenshot(path=str(output / f"{label}-failure.png"), full_page=True)
                    geometry = page.locator(".mermaid").evaluate_all("""elements => elements.map(el => ({
                        box: el.getBoundingClientRect().toJSON(), scrollLeft: el.scrollLeft,
                        scrollTop: el.scrollTop, width: el.clientWidth, height: el.clientHeight,
                        svg: el.querySelector('svg')?.getBoundingClientRect().toJSON()
                    }))""")
                    raise RuntimeError(f"{label} {source}: {error}\nDiagram geometry: {geometry}") from error
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
    target.add_argument("--check-directory", type=Path,
                        help="check built HTML without a browser (Mermaid pin, no bundled Mermaid)")
    parser.add_argument("--sha", help="commit expected in build-info.json (not used by --check-directory)")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path, default=Path(".maya-output/docs-browser"))
    args = parser.parse_args()
    if not args.check_directory and not args.sha:
        parser.error("--sha is required unless --check-directory is used")
    pin = read_mermaid_pin()
    if args.check_directory:
        pages = check_built_html(args.check_directory, pin)
        print(f"Verified {pages} HTML pages: Mermaid is loaded only from {pin['src']} "
              "with the SRI pinned in docs/conf.py, and is not bundled.")
        return
    if args.stamp_directory:
        stamp(args.stamp_directory, args.sha)
        return
    server = None
    try:
        if args.directory:
            check_built_html(args.directory, pin)
            handler = functools.partial(SimpleHTTPRequestHandler, directory=str(args.directory.resolve()))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}/"
        else:
            base = args.url.rstrip("/") + "/"
        wait_for_release(base, args.sha, args.timeout)
        check_browser(base, args.output, pin)
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
