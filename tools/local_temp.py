"""作業用の一時ファイルを、このワークスペースの中(``.maya-output/temp``)へ作る。

システムの一時フォルダー(``%TEMP%``)は、ワークスペースと別のドライブにあることがある。別のドライブどうしでは
相対パスを作れず、移動も複製になるので、作業用のファイルはワークスペースと同じ場所へ置く。
ワークスペースへ書き込めないとき(読み取り専用など)は、止めずにシステムの一時フォルダーを使う。

``.maya-output/`` はGitの対象外。
"""

import contextlib
import os
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".maya-output" / "temp"

#: この秒数より前に作られた残りは、前の実行が消せなかったものとして掃除する(動いている実行のものは消さない)。
STALE_SECONDS = 24 * 60 * 60


def local_directory():
    """一時ファイルを置くフォルダーを返す。

    Returns:
        str | None: ワークスペースの中の一時フォルダー。作れないときはNone(システムの一時フォルダーを使う合図)。
    """
    try:
        LOCAL.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if not os.access(str(LOCAL), os.W_OK):
        return None
    _remove_stale()
    return str(LOCAL)


def _remove_stale():
    """前の実行が消せずに残した、古い一時フォルダー・ファイルを消す。

    Mayaを使う実行は、Mayaが終わるまで一時フォルダーを掴んでいるので、終了時に消せないことがある。
    次の実行の最初に、1日より前のものだけを消す。消せないものは、そのままにして続ける。
    """
    limit = time.time() - STALE_SECONDS
    try:
        entries = list(LOCAL.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.stat().st_mtime >= limit:
                continue
            if entry.is_dir():
                shutil.rmtree(str(entry), ignore_errors=True)
            else:
                entry.unlink()
        except OSError:
            continue


@contextlib.contextmanager
def temporary_directory(prefix="work-"):
    """一時フォルダーを作り、抜けるときに消す。

    Args:
        prefix (str): フォルダー名の先頭に付ける文字列。

    Yields:
        str: 作った一時フォルダーのパス。
    """
    try:
        path = tempfile.mkdtemp(prefix=prefix, dir=local_directory())
    except OSError:
        # ワークスペースの中へ作れないときは、システムの一時フォルダーで続ける。
        path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def as_default(prefix="run-"):
    """この実行の間、``tempfile`` と ``TEMP``・``TMP`` の一時フォルダーをワークスペースの中にする。

    テストが ``tempfile`` で作るファイルも、Mayaが ``TEMP`` へ作るファイルも、ワークスペースと同じ場所へ置く。
    抜けるときに、作ったフォルダーを消して設定を戻す。作れないときは何も変えずに続ける。

    Args:
        prefix (str): フォルダー名の先頭に付ける文字列。

    Yields:
        str | None: 使っている一時フォルダー。システムの一時フォルダーのままならNone。
    """
    base = local_directory()
    if base is None:
        yield None
        return
    try:
        path = tempfile.mkdtemp(prefix=prefix, dir=base)
    except OSError:
        yield None
        return
    saved = (os.environ.get("TEMP"), os.environ.get("TMP"), tempfile.tempdir)
    os.environ["TEMP"] = os.environ["TMP"] = path
    tempfile.tempdir = path
    try:
        yield path
    finally:
        for key, value in zip(("TEMP", "TMP"), saved):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tempfile.tempdir = saved[2]
        shutil.rmtree(path, ignore_errors=True)


def make_file(prefix="work-", suffix=""):
    """一時ファイルを作る(消すのは呼び出し側)。

    Args:
        prefix (str): ファイル名の先頭に付ける文字列。
        suffix (str): ファイル名の末尾に付ける文字列(拡張子など)。

    Returns:
        tuple[int, str]: ``tempfile.mkstemp`` と同じ、(ファイル記述子, パス)。
    """
    try:
        return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=local_directory())
    except OSError:
        return tempfile.mkstemp(prefix=prefix, suffix=suffix)
