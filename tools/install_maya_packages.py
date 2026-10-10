"""pipのパッケージを、Mayaのバージョン別のフォルダーへ取得する。

``maya/install_packages.bat``(macOSは ``.command``)が、Mayaのバージョンごとに
そのバージョンの ``mayapy`` でこのスクリプトを実行する。

- 取得先は ``maya/site-packages/<Mayaの年>`` だけで、Maya本体やユーザー領域
  (``%APPDATA%\\Python``)には書き込まない。このフォルダーは起動バッチ
  (``maya_core.bat``)だけが ``PYTHONPATH`` に追加するので、通常起動のMayaには影響しない。
- Mayaに同梱のパッケージ(numpyなど)は版を固定して解決し、取得後に取得先から外す。
  同梱品が別の版で上書きされることを防ぐ。
- 新しいフォルダーへ取得してから入れ替えるため、requirements.txtから消したパッケージも残らない。
  Mayaが起動中でファイルが使用中のときは入れ替えに失敗するので、Mayaを閉じてやり直す。

Maya 2022(Python 3.7)でも動くよう、3.7で使える標準ライブラリだけを使う。
"""

import argparse
import json
import os
import re
import shutil
import site
import subprocess
import sys
import tempfile

STAMP_NAME = ".installed-requirements.txt"


def normalize(name):
    """PEP 503 の正規化をしたパッケージ名を返す。

    Args:
        name (str): パッケージ名。

    Returns:
        str: 小文字で、``-``・``_``・``.`` の並びを ``-`` にそろえた名前。
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def has_requirements(path):
    """requirements.txtに、コメントと空行以外の行があるかを返す。

    Args:
        path (str): requirements.txtのパス。

    Returns:
        bool: パッケージの指定が1行でもあればTrue。
    """
    with open(path, encoding="utf-8") as stream:
        return any(line.strip() and not line.strip().startswith("#") for line in stream)


def bundled_site_dirs():
    """Maya本体のsite-packagesを返す(ユーザー領域は含めない)。

    Returns:
        list[str]: 存在するsite-packagesのパス。
    """
    dirs = []
    for path in site.getsitepackages():
        if os.path.basename(path).lower() == "site-packages" and os.path.isdir(path):
            dirs.append(path)
    return dirs


def bundled_packages():
    """Maya本体に同梱のパッケージを ``pip list`` で調べる。

    ``pip freeze`` はファイルから入れたパッケージを ``name @ file:///...`` の形で出す
    (Maya 2027 の numpy など)ため、名前と版を確実に得られる ``pip list`` のJSONを使う。

    Returns:
        dict[str, str]: 正規化した名前から ``name==version`` の行への対応。
    """
    packages = {}
    for path in bundled_site_dirs():
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json", "--path", path, "--disable-pip-version-check"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        for item in json.loads(result.stdout or "[]"):
            packages[normalize(item["name"])] = "{}=={}".format(item["name"], item["version"])
    return packages


def dist_name(dist_info):
    """dist-infoフォルダーのMETADATAからパッケージ名を読む。

    Args:
        dist_info (str): ``*.dist-info`` フォルダーのパス。

    Returns:
        str | None: パッケージ名。読めなければNone。
    """
    metadata = os.path.join(dist_info, "METADATA")
    if not os.path.isfile(metadata):
        return None
    with open(metadata, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("Name:"):
                return line.split(":", 1)[1].strip()
            if not line.strip():
                break
    return None


def remove_distribution(target, dist_info):
    """RECORDに書かれたファイルを消して、1つのパッケージを取得先から外す。

    Args:
        target (str): 取得先のフォルダー。
        dist_info (str): 外すパッケージの ``*.dist-info`` フォルダー。
    """
    root = os.path.realpath(target)
    record = os.path.join(dist_info, "RECORD")
    folders = set()
    lines = []
    if os.path.isfile(record):
        # RECORD自身も一覧に含まれるので、先に読み切って閉じてから消す(Windowsのロック対策)
        with open(record, encoding="utf-8", errors="replace") as stream:
            lines = stream.readlines()
    for line in lines:
        relative = line.split(",", 1)[0].strip()
        if not relative:
            continue
        parts = relative.replace("\\", "/").split("/")
        if parts[0] == ".." and len(parts) >= 2 and parts[-2] in ("bin", "Scripts"):
            # --target では実行ファイルが <target>/bin に置かれるが、RECORDには ../../bin/... と書かれる
            path = os.path.realpath(os.path.join(target, "bin", parts[-1]))
        else:
            path = os.path.realpath(os.path.join(target, relative))
        # 取得先の外を指す行は消さない(安全のため)
        if not path.startswith(root + os.sep):
            continue
        if os.path.isfile(path):
            os.remove(path)
        folders.add(os.path.dirname(path))
    shutil.rmtree(dist_info, ignore_errors=True)
    # 中身が無くなったフォルダーだけを、深いものから消す
    for folder in sorted(folders, key=len, reverse=True):
        while folder.startswith(root + os.sep) and os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
            folder = os.path.dirname(folder)


def drop_bundled(target, bundled):
    """取得先から、Maya同梱と同じパッケージを外す。

    Args:
        target (str): 取得先のフォルダー。
        bundled (dict[str, str]): :func:`bundled_packages` の結果。

    Returns:
        list[str]: 外したパッケージ名。
    """
    dropped = []
    for entry in sorted(os.listdir(target)):
        if not entry.endswith(".dist-info"):
            continue
        dist_info = os.path.join(target, entry)
        name = dist_name(dist_info)
        if name and normalize(name) in bundled:
            remove_distribution(target, dist_info)
            dropped.append(name)
    return dropped


def installed(target):
    """取得先にあるパッケージの名前と版を返す。

    Args:
        target (str): 取得先のフォルダー。

    Returns:
        list[str]: ``name version`` の一覧。
    """
    names = []
    for entry in sorted(os.listdir(target)):
        if entry.endswith(".dist-info"):
            parts = entry[:-len(".dist-info")].split("-")
            names.append("{} {}".format(parts[0], "-".join(parts[1:])))
    return names


def swap(new, target):
    """取得し直したフォルダーを、取得先と入れ替える。

    Args:
        new (str): 取得し直したフォルダー。
        target (str): 取得先のフォルダー。

    Raises:
        OSError: 使用中のファイルがあり入れ替えられないとき。元の取得先は残す。
    """
    old = target + ".old"
    if os.path.exists(old):
        shutil.rmtree(old)
    if os.path.exists(target):
        os.rename(target, old)
    try:
        os.rename(new, target)
    except OSError:
        if os.path.exists(old):
            os.rename(old, target)
        raise
    shutil.rmtree(old, ignore_errors=True)


def main(argv=None):
    """コマンドラインから実行する。

    Args:
        argv (list[str] | None): 引数。Noneならsys.argv。

    Returns:
        int: 終了コード。成功は0、失敗は1。
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requirements", required=True, help="requirements.txt")
    parser.add_argument("--target", required=True, help="maya/site-packages/<year>")
    args = parser.parse_args(argv)

    requirements = os.path.abspath(args.requirements)
    target = os.path.abspath(args.target)
    new = target + ".new"
    print("Python {} ({})".format(sys.version.split()[0], sys.executable))

    if os.path.exists(new):
        shutil.rmtree(new)
    os.makedirs(new)

    if has_requirements(requirements):
        bundled = bundled_packages()
        handle, constraints = tempfile.mkstemp(suffix=".txt", prefix="maya-constraints-")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write("\n".join(sorted(bundled.values())) + "\n")
        # ユーザー設定の user=true と --target は同時に使えないため、子プロセスでは無効にする
        env = dict(os.environ, PIP_USER="0")
        command = [sys.executable, "-m", "pip", "install", "--target", new, "-r", requirements,
                   "-c", constraints, "--no-warn-script-location", "--disable-pip-version-check", "--no-input"]
        try:
            code = subprocess.call(command, env=env)
        finally:
            os.remove(constraints)
        if code != 0:
            shutil.rmtree(new, ignore_errors=True)
            print("[ERROR] pip install failed (exit code {}). The previous packages are kept.".format(code))
            return 1
        for name in drop_bundled(new, bundled):
            print("Using the package bundled with Maya: {}".format(name))
    else:
        print("requirements.txt lists no packages.")

    shutil.copyfile(requirements, os.path.join(new, STAMP_NAME))
    try:
        swap(new, target)
    except OSError as error:
        shutil.rmtree(new, ignore_errors=True)
        print("[ERROR] Could not replace {}: {}".format(target, error))
        print("[ERROR] Close Maya of this version and run the installer again.")
        return 1

    packages = installed(target)
    print("Installed to {}: {}".format(target, ", ".join(packages) if packages else "(none)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
