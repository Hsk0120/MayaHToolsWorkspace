"""Media Foundation で再生できるコーデック・入れ物ごとに、確認用の動画を作る。

作るもの(``--out`` の下):

- ``frames/``: コマ番号を縦縞で描いた動画(README「コマ送りの正確さの確認」と同じ絵)。
  ``frames/list.txt`` に「ファイル名 コマ数」を1行ずつ書く。``FramePlayerVerify.exe`` で確かめる。
- ``color/``: 色の付いた四角(パッチ)の動画と期待値(``expected.txt``)。``FramePlayerColorCheck.exe`` で確かめる。
  色の情報は付けない(コーデックの決まりと FramePlayer の推定どおりに読めるかを確かめる)。

対象は、Windows に入っている Media Foundation の映像デコーダー(H.264・HEVC・AV1・VP9・VP8・MPEG-1/2・
MPEG-4 Part 2・H.263・MS-MPEG4 v2/v3・WMV7/8・MJPEG・DV、拡張機能のTheora)のうち、ffmpeg で作れるもの。
WMV9/VC-1・WMV Screen は ffmpeg で作れないので対象外。

Windows 側の制限で再生できない次のものは作らない(README「対応形式」に記載):
MPEG-4 Part 2 の B フレーム(Advanced Simple Profile。Windows のデコーダーは Simple Profile だけ)、
mov の DV、映像だけの短い(10秒程度の)mpg・vob(音声を付ければ開ける)、ogg・ogv(Theora は mkv なら読める)。

使い方::

    python make_codec_testdata.py --ffmpeg C:/path/to/ffmpeg.exe --out ../build/testdata/codecs

ffmpeg は確認用動画を作るためだけに使い、プレイヤーには含めない。
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_color_testdata as color  # noqa: E402

FRAME_COUNT = 48  # 2秒(24fps)。12コマごとにキーフレームを置き、シークも確かめる。

# (名前, 拡張子, 大きさ, ffmpegの引数(エンコーダー), 入れ物の引数, 色の確認に使うか)
# 大きさが決まっているコーデック(H.263・DV)はその大きさで作る。
H264 = ["-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-g", "12", "-bf", "2"]
HEVC8 = ["-c:v", "libx265", "-x265-params", "crf=10:keyint=12:log-level=error", "-pix_fmt", "yuv420p"]
HEVC10 = ["-c:v", "libx265", "-x265-params", "crf=10:keyint=12:log-level=error", "-pix_fmt", "yuv420p10le",
          "-profile:v", "main10"]
AV1 = ["-c:v", "libaom-av1", "-crf", "12", "-cpu-used", "8", "-row-mt", "1", "-g", "12", "-pix_fmt", "yuv420p"]
AV1_10 = ["-c:v", "libaom-av1", "-crf", "12", "-cpu-used", "8", "-row-mt", "1", "-g", "12",
          "-pix_fmt", "yuv420p10le"]
VP9 = ["-c:v", "libvpx-vp9", "-crf", "10", "-b:v", "0", "-g", "12", "-row-mt", "1", "-pix_fmt", "yuv420p"]
VP9_10 = ["-c:v", "libvpx-vp9", "-crf", "10", "-b:v", "0", "-g", "12", "-row-mt", "1", "-pix_fmt", "yuv420p10le",
          "-profile:v", "2"]
VP8 = ["-c:v", "libvpx", "-crf", "4", "-b:v", "20M", "-g", "12", "-pix_fmt", "yuv420p"]
MPEG2 = ["-c:v", "mpeg2video", "-q:v", "2", "-g", "12", "-bf", "2", "-pix_fmt", "yuv420p"]
MPEG1 = ["-c:v", "mpeg1video", "-q:v", "2", "-g", "12", "-bf", "2", "-pix_fmt", "yuv420p"]
MPEG4 = ["-c:v", "mpeg4", "-q:v", "2", "-g", "12", "-bf", "0", "-pix_fmt", "yuv420p"]
H263 = ["-c:v", "h263", "-q:v", "2", "-g", "12", "-pix_fmt", "yuv420p"]
MSMPEG4V2 = ["-c:v", "msmpeg4v2", "-q:v", "2", "-g", "12", "-pix_fmt", "yuv420p"]
MSMPEG4V3 = ["-c:v", "msmpeg4", "-q:v", "2", "-g", "12", "-pix_fmt", "yuv420p", "-vtag", "MP43"]
WMV1 = ["-c:v", "wmv1", "-q:v", "2", "-g", "12", "-pix_fmt", "yuv420p"]
WMV2 = ["-c:v", "wmv2", "-q:v", "2", "-g", "12", "-pix_fmt", "yuv420p"]
MJPEG = ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj420p"]
DV = ["-c:v", "dvvideo", "-pix_fmt", "yuv411p"]
THEORA = ["-c:v", "libtheora", "-q:v", "10", "-g", "12", "-pix_fmt", "yuv420p"]
# mpg・vobは、映像だけで短いとWindowsが開けないので、無音の音声を付ける。
SILENT_MP2 = ["-c:a", "mp2", "-shortest"]

HD = (1280, 720)
CIF = (352, 288)
NTSC = (720, 480)

CASES = [
    ("h264", "mp4", HD, H264, [], True),
    ("h264", "mov", HD, H264, [], False),
    ("h264", "mkv", HD, H264, [], False),
    ("h264", "ts", HD, H264, [], False),
    ("h264", "m2ts", HD, H264, ["-f", "mpegts", "-mpegts_m2ts_mode", "1"], False),
    ("h264", "avi", HD, H264, [], False),
    ("h264", "3gp", HD, H264, [], False),
    ("hevc8", "mp4", HD, HEVC8 + ["-tag:v", "hvc1"], [], True),
    ("hevc10", "mp4", HD, HEVC10 + ["-tag:v", "hvc1"], [], True),
    ("hevc8", "mkv", HD, HEVC8, [], False),
    ("hevc8", "ts", HD, HEVC8, [], False),
    ("av1", "mp4", HD, AV1, [], True),
    ("av1_10", "mp4", HD, AV1_10, [], True),
    ("av1", "mkv", HD, AV1, [], False),
    ("av1", "webm", HD, AV1, [], False),
    ("vp9", "webm", HD, VP9, [], True),
    ("vp9_10", "webm", HD, VP9_10, [], True),
    ("vp9", "mkv", HD, VP9, [], False),
    ("vp9", "mp4", HD, VP9, [], False),
    ("vp8", "webm", HD, VP8, [], True),
    ("vp8", "mkv", HD, VP8, [], False),
    ("mpeg2", "mpg", HD, MPEG2 + SILENT_MP2, [], True),
    ("mpeg2", "ts", HD, MPEG2, [], False),
    ("mpeg2", "vob", NTSC, MPEG2 + SILENT_MP2, ["-f", "vob"], False),
    ("mpeg1", "mpg", HD, MPEG1 + SILENT_MP2, [], True),
    ("mpeg4", "mp4", HD, MPEG4, [], True),
    ("mpeg4", "mov", HD, MPEG4, [], False),
    ("mpeg4", "avi", HD, MPEG4, [], False),
    ("h263", "3gp", CIF, H263, [], True),
    ("msmpeg4v2", "avi", HD, MSMPEG4V2, [], True),
    ("msmpeg4v3", "avi", HD, MSMPEG4V3, [], True),
    ("wmv1", "wmv", HD, WMV1, [], True),
    ("wmv2", "wmv", HD, WMV2, [], True),
    ("mjpeg", "avi", HD, MJPEG, [], True),
    ("mjpeg", "mov", HD, MJPEG, [], False),
    ("dv", "avi", NTSC, DV, [], True),
    ("theora", "mkv", HD, THEORA, [], True),
]

# コーデックが決まったフレームレートしか持てないもの(DVのNTSCは29.97fps)。
RATES = {"dv": "30000/1001"}


def stripes_filter(width, height):
    """コマ番号の2進数を縦縞で描く ffmpeg のフィルター(README と同じ。12本、上端は白・下端は黒)。"""
    return (f"geq=lum='if(lt(Y,H/8),235,if(gt(Y,7*H/8),16,if(mod(floor(N/pow(2,floor(X*12/W))),2),235,16)))'"
            f":cb=128:cr=128,format=yuv420p")


def run(cmd, stdin=None):
    """ffmpeg を実行する。失敗したら False(そのコーデック・入れ物は飛ばす)。"""
    result = subprocess.run(cmd, input=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("  失敗:", result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:])
        return False
    return True


def expected_color(name, width, height):
    """色の情報が無い動画を FramePlayer が読むべき解釈(コーデックの決まりと推定の決まり)。

    MJPEG は JPEG(JFIF)の決まりで BT.601・全範囲。それ以外は大きさから推定する
    (HD は BT.709、SD は BT.601 で、高さ 576/288 は 625本、それ以外は 525本の色域)。
    """
    hd = width > 1024 or height > 576
    primaries = "bt709" if hd else ("bt470bg" if height in (576, 288) else "smpte170m")
    bits = 10 if name.endswith("_10") or name == "hevc10" else 8
    if name == "mjpeg":
        return {"matrix": "bt601", "range": "full", "primaries": primaries, "transfer": "sdr", "bits": bits}
    return {"matrix": "bt709" if hd else "bt601", "range": "limited", "primaries": primaries, "transfer": "sdr",
            "bits": bits}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", required=True, help="ffmpeg.exe のパス")
    parser.add_argument("--out", required=True, help="出力先のフォルダ")
    args = parser.parse_args()
    frames_dir = os.path.join(args.out, "frames")
    color_dir = os.path.join(args.out, "color")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(color_dir, exist_ok=True)
    base = [args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]

    listed = []
    videos = []
    for name, ext, (width, height), codec, muxer, check_color in CASES:
        file = f"{name}.{ext}"
        print("作成:", file)
        # コマ番号の縞。
        rate = RATES.get(name, "24")
        audio = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] if "-c:a" in codec else []
        cmd = base + ["-f", "lavfi", "-i", f"nullsrc=s={width}x{height}:r={rate}"] + audio + [
            "-frames:v", str(FRAME_COUNT), "-vf", stripes_filter(width, height)] + codec + muxer + [
            os.path.join(frames_dir, file)]
        if run(cmd):
            listed.append(f"{file} {FRAME_COUNT}")
        if not check_color:
            continue
        # 色のパッチ。期待する解釈の行列・範囲で RGB から YUV にする(色の情報は付けない)。
        want = expected_color(name, width, height)
        matrix = "bt709" if want["matrix"] == "bt709" else "bt601"
        range_ = "pc" if want["range"] == "full" else "tv"
        frame = color.raw_frame(width, height, color.SDR_PATCHES, False)
        # mpg・vobは短すぎるとWindowsが開けないので、4秒にする。
        repeat = 95 if audio else 23
        vf = (f"loop=loop={repeat}:size=1:start=0,scale=in_range=pc:out_color_matrix={matrix}:out_range={range_}"
              f":flags=accurate_rnd+full_chroma_int")
        cmd = base + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", rate, "-i", "-"] + audio + [
            "-vf", vf] + codec + muxer + [os.path.join(color_dir, file)]
        if run(cmd, frame):
            videos.append((file, want, color.sdr_expected(color.SDR_PATCHES, want["primaries"])))

    with open(os.path.join(frames_dir, "list.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(listed) + "\n")
    with open(os.path.join(color_dir, "expected.txt"), "w", encoding="utf-8") as f:
        f.write(f"grid {color.COLUMNS} {color.ROWS}\n")
        for file, c, patches in videos:
            f.write(f"video {file} {c['matrix']} {c['range']} {c['primaries']} {c['transfer']} {c['bits']}\n")
            for mode in ("sdr", "hdr"):
                for i, rgb in enumerate(patches[mode]):
                    f.write(f"{mode} {i} {rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
    print(f"作成: frames/list.txt({len(listed)}本), color/expected.txt({len(videos)}本)")


if __name__ == "__main__":
    main()
