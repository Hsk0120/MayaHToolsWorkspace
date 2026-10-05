"""make_codec_testdata.py で作った動画を、コーデック・入れ物ごとにまとめて確かめる。

- コマ番号: ``FramePlayerVerify.exe`` で、GPU と CPU(``--cpu``)の両方。キャッシュを小さくしてシークも確かめる。
- 色: ``FramePlayerColorCheck.exe`` で、GPU と CPU の両方。

1本ごとに時間の上限を設け、止まった(固まった)場合も失敗として記録する。

使い方::

    python run_codec_check.py --data ../build/testdata/codecs --bin ../build/Release
"""

import argparse
import os
import re
import subprocess

TIMEOUT_SECONDS = 120


def run(cmd):
    """実行して(終了コード, 出力)を返す。時間切れは(-1, "時間切れ")。"""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return -1, "時間切れ(止まった)"
    return result.returncode, result.stdout.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="make_codec_testdata.py の出力先")
    parser.add_argument("--bin", required=True, help="FramePlayerVerify.exe などがあるフォルダ")
    args = parser.parse_args()
    verify = os.path.join(args.bin, "FramePlayerVerify.exe")
    color_check = os.path.join(args.bin, "FramePlayerColorCheck.exe")
    frames_dir = os.path.join(args.data, "frames")

    failures = 0
    print("コマ番号(GPU / CPU)")
    with open(os.path.join(frames_dir, "list.txt"), encoding="utf-8") as f:
        entries = [line.split() for line in f if line.strip()]
    for file, count in entries:
        results = []
        for mode in ([], ["--cpu"]):
            code, output = run([verify, os.path.join(frames_dir, file), count, "--cache-mb", "16"] + mode)
            if code == 0:
                results.append("OK")
            else:
                failures += 1
                reason = output.strip().splitlines()[-1] if output.strip() else f"終了コード {code}"
                if code > 0 and "mismatch" in output:
                    counts = re.findall(r"(\w+)\s+frames=\d+ mismatches=(\d+)", output)
                    reason = "不一致 " + " ".join(f"{name}={count}" for name, count in counts)
                results.append("NG: " + reason[:120])
        print(f"  {file:18} {results[0]:10} {results[1]}")

    print("色(GPU / CPU)")
    for mode in ([], ["--cpu"]):
        code, output = run([color_check, os.path.join(args.data, "color")] + mode)
        label = "GPU" if not mode else "CPU"
        if code != 0:
            failures += 1
        for line in output.splitlines():
            if re.match(r"^\S+\.\w+\s", line) or "NG" in line or "期待と違う" in line or "失敗" in line:
                print(f"  [{label}] {line[:200]}")
        print(f"  [{label}] {'OK' if code == 0 else 'FAILED'}")
    print("すべて一致" if failures == 0 else f"失敗 {failures}件")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
