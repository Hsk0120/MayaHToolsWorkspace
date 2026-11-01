"""実際の静的ビルドに対応するソース、ライセンス、構成を配布フォルダーへ集める。"""

import json
from pathlib import Path
import shutil

from build_static_qt import VERSION, SOURCES, digest
from build_native_media import FFMPEG_HASH


def collect(root):
    """固定した上流アーカイブだけを複製し、任意フォルダーの再帰複製を避ける。

    Args:
        root: QuickPathExplorerの絶対パス。
    """
    sdk = root / ".maya-output/static-qt" / VERSION
    media = root / ".maya-output/native-media"
    qt_manifest = json.loads((sdk / "build-manifest.json").read_text(encoding="utf-8"))
    media_manifest = json.loads((media / "build-manifest.json").read_text(encoding="utf-8"))
    if not qt_manifest.get("complete") or not media_manifest.get("complete"):
        raise ValueError("Builds must complete before collecting corresponding sources")
    if digest(media / "qpe-media.exe") != media_manifest["executableSha256"]:
        raise ValueError("Media binary does not match its build record")
    inputs = [(sdk / "sources" / f"{module}-everywhere-src-{VERSION}.tar.xz", expected)
              for module, expected in SOURCES.items()]
    inputs.append((media / "ffmpeg-n8.0.1.tar.gz", FFMPEG_HASH))
    for archive, expected in inputs:
        if digest(archive) != expected:
            raise ValueError(f"Corresponding source mismatch: {archive}")
    destination = root / "third_party"
    (destination / "sources").mkdir(exist_ok=True)
    for archive, _ in inputs:
        shutil.copy2(archive, destination / "sources" / archive.name)
    licenses = destination / "licenses"
    notices = ["QuickPathExplorer — Third-party software notices\n\n"
               "QPE code: MIT; see LICENSE.\n"
               "Windows: Qt 6.8.3 (QtBase / QtSvg), statically linked under LGPL-3.0.\n"
               "Qt: Copyright (C) The Qt Company Ltd. and other contributors.\n"
               "Maya: uses the Qt provided by the installed Autodesk Maya.\n"
               "Media: FFmpeg 8.0.1, LGPL-2.1-or-later, GPL/nonfree components disabled.\n"
               "FFmpeg: Copyright (c) the FFmpeg developers.\n"
               "ZIP: miniz 3.0.2, MIT.\n\n"
               "The full QPE buildable source and corresponding Qt/FFmpeg sources are included\n"
               "in this distribution. See BUILDING.md and third_party/sources.\n"
               "You may modify these libraries, rebuild/relink QPE, and debug those changes.\n"
               "No signature, activation, or installation key is required for a relinked build.\n"
               "The media helper is embedded and prepared in the user cache on demand;\n"
               "an independently rebuilt helper can be selected in settings / QPE_FFMPEG.\n"
               "Third-party components retain their own license terms.\n"]
    for module in SOURCES:
        source = sdk / "sources" / f"{module}-everywhere-src-{VERSION}"
        shutil.copytree(source / "LICENSES", licenses / module, dirs_exist_ok=True)
        # Qt同梱第三者コードの著作権・許諾文も抜き出す。元の全内容は対応ソースに保持する。
        for attribution in source.rglob("qt_attribution.json"):
            relative = attribution.relative_to(source)
            target = licenses / module / "attributions" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(attribution, target)
            # 上流QtにはLicense欄に実改行を含むattributionもある。原本は変更せず保持する。
            entries = json.loads(attribution.read_text(encoding="utf-8"), strict=False)
            if isinstance(entries, dict):
                entries = [entries]
            for entry in entries:
                files = entry.get("LicenseFile", "")
                if isinstance(files, str):
                    files = [files]
                for name in files:
                    original = (attribution.parent / name).resolve()
                    if original.is_relative_to(source.resolve()) and original.is_file():
                        copied = licenses / module / "attributions" / original.relative_to(source.resolve())
                        copied.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(original, copied)
    ffmpeg = media / "FFmpeg-FFmpeg-d22ecc4"
    (licenses / "ffmpeg").mkdir(parents=True, exist_ok=True)
    for original in list(ffmpeg.glob("COPYING*")) + [ffmpeg / "LICENSE.md"]:
        shutil.copy2(original, licenses / "ffmpeg" / original.name)
    shutil.copytree(sdk / "install/sbom", destination / "sbom", dirs_exist_ok=True)
    for name, value in (("qt-build.json", qt_manifest), ("media-build.json", media_manifest)):
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # 実際のビルドで修正したzlibヘッダーを明示して残す。再生成方法はbuild_native_media.py。
    shutil.copytree(media / "zlib", destination / "media-zlib-headers", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.lib"))
    for original in (root / "LICENSE", root / "third_party/miniz/LICENSE",
                     licenses / "qtbase/LGPL-3.0-only.txt", licenses / "qtbase/GPL-3.0-only.txt",
                     licenses / "ffmpeg/COPYING.LGPLv2.1"):
        notices.append("\n\n===== " + original.relative_to(root).as_posix() + " =====\n" + original.read_text(encoding="utf-8"))
    (destination / "NOTICES.txt").write_text("".join(notices), encoding="utf-8")
    hashes = {archive.name: expected for archive, expected in inputs}
    (destination / "sources/SHA256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(f"Collected {len(inputs)} source archives and license records in {destination}")


if __name__ == "__main__":
    collect(Path(__file__).resolve().parents[1])
