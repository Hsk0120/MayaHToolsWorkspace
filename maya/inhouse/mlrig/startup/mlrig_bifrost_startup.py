"""明示呼び出し時にBifrost 3.0.0以降のプラグインをロードする任意ヘルパー。

確認とロードの本体は ``mlib.common.PluginPackage``(``mlib.requirePlugins``)で、
このモジュールは Bifrost 用の設定と起動のタイミングだけを持つ。mlrig パッケージ
(``mlrig/__init__.py``)は import しない。``maya/modules/mlrig_startup.mod`` が
``mlrig/startup`` を ``PYTHONPATH`` へ追加し、標準の ``userSetup.py`` はこのヘルパーを呼ばない。
Bifrostを起動時に読み込みたい利用側だけが :func:`initialize` を明示的に呼ぶ。

環境変数:
    MLRIG_SKIP_BIFROST: ``1`` にするとこの起動処理をすべて行わない(自動テスト用)。
    MLRIG_BIFROST_MIN_VERSION: 必要な最小の版を ``3.0.0`` のように上書きする(動作確認用)。
"""

from maya import cmds

import os

import mlib

MIN_MAYA_VERSION = 2025
DEFAULT_MIN_BIFROST_VERSION = "3.0.0"
# Autodesk の Bifrost パッケージ(PackageContents.xml)が自動ロード対象にしている順序。
PLUGINS = ("mayaVnnPlugin", "bifrostGraph", "flowWedging")
VERSION_PLUGIN = "bifrostGraph"
MODULE = "Bifrost"

_scheduled = False


def minimum_version():
    """必要な最小の Bifrost の版を返す(``MLRIG_BIFROST_MIN_VERSION`` で上書き可能)。

    Returns:
        str: 最小の版。環境変数が空・不正な場合は既定値。
    """
    from mlib.common import Version

    value = os.environ.get("MLRIG_BIFROST_MIN_VERSION")
    return value if Version.parse(value) else DEFAULT_MIN_BIFROST_VERSION


def package():
    """Bifrost の導入確認とロードを行う PluginPackage を作る。

    Returns:
        mlib.common.PluginPackage: Bifrost の定義。
    """
    from mlib.common import PluginPackage

    return PluginPackage(
        "Bifrost",
        plugins=PLUGINS,
        module=MODULE,
        version_plugin=VERSION_PLUGIN,
        minimum_version=minimum_version(),
        minimum_maya=MIN_MAYA_VERSION,
    )


def run(dialog=True):
    """Bifrost の版を確認し、条件を満たせばプラグインをロードする。

    Args:
        dialog (bool | Callable[[str], None]): 警告ダイアログの扱い。テストで関数に差し替える。

    Returns:
        str: ``mlib.common`` の ``LOADED``・``SKIPPED``・``MISSING``・``OUTDATED``・``LOAD_FAILED``。
    """
    result = package().tryLoad(dialog=dialog)
    if result == "loaded":
        from mlib import logger

        logger.info("[mlrig] Bifrost をロードしました")
    return result


def _run_deferred():
    """遅延ロードを実行し、成功・失敗にかかわらず予約状態を解除する。"""
    global _scheduled
    try:
        run()
    finally:
        _scheduled = False


def initialize():
    """GUI 起動時に一度だけ、UI が整ってから :func:`run` を実行する。

    バッチ・スタンドアロンと ``MLRIG_SKIP_BIFROST=1`` では何もしない。
    Maya 2025 未満では :func:`run` が何もしない。
    """
    global _scheduled
    if _scheduled or os.environ.get("MLRIG_SKIP_BIFROST") == "1" or cmds.about(batch=True):
        return
    _scheduled = True
    try:
        mlib.executeDeferred(_run_deferred)
    except Exception:
        _scheduled = False
