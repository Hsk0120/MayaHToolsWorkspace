"""Python不要の静止サムネイル用FFmpegを、LGPL構成・静的CRTで再ビルドする。"""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

from build_static_qt import VERSION, compiler_environment, digest


FFMPEG_HASH = "60d39d4b7d8155b4b9e87c8096fde0429ec219f6bfb1dbf1a0fef031006f91e6"
MAKE_HASH = "2408af61717dae87b00c855b132769a125c708907fc94a46bb16dae076113e5c"


def download(url, target, expected):
    """公式配布先から取得し、固定した対応ソースのハッシュを確認する。"""
    if not target.exists():
        subprocess.run(["curl.exe", "--fail", "--location", "--connect-timeout", "15", "--max-time", "180",
                        "--output", str(target), url], check=True)
    if digest(target) != expected:
        raise ValueError(f"Checksum mismatch: {target}")


def msys(path):
    """ドライブ付き絶対パスをGit Bashの引数へ変換する。"""
    value = Path(path).resolve().as_posix()
    return "/" + value[0].lower() + value[2:]


def main():
    """外部コーデック/GPL/ネットワークを含めず、静止画像出力用exeを構築する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--configure-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="既存の同じ設定のconfigure結果でコンパイルを再開")
    parser.add_argument("--source-archives", type=Path, help="同梱FFmpegソースを使用する。make開発ツールは任意")
    parser.add_argument("--qt-root", type=Path, help="build_static_qt.pyの作業先。sources/installを含むフォルダー")
    parser.add_argument("--work-root", type=Path, help="メディアの作業先。深い配置では短い絶対パスを指定する")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    output = args.work_root.resolve() if args.work_root else root / ".maya-output/native-media"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "ffmpeg-n8.0.1.tar.gz"
    package = output / "make-4.4.1-2-x86_64.pkg.tar.zst"
    if args.source_archives:
        for target, expected in ((archive, FFMPEG_HASH), (package, MAKE_HASH)):
            supplied = args.source_archives / target.name
            # makeは開発用ツールで製品へリンクしない。同梱しない場合は公式配布を取得する。
            if target == package and not supplied.exists():
                continue
            if not supplied.is_file() or digest(supplied) != expected:
                raise ValueError(f"Missing or mismatched build input: {supplied}")
            if not target.exists():
                shutil.copy2(supplied, target)
    download("https://api.github.com/repos/FFmpeg/FFmpeg/tarball/n8.0.1", archive, FFMPEG_HASH)
    source = output / "FFmpeg-FFmpeg-d22ecc4"
    if not source.exists():
        with tarfile.open(archive) as bundle:
            bundle.extractall(output, filter="data")
    download("https://repo.msys2.org/msys/x86_64/" + package.name, package, MAKE_HASH)
    if not (output / "usr/bin/make.exe").exists():
        subprocess.run(["tar.exe", "-xf", str(package), "-C", str(output), "usr/bin/make.exe"], check=True)
    git = Path(shutil.which("git") or "C:/Program Files/Git/cmd/git.exe").resolve().parents[1]
    bash = git / "usr/bin/bash.exe"
    if not bash.is_file():
        raise FileNotFoundError("Git for Windows (Bash) is required")
    _, _, env = compiler_environment()
    env["PATH"] += os.pathsep + str(git / "usr/bin")
    env["MSYS2_ARG_CONV_EXCL"] = "-libpath:;-MT"
    sdk = args.qt_root.resolve() if args.qt_root else root / ".maya-output/static-qt" / VERSION
    zlib = output / "zlib"
    zlib.mkdir(exist_ok=True)
    qt_zlib = sdk / "sources" / f"qtbase-everywhere-src-{VERSION}" / "src/3rdparty/zlib/src"
    # Qtソース由来のzlibを同じ静的libで使用する。ヘッダーのQt公開指定だけを除く。
    # Z_PREFIXは保持する。変更点と対応ソースは再リンク資料にも含める。
    header = (qt_zlib / "zlib.h").read_text(encoding="utf-8")
    header = header.replace('#include <qglobal.h>\n#undef ZEXTERN\n#define ZEXTERN Q_CORE_EXPORT',
                            '/* QPE build adaptation: Qt export annotation removed; static zlib. */')
    (zlib / "zlib.h").write_text(header, encoding="utf-8")
    configuration = (qt_zlib / "zconf.h").read_text(encoding="utf-8")
    configuration = configuration.replace("#if defined(HAVE_UNISTD_H) || !defined(WIN32)", "/* QPE adaptation: FFmpeg defines unavailable features as zero. */\n#if (defined(HAVE_UNISTD_H) && HAVE_UNISTD_H) || !defined(WIN32)")
    (zlib / "zconf.h").write_text(configuration, encoding="utf-8")
    shutil.copy2(sdk / "install/lib/Qt6BundledZLIB.lib", zlib / "zlib.lib")
    build = output / "build"
    build.mkdir(exist_ok=True)
    configure = [msys(source / "configure"), "--toolchain=msvc", "--arch=x86_64", "--target-os=win64",
                 "--disable-autodetect", "--disable-gpl", "--disable-nonfree", "--disable-network",
                 "--disable-x86asm", "--disable-doc", "--disable-debug", "--disable-ffplay", "--disable-ffprobe",
                 "--disable-devices", "--disable-encoders", "--enable-encoder=png", "--disable-muxers",
                 "--enable-muxer=image2pipe", "--disable-filters", "--enable-filter=scale,format",
                 "--disable-avdevice", "--disable-shared", "--enable-static", "--enable-zlib",
                 "--extra-cflags=-MT -I" + zlib.as_posix(), "--extra-ldflags=-libpath:" + zlib.as_posix()]
    manifest = {"ffmpegVersion": "8.0.1", "sourceSha256": FFMPEG_HASH, "makeSha256": MAKE_HASH,
                "zlibLibrarySha256": digest(zlib / "zlib.lib"), "configure": configure, "complete": False}
    record = output / "build-manifest.json"
    if args.resume:
        if not record.is_file() or not (build / "ffbuild/config.mak").is_file():
            raise ValueError("No verified configuration exists; run without --resume")
        previous = json.loads(record.read_text(encoding="utf-8"))
        for key in ("sourceSha256", "makeSha256", "zlibLibrarySha256", "configure"):
            if previous.get(key) != manifest[key]:
                raise ValueError(f"Configuration changed ({key}); run without --resume")
    else:
        subprocess.run([str(bash), "--noprofile", "--norc", "-c", " ".join(map(shlex.quote, configure))],
                       cwd=build, env=env, check=True)
    record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.configure_only:
        command = [msys(output / "usr/bin/make.exe"), "-j", str(args.jobs), "ffmpeg.exe"]
        subprocess.run([str(bash), "--noprofile", "--norc", "-c", " ".join(map(shlex.quote, command))],
                       cwd=build, env=env, check=True)
        executable = build / "ffmpeg.exe"
        license_text = subprocess.run([str(executable), "-L"], capture_output=True, text=True, check=True).stdout
        if "Lesser General Public License" not in license_text:
            raise RuntimeError("The media helper is not an LGPL build")
        shutil.copy2(executable, output / "qpe-media.exe")
        manifest.update(complete=True, executableSha256=digest(executable), license=license_text)
    record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
