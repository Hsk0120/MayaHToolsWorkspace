"""色の正確さを確かめる動画と、その期待値を作る。

各動画は色の付いた四角(パッチ)を並べた1秒の動画で、色の情報(行列・範囲・色域・伝達関数)の
付け方を変えてある。期待値(``expected.json``)には、各パッチの中央で FramePlayer が出すべき値を
表示の状態(SDR表示・HDR表示)ごとに書く。``FramePlayerColorCheck.exe`` がこれを読んで確かめる。

期待値の式は規格(ITU-R BT.601/709/2020/2100、IEC 61966-2-1)から、FramePlayer のコードとは別に書いた。

使い方::

    python make_color_testdata.py --ffmpeg C:/path/to/ffmpeg.exe --out ../build/testdata/color

ffmpeg は確認用動画を作るためだけに使い、プレイヤーには含めない。
"""

import argparse
import json
import math
import os
import struct
import subprocess

# 1280x720 を 8列x4行に分けたパッチ。SDR の値は 0..1 の表示用の値(709 の色域)。
SDR_PATCHES = [
    (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (0.2, 0.2, 0.2),
    (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.8, 0.8, 0.8),
    (0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0), (0.05, 0.05, 0.05),
    (0.75, 0.25, 0.25), (0.25, 0.75, 0.25), (0.25, 0.25, 0.75), (0.9, 0.6, 0.45),
    (0.4, 0.3, 0.2), (0.6, 0.7, 0.9), (0.33, 0.5, 0.1), (0.95, 0.85, 0.2),
    (0.1, 0.4, 0.6), (0.7, 0.2, 0.6), (0.5, 0.1, 0.0), (0.0, 0.3, 0.3),
    (0.25, 0.25, 0.25), (0.6, 0.6, 0.6), (0.9, 0.9, 0.9), (0.12, 0.12, 0.12),
    (0.85, 0.45, 0.1), (0.3, 0.6, 0.55), (0.55, 0.35, 0.75), (0.15, 0.2, 0.35),
]

# HDR のパッチ。BT.2020 の色域の、リニアな明るさ(cd/m2)。灰色の段階と、203cd/m2(基準の白)の原色。
HDR_PATCHES = [
    (0, 0, 0), (1, 1, 1), (10, 10, 10), (50, 50, 50),
    (100, 100, 100), (203, 203, 203), (400, 400, 400), (1000, 1000, 1000),
    (203, 0, 0), (0, 203, 0), (0, 0, 203), (203, 203, 0),
    (20, 10, 5), (60, 40, 20), (150, 100, 60), (300, 250, 200),
    (5, 5, 5), (25, 25, 25), (75, 75, 75), (150, 150, 150),
    (250, 250, 250), (600, 600, 600), (800, 800, 800), (700, 300, 100),
    (100, 50, 150), (30, 60, 90), (120, 120, 40), (2, 2, 2),
    (500, 100, 50), (50, 500, 100), (100, 50, 500), (40, 40, 40),
]

COLUMNS = 8
ROWS = 4

# 色域(xy)。白はどれも D65。
PRIMARIES = {
    "bt709": ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060)),
    "bt2020": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),
    "smpte170m": ((0.630, 0.340), (0.310, 0.595), (0.155, 0.070)),
    "bt470bg": ((0.640, 0.330), (0.290, 0.600), (0.150, 0.060)),
}
D65 = (0.3127, 0.3290)


def srgb_eotf(v):
    """IEC 61966-2-1 の sRGB の値を、リニアな値にする。"""
    sign = -1.0 if v < 0 else 1.0
    v = abs(v)
    return sign * (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)


def srgb_oetf(v):
    """リニアな値を sRGB の値にする(srgb_eotf の逆)。"""
    sign = -1.0 if v < 0 else 1.0
    v = abs(v)
    return sign * (v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)


PQ_M1 = 2610 / 16384
PQ_M2 = 2523 / 4096 * 128
PQ_C1 = 3424 / 4096
PQ_C2 = 2413 / 4096 * 32
PQ_C3 = 2392 / 4096 * 32


def pq_oetf(nits):
    """BT.2100 PQ: 明るさ(cd/m2)を信号(0..1)にする。"""
    y = max(nits, 0.0) / 10000.0
    yp = y ** PQ_M1
    return ((PQ_C1 + PQ_C2 * yp) / (1 + PQ_C3 * yp)) ** PQ_M2


def pq_eotf(signal):
    """BT.2100 PQ: 信号(0..1)を明るさ(cd/m2)にする。"""
    ep = max(signal, 0.0) ** (1 / PQ_M2)
    return 10000.0 * (max(ep - PQ_C1, 0.0) / (PQ_C2 - PQ_C3 * ep)) ** (1 / PQ_M1)


HLG_A = 0.17883277
HLG_B = 1 - 4 * HLG_A
HLG_C = 0.5 - HLG_A * math.log(4 * HLG_A)


def hlg_oetf(e):
    """BT.2100 HLG: シーンのリニアな値(0..1)を信号にする。"""
    return math.sqrt(3 * e) if e <= 1 / 12 else HLG_A * math.log(12 * e - HLG_B) + HLG_C


def mat_mul(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def mat_mat(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_inv(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]


def rgb_to_xyz(name):
    """色域の RGB(リニア)を XYZ にする行列(SMPTE RP 177 の求め方)。"""
    prims = PRIMARIES[name]
    cols = [(x / y, 1.0, (1 - x - y) / y) for x, y in prims]
    m = [[cols[j][i] for j in range(3)] for i in range(3)]
    wx, wy = D65
    white = (wx / wy, 1.0, (1 - wx - wy) / wy)
    s = mat_mul(mat_inv(m), white)
    return [[m[i][j] * s[j] for j in range(3)] for i in range(3)]


def conversion(src, dst):
    return mat_mat(mat_inv(rgb_to_xyz(dst)), rgb_to_xyz(src))


# BT.2390 の EETF(表示の明るさの範囲へ収める曲線)。FramePlayer の SDR 表示での HDR の扱いの期待値に使う。
REFERENCE_WHITE = 203.0


def eetf(nits, source_peak, target_peak):
    src_max = pq_oetf(source_peak)
    e1 = pq_oetf(nits) / src_max
    max_lum = pq_oetf(target_peak) / src_max
    ks = 1.5 * max_lum - 0.5
    if e1 < ks:
        e2 = e1
    else:
        t = (e1 - ks) / (1 - ks)
        e2 = ((2 * t ** 3 - 3 * t ** 2 + 1) * ks + (t ** 3 - 2 * t ** 2 + t) * (1 - ks)
              + (-2 * t ** 3 + 3 * t ** 2) * max_lum)
    return pq_eotf(e2 * src_max)


def hdr_to_sdr(rgb2020_nits, source_peak):
    """HDR(BT.2020 のリニアな cd/m2)を、SDR 表示用のリニアな値(709、1.0 = 基準の白)にする。"""
    peak = max(rgb2020_nits)
    if peak <= 0:
        return (0.0, 0.0, 0.0)
    scale = eetf(peak, source_peak, REFERENCE_WHITE) / peak
    rgb = mat_mul(conversion("bt2020", "bt709"), tuple(c * scale for c in rgb2020_nits))
    return tuple(c / REFERENCE_WHITE for c in rgb)


def hlg_display_nits(scene, peak=1000.0):
    """BT.2100 HLG の OOTF: シーンのリニアな値(0..1)を表示の明るさにする(公称のピーク 1000cd/m2、γ=1.2)。"""
    gamma = 1.2
    ys = 0.2627 * scene[0] + 0.6780 * scene[1] + 0.0593 * scene[2]
    return tuple(peak * (ys ** (gamma - 1) if ys > 0 else 0.0) * c for c in scene)


def hlg_scene_from_nits(nits, peak=1000.0):
    """hlg_display_nits の逆(灰色と原色のパッチを作るため)。"""
    gamma = 1.2
    rel = tuple(c / peak for c in nits)
    yd = 0.2627 * rel[0] + 0.6780 * rel[1] + 0.0593 * rel[2]
    if yd <= 0:
        return (0.0, 0.0, 0.0)
    ys = yd ** (1 / gamma)
    return tuple(c * ys ** (1 - gamma) for c in rel)


def patch_rects(width, height):
    pw = width // COLUMNS
    ph = height // ROWS
    for row in range(ROWS):
        for col in range(COLUMNS):
            yield col * pw, row * ph, pw, ph


def raw_frame(width, height, values, bits16):
    """パッチの値(0..1)から、rgb24 か rgb48le の1コマを作る。"""
    rows = []
    for row in range(ROWS):
        row_values = values[row * COLUMNS:(row + 1) * COLUMNS]
        pw = width // COLUMNS
        if bits16:
            pixels = b"".join(struct.pack("<3H", *(round(min(max(c, 0.0), 1.0) * 65535) for c in v)) * pw
                              for v in row_values)
        else:
            pixels = b"".join(bytes(round(min(max(c, 0.0), 1.0) * 255) for c in v) * pw for v in row_values)
        rows.append(pixels * (height // ROWS))
    return b"".join(rows)


def encode(ffmpeg, out, width, height, frame, bits16, matrix, range_, codec, tags, x265_params="", write_colr=True):
    """1コマの RGB を、指定の行列・範囲で YUV にして1秒の動画にする。"""
    pix_in = "rgb48le" if bits16 else "rgb24"
    pix_out = "yuv420p10le" if codec in ("hevc10", "vp9_10") else "yuv420p"
    vf = (f"loop=loop=23:size=1:start=0,scale=in_range=pc:out_color_matrix={matrix}:out_range={range_}"
          f":flags=accurate_rnd+full_chroma_int,format={pix_out}")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", pix_in,
           "-s", f"{width}x{height}", "-r", "24", "-i", "-", "-vf", vf]
    if codec == "h264":
        cmd += ["-c:v", "libx264", "-qp", "2", "-preset", "medium", "-profile:v", "high"]
    elif codec in ("vp9", "vp9_10"):
        # VP9は可逆で圧縮する(YUVの値がそのまま残る)。mp4ではvpcCボックスに色の情報が入る。
        cmd += ["-c:v", "libvpx-vp9", "-lossless", "1", "-row-mt", "1"]
        if codec == "vp9_10":
            cmd += ["-profile:v", "2"]
    else:
        params = "qp=2" + (":" + x265_params if x265_params else "")
        cmd += ["-c:v", "libx265", "-x265-params", params, "-profile:v", "main10", "-tag:v", "hvc1"]
    for key, value in tags.items():
        cmd += [f"-{key}", value]
    if out.endswith(".mp4") and tags and write_colr:
        cmd += ["-movflags", "+write_colr"]
    cmd.append(out)
    subprocess.run(cmd, input=frame, check=True)


def sdr_expected(values, primaries="bt709"):
    """SDR の動画の期待値。

    SDR 表示では値そのまま(709 以外の色域は、画面の sRGB の曲線でリニアにして 709 へ変換し、範囲外を切って戻した値)。
    HDR 表示(SDR の白 200cd/m2)ではリニアにして明るさを掛けた scRGB の値(範囲外は切らない)。
    """
    m = conversion(primaries, "bt709")
    linear = [mat_mul(m, tuple(srgb_eotf(c) for c in v)) for v in values]
    return {
        "sdr": [[srgb_oetf(min(max(c, 0.0), 1.0)) for c in v] for v in linear],
        "hdr": [[c * 200.0 / 80.0 for c in v] for v in linear],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", required=True, help="ffmpeg.exe のパス")
    parser.add_argument("--out", required=True, help="出力先のフォルダ")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    expected = {"columns": COLUMNS, "rows": ROWS, "videos": []}

    def add(name, width, height, color, patches, **encode_args):
        path = os.path.join(args.out, name)
        encode(args.ffmpeg, path, width, height, **encode_args)
        expected["videos"].append({"file": name, "color": color, "patches": patches})
        print("作成:", name)

    hd = (1280, 720)
    sdr_frame = raw_frame(*hd, SDR_PATCHES, False)
    tags709 = {"colorspace": "bt709", "color_primaries": "bt709", "color_trc": "bt709"}
    add("sdr8_709_tv.mp4", *hd, {"matrix": "bt709", "range": "limited", "primaries": "bt709", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES), frame=sdr_frame, bits16=False, matrix="bt709", range_="tv", codec="h264",
        tags={**tags709, "color_range": "tv"})
    add("sdr8_709_pc.mp4", *hd, {"matrix": "bt709", "range": "full", "primaries": "bt709", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES), frame=sdr_frame, bits16=False, matrix="bt709", range_="pc", codec="h264",
        tags={**tags709, "color_range": "pc"})
    add("sdr8_709_tv.mov", *hd, {"matrix": "bt709", "range": "limited", "primaries": "bt709", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES), frame=sdr_frame, bits16=False, matrix="bt709", range_="tv", codec="h264",
        tags={**tags709, "color_range": "tv"})
    # HDの大きさでも、BT.601と指定されていればBT.601で戻す(大きさからの推定より指定を優先する)。
    add("sdr8_601_tv_hd.mp4", *hd,
        {"matrix": "bt601", "range": "limited", "primaries": "smpte170m", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES, "smpte170m"), frame=sdr_frame, bits16=False, matrix="bt601", range_="tv", codec="h264",
        tags={"colorspace": "smpte170m", "color_primaries": "smpte170m", "color_trc": "smpte170m", "color_range": "tv"})
    # 色の情報が無い動画は、HDならBT.709、SDならBT.601とみなす。
    add("sdr8_untagged_hd.mp4", *hd, {"matrix": "bt709", "range": "limited", "primaries": "bt709", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES), frame=sdr_frame, bits16=False, matrix="bt709", range_="tv", codec="h264", tags={})
    sd = (720, 480)
    add("sdr8_untagged_sd.mp4", *sd,
        {"matrix": "bt601", "range": "limited", "primaries": "smpte170m", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES, "smpte170m"), frame=raw_frame(*sd, SDR_PATCHES, False), bits16=False, matrix="bt601", range_="tv", codec="h264", tags={})
    # 10bit の SDR(BT.709)。
    add("sdr10_709_tv_hevc.mp4", *hd, {"matrix": "bt709", "range": "limited", "primaries": "bt709", "transfer": "sdr", "bits": 10},
        sdr_expected(SDR_PATCHES), frame=raw_frame(*hd, SDR_PATCHES, True), bits16=True, matrix="bt709", range_="tv",
        codec="hevc10", tags={**tags709, "color_range": "tv"})
    # VP9(8bit)。色の情報は colr と vpcC の両方に入る。
    add("vp9_8_709_tv.mp4", *hd, {"matrix": "bt709", "range": "limited", "primaries": "bt709", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES), frame=sdr_frame, bits16=False, matrix="bt709", range_="tv", codec="vp9",
        tags={**tags709, "color_range": "tv"})
    # VP9(8bit)で、色の情報が vpcC にだけある(colr が無い)。HD でも BT.601 と読めることを確かめる。
    add("vp9_8_601_vpcc_only.mp4", *hd,
        {"matrix": "bt601", "range": "limited", "primaries": "smpte170m", "transfer": "sdr", "bits": 8},
        sdr_expected(SDR_PATCHES, "smpte170m"), frame=sdr_frame, bits16=False, matrix="bt601", range_="tv",
        codec="vp9", tags={"colorspace": "smpte170m", "color_primaries": "smpte170m", "color_trc": "smpte170m",
                           "color_range": "tv"}, write_colr=False)
    # BT.2020 の色域の SDR。709 の色を 2020 で表した値を入れ、表示では元の 709 の色に戻ることを確かめる。
    to2020 = conversion("bt709", "bt2020")
    values2020 = [tuple(srgb_oetf(c) for c in mat_mul(to2020, tuple(srgb_eotf(c) for c in v))) for v in SDR_PATCHES]
    add("sdr10_2020_tv_hevc.mp4", *hd,
        {"matrix": "bt2020", "range": "limited", "primaries": "bt2020", "transfer": "sdr", "bits": 10},
        sdr_expected(SDR_PATCHES), frame=raw_frame(*hd, values2020, True), bits16=True, matrix="bt2020", range_="tv",
        codec="hevc10", tags={"colorspace": "bt2020nc", "color_primaries": "bt2020", "color_trc": "bt2020-10",
                              "color_range": "tv"})
    # HDR(PQ)。HDR 表示では明るさそのまま(scRGB は 80cd/m2 が 1.0)、SDR 表示では BT.2390 の EETF で収める。
    peak = 1000.0
    to709 = conversion("bt2020", "bt709")
    pq_values = [tuple(pq_oetf(c) for c in v) for v in HDR_PATCHES]
    hdr_expected = {
        "hdr": [[c / 80.0 for c in mat_mul(to709, v)] for v in HDR_PATCHES],
        "sdr": [[srgb_oetf(min(max(c, 0.0), 1.0)) for c in hdr_to_sdr(v, peak)] for v in HDR_PATCHES],
    }
    add("hdr10_pq_hevc.mp4", *hd,
        {"matrix": "bt2020", "range": "limited", "primaries": "bt2020", "transfer": "pq", "bits": 10},
        hdr_expected, frame=raw_frame(*hd, pq_values, True), bits16=True, matrix="bt2020", range_="tv", codec="hevc10",
        tags={"colorspace": "bt2020nc", "color_primaries": "bt2020", "color_trc": "smpte2084", "color_range": "tv"},
        x265_params="hdr10=1:max-cll=1000,400:master-display=G(13250,34500)B(7500,3000)R(34000,16000)"
                    "WP(15635,16450)L(10000000,1)")
    # VP9(10bit)の HDR(PQ)。最大の明るさの指定は無いので、既定の1000cd/m2として収める(期待値も1000)。
    add("vp9_10_pq.mp4", *hd,
        {"matrix": "bt2020", "range": "limited", "primaries": "bt2020", "transfer": "pq", "bits": 10},
        hdr_expected, frame=raw_frame(*hd, pq_values, True), bits16=True, matrix="bt2020", range_="tv", codec="vp9_10",
        tags={"colorspace": "bt2020nc", "color_primaries": "bt2020", "color_trc": "smpte2084", "color_range": "tv"})
    # HDR(HLG)。表示の明るさが HDR_PATCHES になるようにシーンの値を逆算して入れる。
    hlg_values = [tuple(hlg_oetf(c) for c in hlg_scene_from_nits(v)) for v in HDR_PATCHES]
    add("hdr10_hlg_hevc.mp4", *hd,
        {"matrix": "bt2020", "range": "limited", "primaries": "bt2020", "transfer": "hlg", "bits": 10},
        {"hdr": hdr_expected["hdr"],
         "sdr": [[srgb_oetf(min(max(c, 0.0), 1.0)) for c in hdr_to_sdr(v, 1000.0)] for v in HDR_PATCHES]},
        frame=raw_frame(*hd, hlg_values, True), bits16=True, matrix="bt2020", range_="tv", codec="hevc10",
        tags={"colorspace": "bt2020nc", "color_primaries": "bt2020", "color_trc": "arib-std-b67", "color_range": "tv"})

    with open(os.path.join(args.out, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=1)
    # FramePlayerColorCheck が読む、1行1項目の形式。
    #   video <ファイル> <行列> <範囲> <色域> <伝達関数> <ビット数>
    #   <sdr|hdr> <パッチの番号> <R> <G> <B>
    with open(os.path.join(args.out, "expected.txt"), "w", encoding="utf-8") as f:
        f.write(f"grid {COLUMNS} {ROWS}\n")
        for video in expected["videos"]:
            c = video["color"]
            f.write(f"video {video['file']} {c['matrix']} {c['range']} {c['primaries']} {c['transfer']} {c['bits']}\n")
            for mode in ("sdr", "hdr"):
                for i, rgb in enumerate(video["patches"][mode]):
                    f.write(f"{mode} {i} {rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
    print("作成: expected.json, expected.txt")


if __name__ == "__main__":
    main()
