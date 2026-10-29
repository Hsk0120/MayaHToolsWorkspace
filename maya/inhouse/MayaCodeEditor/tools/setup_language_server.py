"""MCE専用キャッシュへ固定版の解析サーバーを配置する。Mayaの環境は変更しない。"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

VERSION = "1.40.2"
INTEGRITY = "9uld8+5tZC2Gxf8nIynyunK0N4xn01W1ApzLMXDAcuA8uJq2QSfldYn9gSbxn9MWR8wmHDo7GaEHLhlnLFHaJA=="


def install(destination, node):
    """検証済みアーカイブとNodeを配置し、最後に設定を確定する。

    Args:
        destination (Path): 専用キャッシュ。
        node (Path): 既存のNode.js実行ファイル。

    Returns:
        Path: 起動設定のパス。
    """
    if sys.version_info < (3, 10):
        raise RuntimeError("セットアップはPython 3.10以降で実行してください。Maya内の実行版には依存しません。")
    if not node.is_file():
        raise FileNotFoundError("Node.jsが見つかりません。--nodeでnode.exeを指定してください。")
    node_version = subprocess.run([str(node), "--version"], check=True, capture_output=True, text=True, encoding="utf-8", timeout=10).stdout.strip()
    if int(node_version.lstrip("v").split(".")[0]) < 20:
        raise RuntimeError("Node.js 20以降を指定してください。")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ("basedpyright-" + VERSION)
    if not (target / "dist/pyright-langserver.js").is_file():
        if target.exists():
            raise RuntimeError("不完全なインストールが存在します。--destinationで新しい専用フォルダーを指定してください。")
        url = "https://registry.npmjs.org/basedpyright/-/basedpyright-" + VERSION + ".tgz"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") != INTEGRITY:
            raise ValueError("解析サーバーのチェックサムが一致しません。")
        with tempfile.TemporaryDirectory(dir=str(destination)) as temporary:
            staging = Path(temporary)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                for member in archive.getmembers():
                    relative = Path(member.name)
                    if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                        raise ValueError("不正なアーカイブパスです。")
                    if member.isfile():
                        output = staging / relative
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as source, output.open("wb") as stream:
                            shutil.copyfileobj(source, stream)
            (staging / "package").rename(target)
    runtime = destination / "node.exe"
    if node.resolve() != runtime.resolve() and (not runtime.exists() or hashlib.sha256(node.read_bytes()).digest() != hashlib.sha256(runtime.read_bytes()).digest()):
        shutil.copy2(str(node), str(runtime))
    config = destination / "server.json"
    library = destination / "refactor-1.15.0"
    if not (library / "rope/__init__.py").is_file():
        if library.exists():
            raise RuntimeError("不完全なリファクタリング環境が存在します。--destinationで新しい専用フォルダーを指定してください。")
        with tempfile.TemporaryDirectory(dir=str(destination)) as temporary:
            staging = Path(temporary) / "library"
            subprocess.run([sys.executable, "-m", "pip", "install", "--only-binary=:all:",
                            "--target", str(staging), "rope==1.15.0", "pytoolconfig==1.3.1", "packaging==26.3", "platformdirs==4.14.0"], check=True)
            staging.rename(library)
    helper = destination / "refactor_worker.py"
    shutil.copy2(str(Path(__file__).with_name("refactor_worker.py")), str(helper))
    pending = destination / "server.json.tmp"
    pending.write_text(json.dumps({"node": str(runtime), "server": str(target / "dist/pyright-langserver.js"),
                                   "version": VERSION, "refactorPython": sys.executable,
                                   "refactorHelper": str(helper), "refactorLibrary": str(library)}, indent=2), encoding="utf-8")
    pending.replace(config)
    return config


def main():
    """コマンドラインから専用キャッシュへセットアップする。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--destination", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "MayaCodeEditor/language-server")
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.jsをインストールするか--nodeを指定してください。")
    print(install(args.destination, Path(args.node)))


if __name__ == "__main__":
    main()
