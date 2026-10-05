"""make_sequence_testdata.py で作った連番画像を、FramePlayerVerify で順に確かめる。

使い方::

    python run_sequence_check.py --verify ..\\build\\Release\\FramePlayerVerify.exe --data ..\\build\\testdata\\sequences [--cpu]

欠けのある連番は、欠けた番号のコマが「欠け」として扱われ、それ以外のコマが正しく読めれば合格とする。
"""

import argparse
import os
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", required=True, help="FramePlayerVerify.exe")
    parser.add_argument("--data", required=True, help="make_sequence_testdata.py の --out")
    parser.add_argument("--cpu", action="store_true", help="GPUを使わない")
    parser.add_argument("--only", help="この名前の連番だけ確かめる")
    args = parser.parse_args()
    frames = os.path.join(args.data, "frames")
    failed = []
    with open(os.path.join(frames, "list.txt"), encoding="utf-8") as f:
        rows = [line.split() for line in f if line.strip()]
    for name, first, count, missing in rows:
        if args.only and name != args.only:
            continue
        cmd = [os.path.abspath(args.verify), os.path.join(frames, first), count, "--bits", "12", "--cache-mb", "16"]
        if missing != "-":
            cmd += ["--missing", missing]
        if args.cpu:
            cmd.append("--cpu")
        start = time.time()
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout.decode("utf-8", "replace").strip().splitlines()
        status = "OK" if result.returncode == 0 else "NG"
        print(f"{status} {name:18s} {time.time() - start:5.1f}s  {output[-1] if output else ''}")
        if result.returncode != 0:
            failed.append(name)
            for line in output[-8:]:
                print("    " + line)
    print("全て合格" if not failed else "不合格: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
