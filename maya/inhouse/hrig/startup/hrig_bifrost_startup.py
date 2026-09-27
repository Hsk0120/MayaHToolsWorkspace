"""明示呼び出し時にBifrost 3.0.0以降のプラグインをロードする任意ヘルパー。

確認とロードの本体は ``hlib.plugins.PluginPackage``(``hlib.requirePlugins``)で、
このモジュールは Bifrost 用の設定と起動のタイミングだけを持つ。hrig パッケージ
(``hrig/__init__.py``)は import しない。``maya/modules/hrig_startup.mod`` が
``hrig/startup`` を ``PYTHONPATH`` へ追加し、標準の ``userSetup.py`` はこのヘルパーを呼ばない。
Bifrostを起動時に読み込みたい利用側だけが :func:`initialize` を明示的に呼ぶ。

環境変数:
    HRIG_SKIP_BIFROST: ``1`` にするとこの起動処理をすべて行わない(自動テスト用)。
    HRIG_BIFROST_MIN_VERSION: 必要な最小の版を ``3.0.0`` のように上書きする(動作確認用)。
"""

import os

import maya.cmds as cmds
import maya.utils as maya_utils

MIN_MAYA_VERSION = 2025
DEFAULT_MIN_BIFROST_VERSION = "3.0.0"
# Autodesk の Bifrost パッケージ(PackageContents.xml)が自動ロード対象にしている順序。
PLUGINS = ("mayaVnnPlugin", "bifrostGraph", "flowWedging")
VERSION_PLUGIN = "bifrostGraph"
MODULE = "Bifrost"

_scheduled = False


def minimum_version():
    """必要な最小の Bifrost の版を返す(``HRIG_BIFROST_MIN_VERSION`` で上書き可能)。

    Returns:
        str: 最小の版。環境変数が空・不正な場合は既定値。
    """
    from hlib.utils import Version

    value = os.environ.get("HRIG_BIFROST_MIN_VERSION")
    return value if Version.parse(value) else DEFAULT_MIN_BIFROST_VERSION


def package():
    """Bifrost の導入確認とロードを行う PluginPackage を作る。

    Returns:
        hlib.plugins.PluginPackage: Bifrost の定義。
    """
    from hlib.plugins import PluginPackage

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
        str: ``hlib.plugins`` の ``LOADED``・``SKIPPED``・``MISSING``・``OUTDATED``・``LOAD_FAILED``。
    """
    result = package().ensure_loaded(dialog=dialog)
    if result == "loaded":
        print("[hrig] Bifrost をロードしました")
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

    バッチ・スタンドアロンと ``HRIG_SKIP_BIFROST=1`` では何もしない。
    Maya 2025 未満では :func:`run` が何もしない。
    """
    global _scheduled
    if _scheduled or os.environ.get("HRIG_SKIP_BIFROST") == "1" or cmds.about(batch=True):
        return
    _scheduled = True
    try:
        maya_utils.executeDeferred(_run_deferred)
    except Exception:
        _scheduled = False
