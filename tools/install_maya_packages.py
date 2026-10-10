"""pipのパッケージを、グループごとにMayaのバージョン別のフォルダーへ取得する。

``maya/install_packages.bat``(macOSは ``.command``)が、Mayaのバージョンごとに
そのバージョンの ``mayapy`` でこのスクリプトを実行する。

- ``maya/requirements/<名前>.txt`` が1グループで、``maya/site-packages/<年>/<名前>`` へ
  ``pip install --target`` する。取得先はGit対象外で、Maya本体やユーザー領域
  (``%APPDATA%\\Python``)には書き込まない。
- ``PYTHONPATH`` へ通すのは ``pip_<名前>.mod`` で、``maya/modules`` に置いたグループだけが使われる。
  ``.mod`` が無いグループには、無効の ``.mod`` を ``maya/modules_disabled`` に作る。
- グループは依存も含めて自己完結させる(グループ間で依存を共有しない)。
- Mayaに同梱のパッケージ(numpyなど)は版を固定して解決し、取得後に取得先から外す。
- 新しいフォルダーへ取得してから入れ替える。起動中のMayaが使うファイルがあると入れ替えに失敗する。
- 取得に失敗したグループ(そのPythonの版に対応する配布が無い等)は ``<名前>.failed`` に
  requirementsの写しを残し、起動バッチが同じ内容で取得をやり直さないようにする。

Maya 2022(Python 3.7)でも動くよう、3.7で使える標準ライブラリだけを使う。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import site
import subprocess
import sys
import tempfile

STAMP_NAME = ".installed-requirements.txt"
FAILED_SUFFIX = ".failed"
LEGACY_STAMP = ".installed-requirements.txt"
MOD_VERSIONS = (2022, 2023, 2024, 2025, 2026, 2027)
MOD_PLATFORMS = ("win64", "mac")


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


def write_mod(name, modules_dir, disabled_dir):
    """グループの ``pip_<名前>.mod`` が無ければ、無効側に作る。

    Args:
        name (str): グループ名。
        modules_dir (str): 有効な.modのフォルダー(maya/modules)。
        disabled_dir (str): 無効な.modのフォルダー(maya/modules_disabled)。

    Returns:
        str | None: 作った.modのパス。既にあればNone。
    """
    file_name = "pip_{}.mod".format(name)
    if os.path.exists(os.path.join(modules_dir, file_name)) or os.path.exists(os.path.join(disabled_dir, file_name)):
        return None
    blocks = []
    for version in MOD_VERSIONS:
        for platform in MOD_PLATFORMS:
            blocks.append("+ MAYAVERSION:{0} PLATFORM:{1} pip_{2} 1.0.0 ../site-packages/{0}/{2}\n"
                          "PYTHONPATH +:= .".format(version, platform, name))
    path = os.path.join(disabled_dir, file_name)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n\n".join(blocks) + "\n")
    return path


def install_group(name, requirements, target_root, bundled):
    """1グループを取得して入れ替える。

    Args:
        name (str): グループ名。
        requirements (str): グループのrequirementsファイル。
        target_root (str): ``maya/site-packages/<年>``。
        bundled (dict[str, str]): :func:`bundled_packages` の結果。

    Returns:
        bool: 成功したらTrue。
    """
    target = os.path.join(target_root, name)
    new = target + ".new"
    failed = target + FAILED_SUFFIX
    if os.path.exists(new):
        shutil.rmtree(new)
    os.makedirs(new)

    if has_requirements(requirements):
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
            shutil.copyfile(requirements, failed)
            print("[ERROR] {}: pip install failed (exit code {}). The previous packages are kept.".format(name, code))
            return False
        for package in drop_bundled(new, bundled):
            print("{}: using the package bundled with Maya: {}".format(name, package))
        # pip が取得先の直下に残す空の.whlを消す(パッケージ本体ではない)
        for entry in os.listdir(new):
            path = os.path.join(new, entry)
            if entry.endswith(".whl") and os.path.isfile(path):
                os.remove(path)

    shutil.copyfile(requirements, os.path.join(new, STAMP_NAME))
    try:
        swap(new, target)
    except OSError as error:
        shutil.rmtree(new, ignore_errors=True)
        print("[ERROR] {}: could not replace {}: {}".format(name, target, error))
        print("[ERROR] Close Maya of this version and run the installer again.")
        return False
    if os.path.exists(failed):
        os.remove(failed)
    packages = installed(target)
    print("{}: installed to {}: {}".format(name, target, ", ".join(packages) if packages else "(none)"))
    return True


def file_digest(path):
    """ファイル内容のSHA-1を返す。

    Args:
        path (str): ファイルのパス。

    Returns:
        str: 16進のSHA-1。
    """
    digest = hashlib.sha1()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_duplicates(target_root):
    """同じバージョンの各グループで、中身が同じファイルをハードリンクにまとめる。

    グループは依存も含めて自己完結させているので、scipyなどが複数のグループに入る。
    同じ相対パス・同じ大きさ・同じ内容のファイルを1つのデータにまとめ、使用量を減らす。
    読み込まれる内容は変わらない。ハードリンクを作れないファイルシステムでは何もしない。

    Args:
        target_root (str): ``maya/site-packages/<年>``。

    Returns:
        int: まとめて減らしたバイト数。
    """
    # 相対パスと大きさが同じファイルだけを候補にする(内容の比較はその中だけ)
    groups = {}
    for group in sorted(os.listdir(target_root)):
        group_dir = os.path.join(target_root, group)
        if not os.path.isdir(group_dir) or group.endswith((".new", ".old")):
            continue
        for folder, _, files in os.walk(group_dir):
            for file_name in files:
                path = os.path.join(folder, file_name)
                relative = os.path.relpath(path, group_dir)
                size = os.path.getsize(path)
                if relative != STAMP_NAME and size >= 4096:
                    groups.setdefault((relative, size), []).append(path)

    saved = 0
    for (_, size), paths in groups.items():
        if len(paths) < 2:
            continue
        originals = []
        for path in paths:
            # 既に同じデータ(リンク済み)なら内容を読まない
            if any(os.path.samefile(original, path) for original, _ in originals):
                continue
            digest = file_digest(path)
            match = next((original for original, known in originals if known == digest), None)
            if match is None:
                originals.append((path, digest))
                continue
            temporary = path + ".link"
            try:
                os.link(match, temporary)
                os.replace(temporary, path)
                saved += size
            except OSError:
                if os.path.exists(temporary):
                    os.remove(temporary)
                return saved
    return saved


def remove_legacy_layout(target_root):
    """グループに分ける前の配置(site-packages/<年>直下に全部)を消す。

    Args:
        target_root (str): ``maya/site-packages/<年>``。
    """
    if os.path.isfile(os.path.join(target_root, LEGACY_STAMP)):
        print("Removing the old layout in {}".format(target_root))
        shutil.rmtree(target_root)


def main(argv=None):
    """コマンドラインから実行する。

    Args:
        argv (list[str] | None): 引数。Noneならsys.argv。

    Returns:
        int: 終了コード。全グループ成功で0、1つでも失敗で1。
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requirements-dir", required=True, help="maya/requirements")
    parser.add_argument("--target-root", required=True, help="maya/site-packages/<year>")
    parser.add_argument("--modules-dir", required=True, help="maya/modules")
    parser.add_argument("--disabled-modules-dir", required=True, help="maya/modules_disabled")
    parser.add_argument("--groups", nargs="*", default=[], help="groups to install (default: all)")
    args = parser.parse_args(argv)

    requirements_dir = os.path.abspath(args.requirements_dir)
    target_root = os.path.abspath(args.target_root)
    available = sorted(os.path.splitext(entry)[0] for entry in os.listdir(requirements_dir) if entry.endswith(".txt"))
    groups = args.groups or available
    unknown = [name for name in groups if name not in available]
    if unknown:
        print("[ERROR] No requirements file for: {}".format(", ".join(unknown)))
        return 1
    print("Python {} ({})".format(sys.version.split()[0], sys.executable))

    remove_legacy_layout(target_root)
    if not os.path.isdir(target_root):
        os.makedirs(target_root)
    bundled = bundled_packages()
    failures = []
    for name in groups:
        print("-- {}".format(name))
        if not install_group(name, os.path.join(requirements_dir, name + ".txt"), target_root, bundled):
            failures.append(name)
        created = write_mod(name, os.path.abspath(args.modules_dir), os.path.abspath(args.disabled_modules_dir))
        if created:
            print("{}: created disabled module file {}".format(name, created))
    saved = link_duplicates(target_root)
    if saved:
        print("Linked files shared by groups: {:.0f} MB saved".format(saved / 1048576.0))
    if failures:
        print("[ERROR] Failed groups: {}".format(", ".join(failures)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
