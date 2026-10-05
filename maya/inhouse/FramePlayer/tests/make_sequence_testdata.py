"""連番画像の確認用データを作る。

作るもの(``--out`` の下):

- ``frames/<名前>/shot.1001.<拡張子>``〜: コマ番号を縦縞で描いた48枚の連番(README「コマ送りの正確さの確認」と同じ絵)。
  ``frames/list.txt`` に「名前 最初のファイル コマ数 欠けた番号(カンマ区切り、無ければ -)」を1行ずつ書く。
  ``FramePlayerVerify.exe`` で確かめる(``run_sequence_check.py``)。
- ``color/``: 色の付いた四角(パッチ)の画像と期待値(``expected.txt``)。``FramePlayerColorCheck.exe`` で確かめる。

形式: PNG(8・16bit)・JPEG・BMP・TIFF(8・16bit)・WebP・GIF(Python・ffmpeg)、
HEIF・JPEG XL・JPEG XR(8bit・浮動小数点。FramePlayerImageConvert = WIC)、
OpenEXR(半精度・32bit浮動小数点、圧縮 NONE・RLE・ZIPS・ZIP・PIZ・PXR24・B44・B44A・DWAA・DWAB、走査線・タイル。
oiiotool)、ACEScg(AP1)の色域のEXR。

使い方::

    python make_sequence_testdata.py --ffmpeg ffmpeg.exe --oiiotool oiiotool.exe ^
        --convert ..\\build\\Release\\FramePlayerImageConvert.exe --out ..\\build\\testdata\\sequences

ffmpeg・oiiotool・FramePlayerImageConvert は確認用データを作るためだけに使い、プレイヤーには含めない。
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_color_testdata as color  # noqa: E402

FRAME_COUNT = 48
FIRST = 1001
STRIPE_SIZE = (640, 360)
MISSING = [1010, 1011, 1012]


def png(path, width, height, rows, bits16=False):
    """RGBのPNGを書く(行ごとのバイト列から。16bitは上位バイトが先)。"""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 16 if bits16 else 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def exr(path, width, height, pixel):
    """圧縮なし・半精度のRGBのEXRを書く。pixel(x, y) は (r, g, b) のリニアな値を返す。"""
    def attribute(name, kind, data):
        return name.encode() + b"\x00" + kind.encode() + b"\x00" + struct.pack("<i", len(data)) + data
    channels = b"".join(name + b"\x00" + struct.pack("<iB3xii", 1, 0, 1, 1) for name in (b"B", b"G", b"R")) + b"\x00"
    box = struct.pack("<iiii", 0, 0, width - 1, height - 1)
    header = (attribute("channels", "chlist", channels) + attribute("compression", "compression", b"\x00") +
              attribute("dataWindow", "box2i", box) + attribute("displayWindow", "box2i", box) +
              attribute("lineOrder", "lineOrder", b"\x00") + attribute("pixelAspectRatio", "float", struct.pack("<f", 1.0)) +
              attribute("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0)) +
              attribute("screenWindowWidth", "float", struct.pack("<f", 1.0)) + b"\x00")
    start = 8 + len(header) + 8 * height
    line_size = 8 + width * 2 * 3
    offsets = b"".join(struct.pack("<Q", start + y * line_size) for y in range(height))
    lines = []
    for y in range(height):
        values = [pixel(x, y) for x in range(width)]
        data = b"".join(struct.pack("<%de" % width, *[v[c] for v in values]) for c in (2, 1, 0))
        lines.append(struct.pack("<ii", y, len(data)) + data)
    with open(path, "wb") as f:
        f.write(struct.pack("<II", 20000630, 2) + header + offsets + b"".join(lines))


def stripe_rows(index, width, height, bits16=False):
    """コマ番号の縦縞(上端は白、下端は黒、中央に12本の2進数)の行を返す。"""
    white = b"\xff\xff" * 3 if bits16 else b"\xff" * 3
    black = b"\x00\x00" * 3 if bits16 else b"\x00" * 3
    middle = b"".join(white if (index >> (x * 12 // width)) & 1 else black for x in range(width))
    rows = []
    for y in range(height):
        if y < height // 8:
            rows.append(white * width)
        elif y > height * 7 // 8:
            rows.append(black * width)
        else:
            rows.append(middle)
    return rows


def run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("  失敗:", " ".join(os.path.basename(str(c)) for c in cmd[:2]),
              result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:])
        return False
    return True


def bradford_to_d65(m_xyz_white):
    return m_xyz_white


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--oiiotool", required=True)
    parser.add_argument("--convert", required=True, help="FramePlayerImageConvert.exe")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    frames = os.path.join(args.out, "frames")
    colors = os.path.join(args.out, "color")
    os.makedirs(frames, exist_ok=True)
    os.makedirs(colors, exist_ok=True)
    width, height = STRIPE_SIZE
    listed = []

    def folder(name):
        path = os.path.join(frames, name)
        os.makedirs(path, exist_ok=True)
        return path

    def add(name, ext, missing=()):
        first = os.path.join(frames, name, f"shot.{FIRST}.{ext}")
        if os.path.exists(first):
            listed.append(f"{name} {name}/shot.{FIRST}.{ext} {FRAME_COUNT} {','.join(map(str, missing)) or '-'}")
            print("作成:", name)

    # PNGはPythonで直接書く(8bit・16bit)。
    for bits16, name in ((False, "png8"), (True, "png16")):
        out = folder(name)
        for i in range(FRAME_COUNT):
            png(os.path.join(out, f"shot.{FIRST + i}.png"), width, height, stripe_rows(i, width, height, bits16), bits16)
        add(name, "png")
    png8 = os.path.join(frames, "png8", "shot.%04d.png")
    png16 = os.path.join(frames, "png16", "shot.%04d.png")
    base = [args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-start_number", str(FIRST)]
    ffmpeg_cases = [
        ("jpg", "jpg", png8, ["-q:v", "2"]),
        ("bmp", "bmp", png8, []),
        ("tif8", "tif", png8, ["-pix_fmt", "rgb24"]),
        ("tif16", "tif", png16, ["-pix_fmt", "rgb48le"]),
        ("webp", "webp", png8, ["-c:v", "libwebp", "-lossless", "1"]),
        ("gif", "gif", png8, ["-f", "image2"]),
    ]
    for name, ext, source, options in ffmpeg_cases:
        out = folder(name)
        if run(base + ["-i", source] + options + ["-start_number", str(FIRST), os.path.join(out, f"shot.%04d.{ext}")]):
            add(name, ext)
    # WICで書く形式(HEIF・JPEG XL・JPEG XR)。
    for name, ext, option in (("heif", "heic", []), ("jxl", "jxl", []), ("jxr", "jxr", []), ("jxr_float", "jxr", ["--float"])):
        out = folder(name)
        ok = True
        for i in range(FRAME_COUNT):
            ok = ok and run([os.path.abspath(args.convert), os.path.join(frames, "png8", f"shot.{FIRST + i}.png"),
                             os.path.join(out, f"shot.{FIRST + i}.{ext}")] + option)
        if ok:
            add(name, ext)
    # EXR(oiiotool)。圧縮・データの型・タイルを変えて作る。
    exr_cases = [
        ("exr_none", ["-d", "half", "--compression", "none"]),
        ("exr_rle", ["-d", "half", "--compression", "rle"]),
        ("exr_zips", ["-d", "half", "--compression", "zips"]),
        ("exr_zip", ["-d", "half", "--compression", "zip"]),
        ("exr_piz", ["-d", "half", "--compression", "piz"]),
        ("exr_pxr24", ["-d", "half", "--compression", "pxr24"]),
        ("exr_b44", ["-d", "half", "--compression", "b44"]),
        ("exr_b44a", ["-d", "half", "--compression", "b44a"]),
        ("exr_dwaa", ["-d", "half", "--compression", "dwaa"]),
        ("exr_dwab", ["-d", "half", "--compression", "dwab"]),
        ("exr_float_zip", ["-d", "float", "--compression", "zip"]),
        ("exr_float_piz", ["-d", "float", "--compression", "piz"]),
        ("exr_float_pxr24", ["-d", "float", "--compression", "pxr24"]),
        ("exr_tiled_zip", ["-d", "half", "--compression", "zip", "--tile", "64", "64"]),
        ("exr_tiled_piz", ["-d", "half", "--compression", "piz", "--tile", "128", "32"]),
    ]
    for name, options in exr_cases:
        out = folder(name)
        if run([args.oiiotool, "--frames", f"{FIRST}-{FIRST + FRAME_COUNT - 1}",
                os.path.join(frames, "png8", "shot.#.png")] + options + ["-o", os.path.join(out, "shot.#.exr")]):
            add(name, "exr")
    # 欠けのある連番(PNGから写し、いくつかの番号を抜く)。
    out = folder("missing")
    for i in range(FRAME_COUNT):
        if FIRST + i not in MISSING:
            shutil.copy(os.path.join(frames, "png8", f"shot.{FIRST + i}.png"), os.path.join(out, f"shot.{FIRST + i}.png"))
    add("missing", "png", MISSING)
    with open(os.path.join(frames, "list.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(listed) + "\n")

    # ---------------------------------------------------------------- 色
    cw, ch = 1280, 720
    pw, ph = cw // color.COLUMNS, ch // color.ROWS
    expected = []

    def patch_rows(values, bits16):
        rows = []
        for y in range(ch):
            row_values = values[(y // ph) * color.COLUMNS:(y // ph + 1) * color.COLUMNS]
            if bits16:
                rows.append(b"".join(struct.pack(">3H", *(round(c * 65535) for c in v)) * pw for v in row_values))
            else:
                rows.append(b"".join(bytes(round(c * 255) for c in v) * pw for v in row_values))
        return rows

    sdr = color.sdr_expected(color.SDR_PATCHES)
    png(os.path.join(colors, "c_png_low.png"), cw, ch, patch_rows(color.SDR_PATCHES, False))
    png(os.path.join(colors, "c_png_deep.png"), cw, ch, patch_rows(color.SDR_PATCHES, True), True)
    expected.append(("c_png_low.png", "sdr", 8, "bt709", sdr))
    expected.append(("c_png_deep.png", "sdr", 16, "bt709", sdr))
    for name, source, options in (("c_tif_deep.tif", "c_png_deep.png", ["-pix_fmt", "rgb48le"]), ("c_bmp.bmp", "c_png_low.png", []),
                                  ("c_webp.webp", "c_png_low.png", ["-c:v", "libwebp", "-lossless", "1"]),
                                  ("c_jpg.jpg", "c_png_low.png", ["-q:v", "1", "-pix_fmt", "yuvj444p"])):
        if run([args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", os.path.join(colors, source)] + options +
               [os.path.join(colors, name)]):
            expected.append((name, "sdr", 16 if "deep" in name else 8, "bt709", sdr))
    for name, option in (("c_heif.heic", []), ("c_jxl.jxl", []), ("c_jxr.jxr", []), ("c_jxr_float.jxr", ["--float"])):
        if run([os.path.abspath(args.convert), os.path.join(colors, "c_png_low.png"), os.path.join(colors, name)] + option):
            float_ = bool(option)
            expected.append((name, "linear" if float_ else "sdr", 16 if float_ else 8, "bt709", sdr))
    # EXRはリニアな値(パッチの値をsRGBの曲線でリニアにしたもの)。画面ではsRGBにして元の値に戻る。
    def patch_linear(x, y):
        v = color.SDR_PATCHES[(y // ph) * color.COLUMNS + x // pw]
        return tuple(color.srgb_eotf(c) for c in v)
    base_exr = os.path.join(colors, "c_base.exr")
    exr(base_exr, cw, ch, patch_linear)
    for name, options in (("c_exr_zip.exr", ["--compression", "zip"]), ("c_exr_piz.exr", ["--compression", "piz"]),
                          ("c_exr_float.exr", ["-d", "float", "--compression", "zip"])):
        if run([args.oiiotool, base_exr] + options + ["-o", os.path.join(colors, name)]):
            expected.append((name, "linear", 16, "bt709", sdr))
    # ACEScg(AP1)の色域と書いたEXR。値はAP1のリニアな値として読まれ、BT.709へ変換して表示される。
    ap1 = "0.713,0.293,0.165,0.830,0.128,0.044,0.32168,0.33767"
    if run([args.oiiotool, base_exr, "--attrib:type=float[8]", "chromaticities", ap1, "--compression", "zip",
            "-o", os.path.join(colors, "c_exr_acescg.exr")]):
        expected.append(("c_exr_acescg.exr", "linear", 16, "acesap1", color_ap1_expected()))
    os.remove(base_exr)
    with open(os.path.join(colors, "expected.txt"), "w", encoding="utf-8") as f:
        f.write(f"grid {color.COLUMNS} {color.ROWS}\n")
        for name, transfer, bits, primaries, patches in expected:
            f.write(f"video {name} bt709 full {primaries} {transfer} {bits}\n")
            for mode in ("sdr", "hdr"):
                for i, rgb in enumerate(patches[mode]):
                    f.write(f"{mode} {i} {rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
    print(f"作成: frames/list.txt({len(listed)}種), color/expected.txt({len(expected)}枚)")


def color_ap1_expected():
    """AP1(白はACESの白)のリニアな値を、Bradford法でD65に合わせてBT.709へ変換した期待値。"""
    def xyz(x, y):
        return (x / y, 1.0, (1 - x - y) / y)

    def rgb_to_xyz(prims, white):
        cols = [xyz(*p) for p in prims]
        m = [[cols[j][i] for j in range(3)] for i in range(3)]
        s = color.mat_mul(color.mat_inv(m), xyz(*white))
        return [[m[i][j] * s[j] for j in range(3)] for i in range(3)]
    cone = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
    aces_white = (0.32168, 0.33767)
    d65 = color.D65
    src = color.mat_mul(cone, xyz(*aces_white))
    dst = color.mat_mul(cone, xyz(*d65))
    scale = [[dst[i] / src[i] if i == j else 0.0 for j in range(3)] for i in range(3)]
    adapt = color.mat_mat(color.mat_inv(cone), color.mat_mat(scale, cone))
    ap1 = rgb_to_xyz(((0.713, 0.293), (0.165, 0.830), (0.128, 0.044)), aces_white)
    to709 = color.mat_mat(color.mat_inv(rgb_to_xyz((((0.64, 0.33)), (0.30, 0.60), (0.15, 0.06)), d65)),
                          color.mat_mat(adapt, ap1))
    linear = [color.mat_mul(to709, tuple(color.srgb_eotf(c) for c in v)) for v in color.SDR_PATCHES]
    return {
        "sdr": [[color.srgb_oetf(min(max(c, 0.0), 1.0)) for c in v] for v in linear],
        "hdr": [[c * 200.0 / 80.0 for c in v] for v in linear],
    }


if __name__ == "__main__":
    main()
