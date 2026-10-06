"""FramePlayer ドキュメントの画面の画像を作る(FramePlayer とセットアップの窓だけを撮る。画面全体は撮らない)。

使い方(リポジトリの FramePlayer フォルダから)::

    python docs/tools/capture_docs.py --ffmpeg C:/path/to/ffmpeg.exe
    python docs/tools/capture_docs.py --ffmpeg ffmpeg.exe --only main,compare   # 一部だけ撮り直す

流れ:

1. 見本の動画と連番画像を ``docs/tools/_media`` に作る(ffmpeg。一度作れば使い回す。Git 対象外)。
2. FramePlayer の設定(``HKEY_CURRENT_USER\\Software\\FramePlayer``)を控え、撮影用の値にする。
3. ``build/Release/FramePlayer.exe`` を撮影ごとに起動し、キー・マウスのメッセージを送って画面の状態を作り、
   ``PrintWindow`` でその窓だけを画像にして ``docs/_static/images`` へ PNG で保存する。右クリックなどのメニューは、
   メニューの窓も撮って同じ位置に重ねる。
4. セットアップの画面は、識別名だけを変えた撮影用のセットアップを作って開き、撮ったら閉じる(インストールはしない)。
5. 最後に設定を元に戻す。

撮影の間、FramePlayer の窓が前面に出る(数秒ずつ)。既定の窓の大きさ(1280×800)で撮る。
外部のライブラリは使わない(PNG の書き出しも標準ライブラリの zlib で行う)。
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import winreg
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
DOCS = os.path.join(PACKAGE, "docs")
IMAGES = os.path.join(DOCS, "_static", "images")
MEDIA = os.path.join(HERE, "_media")
EXE = os.path.join(PACKAGE, "build", "Release", "FramePlayer.exe")
SETTINGS_KEY = r"Software\FramePlayer"
PAGE_COLOR = (20, 20, 20)  # ドキュメントの地の色(FramePlayer の地と同じ #141414)。
# セットアップの画面に出すインストール先(撮る人のユーザー名を画像に残さないため)。
SAMPLE_INSTALL_DIR = r"C:\Users\User\AppData\Local\Programs\FramePlayer"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # 画素の座標で扱う(拡大率の影響を受けない)。

WM_KEYDOWN, WM_KEYUP, WM_LBUTTONDOWN, WM_CONTEXTMENU = 0x0100, 0x0101, 0x0201, 0x007B
VK_RIGHT = 0x27
TDM_CLICK_BUTTON = 0x0400 + 102
PW_RENDERFULLCONTENT = 2

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.GetDpiForWindow.argtypes = [wt.HWND]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


# ---------------------------------------------------------------- 画像


class Image:
    """RGB の画像(行ごとの bytes)。"""

    def __init__(self, width, height, rows=None, fill=(0, 0, 0)):
        self.width = width
        self.height = height
        self.rows = rows if rows is not None else [bytearray(bytes(fill) * width) for _ in range(height)]

    def crop(self, left, top, right, bottom):
        """範囲を切り出す(右・下は含まない)。"""
        return Image(right - left, bottom - top, [bytearray(r[left * 3:right * 3]) for r in self.rows[top:bottom]])

    def paste(self, other, x, y):
        """別の画像を (x, y) に重ねる(はみ出す分は捨てる)。"""
        for j, row in enumerate(other.rows):
            ty = y + j
            if not 0 <= ty < self.height:
                continue
            left = max(0, x)
            right = min(self.width, x + other.width)
            if left < right:
                self.rows[ty][left * 3:right * 3] = row[(left - x) * 3:(right - x) * 3]

    def save(self, path):
        """PNG で保存する。"""
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        raw = b"".join(b"\x00" + bytes(r) for r in self.rows)
        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) +
                    chunk(b"IEND", b""))
        print("  保存:", os.path.relpath(path, PACKAGE), "%dx%d" % (self.width, self.height))


def window_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def capture(hwnd):
    """窓だけを PrintWindow で画像にする(GPU で描いた映像も含める)。"""
    r = window_rect(hwnd)
    width, height = r.right - r.left, r.bottom - r.top
    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(dc, bitmap)
    user32.PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT)
    info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(None, screen)
    data = buffer.raw
    rows = []
    for y in range(height):
        line = data[y * width * 4:(y + 1) * width * 4]
        row = bytearray(width * 3)
        row[0::3] = line[2::4]
        row[1::3] = line[1::4]
        row[2::3] = line[0::4]
        rows.append(row)
    return Image(width, height, rows)


def process_windows(pid, class_name=None):
    """そのプロセスの、見えている窓を返す(上にある順)。"""
    found = []

    def callback(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, name, 64)
            if class_name is None or name.value == class_name:
                found.append(hwnd)
        return True
    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def wait_window(pid, class_name, timeout=15.0, exclude=()):
    end = time.time() + timeout
    while time.time() < end:
        windows = [w for w in process_windows(pid, class_name) if w not in exclude]
        if windows:
            return windows[0]
        time.sleep(0.1)
    raise RuntimeError("窓が出ません: %s" % class_name)


def client_origin(hwnd):
    """クライアント領域の左上が、窓の画像のどこにあるか。"""
    point = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(point))
    r = window_rect(hwnd)
    return point.x - r.left, point.y - r.top


def client_size(hwnd):
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right, r.bottom


def lparam(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


# ---------------------------------------------------------------- FramePlayer の操作


class Player:
    """撮影用に起動した FramePlayer。"""

    def __init__(self, args):
        self.process = subprocess.Popen([EXE] + list(args))
        self.hwnd = wait_window(self.process.pid, "FramePlayerWindow")
        user32.SetForegroundWindow(self.hwnd)
        self.scale = user32.GetDpiForWindow(self.hwnd) / 96.0

    def s(self, value):
        return int(round(value * self.scale))

    def key(self, vk, times=1, delay=0.03):
        for _ in range(times):
            user32.PostMessageW(self.hwnd, WM_KEYDOWN, vk, 0)
            user32.PostMessageW(self.hwnd, WM_KEYUP, vk, 0xC0000001)
            time.sleep(delay)

    def control_point(self, name):
        """操作部の下段のボタンの中心(クライアント座標)。PlayerWindowControls.cpp の配置と同じ計算。"""
        width, height = client_size(self.hwnd)
        s = self.s
        range_top = height - s(36)
        volume_left = width - s(8) - s(80)
        speaker_left = volume_left - s(6) - s(22)
        compare_right = speaker_left - s(16)
        compare_left = compare_right - s(76)
        file_right = compare_left - s(6)
        file_left = file_right - s(56)
        sync_right = file_left - s(6)
        sync_left = sync_right - s(80)
        rate_right = sync_left - s(16)
        x = {"compare": (compare_left + compare_right) // 2, "file": (file_left + file_right) // 2,
             "sync": (sync_left + sync_right) // 2, "rate": rate_right - s(26)}[name]
        return x, range_top + s(18)

    def press(self, name):
        x, y = self.control_point(name)
        user32.PostMessageW(self.hwnd, WM_LBUTTONDOWN, 1, lparam(x, y))

    def context_menu(self, x, y):
        origin = wt.POINT(x, y)
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        user32.PostMessageW(self.hwnd, WM_CONTEXTMENU, self.hwnd, lparam(origin.x, origin.y))

    def capture_with_menus(self):
        """窓を撮り、開いているメニューの窓も同じ位置に重ねる。

        メニューが窓の外へはみ出すときは、はみ出す分まで画像を広げる(広げた所はドキュメントの地の色)。
        """
        base = window_rect(self.hwnd)
        menus = [(window_rect(m), capture(m)) for m in reversed(process_windows(self.process.pid, "#32768"))]
        left = min([base.left] + [r.left for r, _ in menus])
        top = min([base.top] + [r.top for r, _ in menus])
        right = max([base.right] + [r.right for r, _ in menus])
        bottom = max([base.bottom] + [r.bottom for r, _ in menus])
        image = Image(right - left, bottom - top, fill=PAGE_COLOR)
        image.paste(capture(self.hwnd), base.left - left, base.top - top)
        for r, shot in menus:
            image.paste(shot, r.left - left, r.top - top)
        return image

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


# ---------------------------------------------------------------- 設定と見本


def write_settings(values):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
        for name, value in values.items():
            if isinstance(value, list):
                winreg.SetValueEx(key, name, 0, winreg.REG_MULTI_SZ, value)
            else:
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def delete_settings():
    def remove(root, path):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        remove(key, winreg.EnumKey(key, 0))
                    except OSError:
                        break
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass
    remove(winreg.HKEY_CURRENT_USER, SETTINGS_KEY)


def make_media(ffmpeg):
    """見本の動画(2版)と連番画像(欠けあり)を作る。

    絵は灰色のチェッカー模様の上を四角が左から右へ動くだけの、落ち着いた見本(コマ送りで動きが分かるように)。
    下に「ショット名・版・フレーム番号」の文字を入れる。2版は四角の色だけが違う。
    """
    os.makedirs(MEDIA, exist_ok=True)
    font = "C\\:/Windows/Fonts/segoeui.ttf"
    checker = "geq=lum='if(mod(floor(X/120)+floor(Y/120)\\,2)\\,150\\,110)':cb=128:cr=128"
    for name, color, label in (("sh010_anim_v003.mp4", "0xFF8232", "v003"), ("sh010_anim_v004.mp4", "0x4A90E2", "v004")):
        path = os.path.join(MEDIA, name)
        if os.path.exists(path):
            continue
        text = ("drawtext=fontfile='{0}':text='sh010   {1}   %{{eif\\:n+1001\\:d}}':x=(w-text_w)/2:y=h-170:"
                "fontsize=72:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=20").format(font, label)
        # 動く四角は色の板を重ねて描く(重ねる位置は時刻 t の式で動かせる)。
        graph = ("color=c=gray:size=1920x1080:rate=24,{0}[bg];color=c={1}:size=240x240:rate=24[box];"
                 "[bg][box]overlay=x='150+t*320':y=360:shortest=1,{2},format=yuv420p").format(checker, color, text)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-filter_complex", graph,
                        "-frames:v", "96", "-c:v", "libx264", "-crf", "18", "-g", "24", path], check=True)
    sequence = os.path.join(MEDIA, "sequence")
    if not os.path.isdir(sequence):
        os.makedirs(sequence)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i",
                        os.path.join(MEDIA, "sh010_anim_v003.mp4"), "-frames:v", "48", "-start_number", "1001",
                        os.path.join(sequence, "sh010_comp.%04d.png")], check=True)
        for number in (1010, 1011, 1012):
            os.remove(os.path.join(sequence, "sh010_comp.%04d.png" % number))


# ---------------------------------------------------------------- 撮影


def base_settings(**extra):
    values = {"AutoPlay": 0, "ShowColorInfo": 0, "StartFrame": 1001, "Volume": 80, "Muted": 0}
    values.update(extra)
    return values


def shot_player(name, args, settings, prepare=None, crop=None, wait=3.0):
    delete_settings()
    write_settings(settings)
    player = Player(args)
    try:
        time.sleep(wait)
        if prepare:
            prepare(player)
        image = player.capture_with_menus()
        if crop:
            image = crop(player, image)
        image.save(os.path.join(IMAGES, name + ".png"))
        return image
    finally:
        player.close()


def controls_crop(player, image):
    """操作部(下の2段)だけを切り出す。"""
    ox, oy = client_origin(player.hwnd)
    width, height = client_size(player.hwnd)
    return image.crop(ox, oy + height - player.s(76), ox + width, oy + height)


def shoot_installer(setup_builder):
    """セットアップの確認の画面と、関連付けの画面を撮る(インストールはしない)。"""
    work = tempfile.mkdtemp(prefix="fp-docs-")
    try:
        ini = open(os.path.join(PACKAGE, "installer", "FramePlayer.wak.ini"), encoding="utf-8").read()
        installer_dir = os.path.join(PACKAGE, "installer").replace("\\", "/")
        lines = []
        for line in ini.splitlines():
            if line.startswith("Id="):
                line = "Id=FramePlayerDocsCapture"  # インストール済みでも「新しく入れる」画面になるように。
            elif line.startswith("../"):
                line = installer_dir + "/" + line
            elif line.startswith("SetupIcon=../"):
                line = "SetupIcon=" + installer_dir + "/" + line[len("SetupIcon="):]
            lines.append(line)
        path = os.path.join(work, "docs.wak.ini")
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        setup = os.path.join(work, "FramePlayerSetup.exe")
        subprocess.run([setup_builder, "--build", path, "--out", setup], check=True, stdout=subprocess.DEVNULL)
        process = subprocess.Popen([setup, "--dir", SAMPLE_INSTALL_DIR])
        try:
            dialog = wait_window(process.pid, "#32770")
            time.sleep(1.0)
            capture(dialog).save(os.path.join(IMAGES, "installer.png"))
            user32.PostMessageW(dialog, TDM_CLICK_BUTTON, 104, 0)  # 「Change file associations」
            associations = wait_window(process.pid, "#32770", exclude=(dialog,))
            time.sleep(1.0)
            capture(associations).save(os.path.join(IMAGES, "installer-associations.png"))
        finally:
            process.kill()
            process.wait()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", required=True, help="見本の動画を作る ffmpeg.exe")
    parser.add_argument("--setup-builder", default=os.path.join(PACKAGE, os.pardir, os.pardir, os.pardir, "tools",
                                                                 "WinAppKit", "build", "Release", "WinAppSetup.exe"))
    parser.add_argument("--only", help="撮る画像の名前(カンマ区切り)")
    args = parser.parse_args()
    if not os.path.isfile(EXE):
        sys.exit("FramePlayer.exe がありません(先にビルドする): " + EXE)
    os.makedirs(IMAGES, exist_ok=True)
    make_media(args.ffmpeg)
    wanted = set(args.only.split(",")) if args.only else None
    v003 = os.path.join(MEDIA, "sh010_anim_v003.mp4")
    v004 = os.path.join(MEDIA, "sh010_anim_v004.mp4")
    first_image = os.path.join(MEDIA, "sequence", "sh010_comp.1001.png")

    def step(player, frames=40):
        player.key(VK_RIGHT, frames)
        time.sleep(1.5)

    shots = [
        ("main", lambda: shot_player("main", [v003], base_settings(), prepare=step)),
        ("controls", lambda: shot_player("controls", [v003], base_settings(), prepare=step, crop=controls_crop)),
        ("compare", lambda: shot_player("compare", [v003, v004], base_settings(), prepare=step)),
        ("color-info", lambda: shot_player("color-info", [v003], base_settings(ShowColorInfo=1), prepare=step)),
        ("context-menu", lambda: shot_player(
            "context-menu", [v003], base_settings(),
            prepare=lambda p: (step(p), p.context_menu(p.s(420), p.s(260)), time.sleep(1.0)))),
        ("file-menu", lambda: shot_player(
            "file-menu", [v003], base_settings(RecentFiles=[v004, v003]),
            prepare=lambda p: (step(p), p.press("file"), time.sleep(1.0)))),
        ("sequence", lambda: shot_player("sequence", [first_image], base_settings(), prepare=lambda p: step(p, 10))),
        ("sync", lambda: shot_player("sync", [v003, "--sync"], base_settings(), prepare=step, crop=controls_crop)),
        ("installer", lambda: shoot_installer(os.path.normpath(args.setup_builder))),
    ]
    backup = os.path.join(tempfile.gettempdir(), "FramePlayer-docs-settings.reg")
    had_settings = subprocess.run(["reg", "export", "HKCU\\" + SETTINGS_KEY, backup, "/y"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    try:
        for name, run in shots:
            if wanted and name not in wanted:
                continue
            print(name)
            run()
    finally:
        # 設定を撮影の前の状態に戻す。
        delete_settings()
        if had_settings:
            subprocess.run(["reg", "import", backup], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(backup)
        print("設定を元に戻しました")


if __name__ == "__main__":
    main()
