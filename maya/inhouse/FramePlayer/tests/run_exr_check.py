"""FramePlayerの自前のEXRの読み込みを、oiiotool(OpenImageIO)の読み込みと画素単位で比べる。

ノイズの画像(幅・高さが4や16・32の倍数でない、負の値や1を超える値を含むRGBA)を、
圧縮・画素の型・走査線/タイルを変えてoiiotoolで書き、次の2つが一致するかを確かめる。

- FramePlayerImageConvert(readExr)で読んで、圧縮なしの半精度のEXRにしたもの
- oiiotoolで同じファイルを読んで、半精度にしたもの

可逆でない圧縮(B44・B44A・DWAA・DWAB・floatのPXR24)も、同じファイルを読んだ結果どうしを比べるので一致するはず。
32bit浮動小数点は半精度へ丸めるので、丸め方の違いの分(半精度の1段)だけ許す。
DWAA・DWABは逆DCTの浮動小数点の計算の順序で半精度の1段ずれる画素がまれにあるので、0.5%未満なら許す。

使い方::

    python run_exr_check.py --oiiotool oiiotool.exe --convert ..\\build\\Release\\FramePlayerImageConvert.exe ^
        --out ..\\build\\testdata\\exr_check
"""

import argparse
import os
import re
import subprocess
import sys

SIZE = "643x371"
COMPRESSIONS = ["none", "rle", "zips", "zip", "piz", "pxr24", "b44", "b44a", "dwaa", "dwab"]
# (名前, oiiotoolの追加の引数)
LAYOUTS = [
    ("half", ["-d", "half"]),
    ("float", ["-d", "float"]),
    ("half_tiled", ["-d", "half", "--tile", "64", "32"]),
    ("float_tiled", ["-d", "float", "--tile", "128", "64"]),
]


def run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode, result.stdout.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--oiiotool", required=True)
    parser.add_argument("--convert", required=True, help="FramePlayerImageConvert.exe")
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", help="名前にこの文字列を含むものだけ確かめる")
    args = parser.parse_args()
    convert = os.path.abspath(args.convert)
    os.makedirs(args.out, exist_ok=True)
    # 元の画像: 一様なノイズに、滑らかな傾き(B44・DWAの圧縮が効く部分)を重ねる。
    base = os.path.join(args.out, "base.exr")
    code, text = run([args.oiiotool, "--pattern", "noise:type=uniform:min=-1:max=6:seed=7", SIZE, "4",
                      "--pattern", "fill:topleft=0,0,0,1:topright=4,0,1,1:bottomleft=0,2,8,1:bottomright=1,1,1,1",
                      SIZE, "4", "--add", "-d", "float", "-o", base])
    if code != 0:
        print(text)
        return 2
    failed = []
    for layout, layout_args in LAYOUTS:
        for compression in COMPRESSIONS:
            name = f"{layout}_{compression}"
            if args.only and args.only not in name:
                continue
            source = os.path.join(args.out, name + ".exr")
            mine = os.path.join(args.out, name + "_mine.exr")
            reference = os.path.join(args.out, name + "_ref.exr")
            code, text = run([args.oiiotool, base] + layout_args + ["--compression", compression, "-o", source])
            if code != 0:
                print(f"作成失敗 {name}: {text.strip()}")
                failed.append(name)
                continue
            code, text = run([convert, source, mine])
            if code != 0:
                print(f"NG  {name:18s} 読めない: {text.strip()}")
                failed.append(name)
                continue
            run([args.oiiotool, source, "-d", "half", "--compression", "none", "-o", reference])
            code, text = run([args.oiiotool, "--diff", "--fail", "1e-6", "--failpercent", "0", mine, reference])
            match = re.search(r"Max error\s*=\s*([0-9.e+-]+)", text)
            worst = float(match.group(1)) if match else (0.0 if "PASS" in text else float("nan"))
            # 32bit浮動小数点は、半精度への丸め方の違いで1段ずれることがある(値の1/1024ほど)。
            limit = 0.0 if layout.startswith("half") else 8.0 / 1024.0
            ok = worst <= limit
            note = ""
            if not ok and compression.startswith("dwa"):
                # DWAは逆DCTを浮動小数点で計算するので、計算の順序の違いで、圧縮した非線形の値が半精度の1段
                # ずれる画素がまれにある(リニアに戻すと大きな値ほど差が広がる)。ずれる画素がごく少なければ合格。
                percent = re.search(r"([0-9.]+)%\) over", text)
                share = float(percent.group(1)) if percent else 100.0
                ok = share < 0.5
                note = f"(半精度の1段ずれる画素 {share}%)"
            print(f"{'OK' if ok else 'NG'}  {name:18s} 最大の差 {worst:.6g}{note}")
            if not ok:
                failed.append(name)
                print("    " + "\n    ".join(text.strip().splitlines()[-6:]))
    print("全て合格" if not failed else "不一致: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
