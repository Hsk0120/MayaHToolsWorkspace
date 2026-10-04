"""隔離した VS Code を起動し、手順どおりに操作して窓を撮影する(hedit の見た目を VS Code と見比べる開発用)。

使い方(リポジトリ直下から。Python 3 の標準ライブラリだけで動く。mayapy でもよい)::

    python maya/inhouse/hedit/docs/tools/vscode_capture/capture.py
    python maya/inhouse/hedit/docs/tools/vscode_capture/capture.py 手順.json --output 出力フォルダ

手順(JSON)の書き方は ``extension/extension.js`` の先頭と、例の ``find_replace.json`` を参照。
手順の中の ``{"capture": 名前}`` ごとに ``<出力フォルダ>/vscode_<名前>.png`` を書く。
既定の出力先は ``.maya-output/vscode-capture/<日時>/``(Git 対象外)。

手順の ``files``(相対パス→本文)で、開くフォルダに別のファイルも置ける(複数ファイルの検索などの撮影用)。
手順の ``extensions``(フォルダ名の先頭の一覧。例: ``["ms-python.python-", "ms-python.vscode-pylance-"]``)は、
``%USERPROFILE%/.vscode/extensions`` の該当する拡張機能を一時フォルダへ **コピー** して読み込む(元は書き換えない)。

ユーザーの VS Code・設定・拡張機能には触れない。一時フォルダに専用の ``--user-data-dir`` と
``--extensions-dir`` を作り、撮影用の拡張機能(``extension/``)だけを ``--extensionDevelopmentPath`` で読み込む。
撮影は Windows の PrintWindow を使うので、VS Code の窓がほかの窓の後ろにあっても撮れる。
終了時は、このスクリプトが起動した VS Code のプロセスだけを終了する。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def find_code():
    """VS Code の実行ファイルを探す。

    Returns:
        Path: ``Code.exe`` のパス。環境変数 ``HEDIT_VSCODE_EXE`` があればそれを使う。

    Raises:
        FileNotFoundError: 既定のインストール先に見つからない場合。
    """
    candidates = [os.environ.get("HEDIT_VSCODE_EXE", "")]
    candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs/Microsoft VS Code/Code.exe"))
    candidates.append(os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft VS Code/Code.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError("Code.exe not found. Set HEDIT_VSCODE_EXE to its path.")


def write_png(path, width, height, bgra):
    """BGRA の画素を、標準ライブラリだけで PNG に書く。

    Args:
        path (Path): 書き出し先。
        width (int): 幅。
        height (int): 高さ。
        bgra (bytes): 上の行から順の BGRA 画素(1画素4バイト)。
    """
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rows.append(0)  # 各行の先頭は、フィルターの種類(0=なし)。
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        rows += rgb

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def find_window(title_part, timeout=60):
    """タイトルに指定の文字を含む、表示中のトップレベル窓を探す。

    Args:
        title_part (str): タイトルに含まれる文字。
        timeout (float): 待つ秒数。

    Returns:
        int | None: 窓のハンドル。見つからなければ None。
    """
    found = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if title_part in buffer.value:
                found.append(hwnd)
        return True

    end = time.time() + timeout
    while time.time() < end:
        found.clear()
        user32.EnumWindows(enum_proc(callback), 0)
        if found:
            return found[0]
        time.sleep(0.3)
    return None


def capture(hwnd, path):
    """PrintWindow で窓の中身を撮って PNG に書く。

    Args:
        hwnd (int): 窓のハンドル。
        path (Path): 書き出し先。

    Returns:
        tuple[int, int]: 撮った画像の幅と高さ。
    """

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    user32.PrintWindow(hwnd, memory_dc, 2)  # PW_RENDERFULLCONTENT: Chromium(VS Code)の描画も撮る。
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    write_png(path, width, height, buffer.raw)
    return width, height


def copy_extensions(prefixes, destination):
    """ユーザーの拡張機能のうち、指定の名前で始まるものを一時フォルダへコピーする。

    Args:
        prefixes (list[str]): 拡張機能のフォルダ名の先頭(``ms-python.python-`` など)。
        destination (Path): 隔離した VS Code の ``--extensions-dir``。

    Raises:
        FileNotFoundError: 指定の拡張機能が見つからない場合。
    """
    source = Path(os.environ.get("USERPROFILE", "")) / ".vscode/extensions"
    destination.mkdir(parents=True, exist_ok=True)
    for prefix in prefixes:
        matches = sorted(path for path in source.glob(prefix + "*") if path.is_dir())
        if not matches:
            raise FileNotFoundError("extension not found: " + prefix)
        # 同じ拡張機能の版が複数あれば、名前の順で最後(新しい版)を使う。
        shutil.copytree(matches[-1], destination / matches[-1].name)


def run(script, output, code=None):
    """隔離した VS Code で手順を実行し、撮影する。

    Args:
        script (dict): 手順(``find_replace.json`` と同じ形)。
        output (Path): 画像の出力フォルダ。
        code (Path | None): ``Code.exe``。None なら :func:`find_code` で探す。

    Returns:
        dict: 撮った画像(``shots``)と、拡張機能が書いた実行記録(``log``)。

    Raises:
        RuntimeError: VS Code の窓が見つからない、または撮影の合図が来ない場合。
    """
    code = code or find_code()
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="hedit_vscode_"))
    user_data = work / "user-data"
    (user_data / "User").mkdir(parents=True)
    # 撮影の邪魔になる案内・サイドバー・更新確認を止める。
    settings = {
        "workbench.startupEditor": "none", "window.restoreWindows": "none", "workbench.tips.enabled": False,
        "security.workspace.trust.enabled": False, "update.mode": "none", "telemetry.telemetryLevel": "off",
        "extensions.autoCheckUpdates": False, "workbench.enableExperiments": False, "chat.disableAIFeatures": True,
        "window.zoomLevel": script.get("zoomLevel", 0),
        "workbench.secondarySideBar.defaultVisibility": "hidden", "workbench.activityBar.location": "hidden",
    }
    settings.update(script.get("settings", {}))
    (user_data / "User/settings.json").write_text(json.dumps(settings), encoding="utf-8")
    # 開くフォルダの名前が窓のタイトルに入るので、それを目印に窓を探す。
    folder = work / "hedit-vscode-capture"
    folder.mkdir()
    sample = folder / script.get("fileName", "sample.py")
    sample.write_text(script.get("text", ""), encoding="utf-8")
    for relative, text in script.get("files", {}).items():
        extra = folder / relative
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(text, encoding="utf-8")
    copy_extensions(script.get("extensions", []), work / "ext")
    done = work / "done.json"
    runtime_path = work / "script.json"
    runtime_path.write_text(json.dumps(dict(script, file=str(sample), done=str(done))), encoding="utf-8")
    env = dict(os.environ, HEDIT_VSCODE_SCRIPT=str(runtime_path))
    process = subprocess.Popen([str(code), "--user-data-dir", str(user_data), "--extensions-dir", str(work / "ext"),
                                "--extensionDevelopmentPath", str(HERE / "extension"), "--new-window",
                                "--disable-workspace-trust", "--skip-welcome", "--skip-release-notes", str(folder)],
                               env=env)
    try:
        hwnd = find_window(folder.name)
        if not hwnd:
            raise RuntimeError("VS Code window not found")
        width, height = script.get("windowSize", [1200, 720])
        user32.ShowWindow(hwnd, 1)
        user32.MoveWindow(hwnd, 40, 40, width, height, True)
        # {"capture": 名前}ごとに、拡張機能の合図(.ready)を待って撮り、返事(.ack)を書く。
        names = [step["capture"] for step in script.get("steps", []) if "capture" in step]
        shots = []
        end = time.time() + script.get("timeout", 120)
        for name in names:
            ready = Path("{}.{}.ready".format(done, name))
            while not ready.exists() and time.time() < end:
                time.sleep(0.2)
            if not ready.exists():
                raise RuntimeError("capture step not reached: " + name)
            path = output / "vscode_{}.png".format(name)
            shots.append({"name": name, "path": str(path), "size": capture(hwnd, path)})
            Path("{}.{}.ack".format(done, name)).write_text("ok", encoding="utf-8")
        while not done.exists() and time.time() < end:
            time.sleep(0.3)
        log = json.loads(done.read_text(encoding="utf-8")) if done.exists() else None
        return {"shots": shots, "log": log}
    finally:
        # 自分が起動した VS Code だけを閉じる(ユーザーの VS Code は別のプロセス)。
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        time.sleep(1.0)
        shutil.rmtree(work, ignore_errors=True)


def main():
    """コマンドラインの入口。"""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", nargs="?", default=str(HERE / "find_replace.json"), help="手順の JSON")
    parser.add_argument("--output", help="出力フォルダ(既定: .maya-output/vscode-capture/<日時>)")
    args = parser.parse_args()
    user32.SetProcessDPIAware()  # 高DPIの画面でも、実際のピクセル数で撮る。
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else ROOT / ".maya-output/vscode-capture" / stamp
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    print(json.dumps(run(script, output), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
