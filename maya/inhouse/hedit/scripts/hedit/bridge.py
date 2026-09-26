"""Mayaメインスレッド専用。補完のためのeval/importは行わない。"""
import json
import os
import re
import sys
import types
from .completion import Index

_index = None


def compact_history(text):
    """既存reporterの履歴をコンパクトに表示する。

    過去の通知境界はMayaが改行へ変換済みで復元できないため、空行を省略する。
    print(a, b)の空白だけの通知は前後の断片に接続する。ライブ出力には適用しない。
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n([ \t]+)\n', r'\1', text)
    return '\n'.join(line for line in text.split('\n') if line.strip()) + ('\n' if text else '')


def output_history():
    """Mayaが保持している履歴を、初回表示用に読み取る。

    Returns:
        str: 既存履歴のJSON。設定・選択・標準エディタの履歴は変更しない。
            Maya側ですでに破棄された履歴は復元できない。
    """
    from maya import cmds, mel
    reporter = mel.eval('global string $gCommandReporter; string $heditReporter = $gCommandReporter;')
    temporary = None
    try:
        if not reporter or not cmds.cmdScrollFieldReporter(reporter, exists=True):
            # 標準エディタを開かず、Mayaが保持する履歴を非表示のreporterで読む。
            temporary = cmds.window()
            cmds.columnLayout()
            reporter = cmds.cmdScrollFieldReporter()
        # 既存の表示用文書を優先する。ただし遡及生成した文書にも通知区切りが
        # 含まれるため、末尾で初期履歴専用のコンパクト化を行う。
        from maya import OpenMayaUI
        try:
            from PySide6 import QtWidgets
            from shiboken6 import wrapInstance
        except ImportError:
            from PySide2 import QtWidgets
            from shiboken2 import wrapInstance
        pointer = OpenMayaUI.MQtUtil.findControl(reporter)
        text = None
        if pointer:
            widget = wrapInstance(int(pointer), QtWidgets.QWidget)
            for kind in (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit):
                document = (wrapInstance(int(pointer), kind) if widget.inherits(kind.__name__)
                            else widget.findChild(kind))
                if document is not None:
                    # Maya内の既存PythonラッパーがQWidget型でもQtプロパティは読める。
                    text = document.property('plainText')
                    break
        if text is None:
            text = cmds.cmdScrollFieldReporter(reporter, query=True, text=True) or ''
        return json.dumps(compact_history(text[-512 * 1024:]), ensure_ascii=True)
    finally:
        if temporary:
            cmds.deleteUI(temporary)


def runtime_module(name):
    """対象モジュールの現在の公開名だけ取得。import/reload/getattrは行わない。"""
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType):
        return None
    def members(mapping, depth=0):
        result = {}
        for key, value in list(mapping.items()):
            if key.startswith('_'):
                continue
            if isinstance(value, types.ModuleType):
                result[key] = {'target': vars(value).get('__name__', '')}
            elif isinstance(value, type) and depth < 1:
                result[key] = {'members': members(vars(value), depth + 1), 'detail': 'class ' + key}
            else:
                result[key] = {}
        return result
    return members(vars(module)), vars(module).get('__file__', '')


def session_path():
    """Mayaバージョン別のタブ復元先。環境変数は隔離テスト用にも使用する。"""
    from maya import cmds
    override = os.environ.get('HEDIT_SESSION_FILE')
    if override:
        return override
    # 名前変更前の未保存タブ・設定を初回のみコピー。旧データは削除しない。
    import shutil
    from pathlib import Path
    base = Path(cmds.internalVar(userPrefDir=True))
    destination = base / 'hedit'
    legacy = base / 'heditor'
    for name in ('tabs.json', 'ui.json', 'preferences.ini'):
        source = legacy / name
        target = destination / name
        if source.is_file() and not target.exists():
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))
    return str(destination / 'tabs.json')



def configuration():
    """有効な検索パスとロード済みモジュールの実在する名前を渡す。"""
    global _index
    # 全モジュールの全属性をJSON化しない。公開名は補完対象だけを取得する。
    modules = {name: {} for name in sys.modules}
    data = {
        "paths": [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)],
        "modules": modules,
    }
    # 過去の公開名を固定せず、補完対象ごとに現在の状態を読む。
    _index = Index(data["paths"], modules=modules, runtime=runtime_module, async_scan=True)
    return json.dumps({'ready': True})



def complete(source):
    """Mayaの同一プロセス内で候補を返す。補完対象はimportしない。"""
    try:
        if _index is None:
            configuration()
        if _index.runtime:
            _index.paths = [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)]
            _index.modules = {name: {} for name in sys.modules}
        items = _index.complete(source)
        return json.dumps({'items': items, 'pending': bool(_index.scan_thread and _index.scan_thread.is_alive())}, ensure_ascii=True)
    except Exception as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=True)


_native_reporter_window = None

def create_output_reporter():
    """ライブ整形専用の非表示reporterを保持する。

    Returns:
        str: C++側で表示文書を参照するためのQtウィジェットアドレス。

    Note:
        標準Script Editorの設定は変更せず、専用ウィンドウを作成する。
        release_output_reporter()で破棄する。
    """
    global _native_reporter_window
    from maya import cmds, OpenMayaUI
    previous_parent = cmds.setParent(query=True)
    try:
        _native_reporter_window = cmds.window()
        cmds.columnLayout()
        reporter = cmds.cmdScrollFieldReporter()
        return str(int(OpenMayaUI.MQtUtil.findControl(reporter)))
    finally:
        if previous_parent:
            cmds.setParent(previous_parent)

def release_output_reporter():
    """プラグイン解除時に専用reporterを破棄する。"""
    global _native_reporter_window
    from maya import cmds
    if _native_reporter_window and cmds.window(_native_reporter_window, exists=True):
        cmds.deleteUI(_native_reporter_window)
    _native_reporter_window = None
