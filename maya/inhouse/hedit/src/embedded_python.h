/** @file embedded_python.h
 * @brief hedit の旧 scripts/hedit/*.py を文字列として埋め込み、プラグインロード時にMaya同梱の
 * CPython上へ展開するブートストラップ。
 * @details ディスク上の.pyファイル・PYTHONPATHへ依存せず、.mll単体でロード可能にするための
 * 仕組み。Python言語自体の構文解析(ast)・compile()はCPythonでしか正確に行えないため、
 * ロジックはC++の生文字列としてバイナリへ埋め込み、MGlobal::executePythonCommand経由で
 * Maya本体が既に保持するインタプリタ上に展開する(追加のPythonリンクは不要)。
 * 各モジュールはsys.meta_path先頭のimportフックから配るため、通常の.pyと同じく
 * 初回importまで実行されない(docking等のGUI依存モジュールをバッチで実行しない)。
 * @note MSVCの制約: 生文字列の区切り子は16文字以内、1リテラルは約16KB以内に保つ。
 */
#pragma once
#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <string>
#include <utility>

namespace hedit {
namespace embedded {

/** @brief hedit.__init__ 相当。プラグインのロードとエディタ表示の窓口。 */
inline const char* kInitSource = R"HEDIT_INIT(
__version__ = '0.2.10'


def show(floating=None):
    """hedit.mllをロードして編集画面を表示する。"""
    from maya import cmds
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('hedit')
    from . import docking
    host = docking.show(floating=floating)
    from . import startup
    startup.opened()
    return host


def restore():
    """Mayaのワークスペース復元から呼び出す。"""
    from maya import cmds, utils
    from . import startup
    reopen = startup.previous_open()
    if not reopen:
        # 閉じたドックは必要になるまでQt本体を生成しない。
        utils.executeDeferred(startup.hide_if_closed)
        return None
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('hedit')
    from . import docking
    host = docking.show(restore=True)
    startup.opened()
    return host
)HEDIT_INIT";

/** @brief hedit.completion 相当。標準ライブラリだけの静的補完エンジン。 */
inline const char* kCompletionSource = R"HEDIT_COMPLETION(
"""Maya内で呼び出す標準ライブラリだけの静的補完。対象ソースは実行しない。"""
import ast
import builtins
import keyword
import os
import re
import sys
import threading
import time


class Index:
    def __init__(self, paths, modules=None, runtime=None, async_scan=False):
        self.paths = paths
        self.modules = modules or {}
        self.cache = {}
        self.runtime = runtime
        self.top = set(sys.builtin_module_names)
        self.top.update(name.split('.')[0] for name in self.modules)
        self.top_scanned = False
        self.async_scan = async_scan
        self.scan_thread = None
        self.scan_started = 0
        self.local_source = None
        self.local_symbols = {}

    def scan_top(self):
        """GUIではファイル列挙を同一プロセスの別スレッドで実行する。"""
        if self.async_scan:
            if self.scan_thread and (self.scan_thread.is_alive() or time.monotonic()-self.scan_started < 5):
                return
            self.scan_started = time.monotonic()
            self.scan_thread = threading.Thread(target=self._scan_top, args=(tuple(self.paths), tuple(self.modules)), daemon=True)
            self.scan_thread.start()
        else:
            self._scan_top(tuple(self.paths), tuple(self.modules))

    def _scan_top(self, paths, modules):
        """Maya APIやUIを呼ばず、完了した候補集合を一度に交換する。"""
        top = set(sys.builtin_module_names)
        top.update(name.split('.')[0] for name in modules)
        for path in paths:
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.name.endswith('.py'):
                            top.add(entry.name[:-3])
                        elif entry.is_dir() and entry.name.isidentifier():
                            top.add(entry.name)
            except OSError:
                pass
        self.top_scanned = True
        self.top = top

    def locals(self, source):
        """同じ宣言部分を再解析せず、構文エラー時の全行再試行を最大4回に制限する。"""
        if source == self.local_source:
            return dict(self.local_symbols)
        lines = source.splitlines()
        symbols = {}
        for _ in range(4):
            if not lines:
                break
            try:
                symbols = self.symbols(ast.parse('\n'.join(lines)))
                break
            except SyntaxError as error:
                # エラー位置以後をまとめて除外する。1行ずつ削ると二乗時間になる。
                lines = lines[:max(0, min(len(lines)-1, (error.lineno or 1)-1))]
        self.local_source, self.local_symbols = source, symbols
        return dict(symbols)

    def module(self, name):
        """ディレクトリ型パッケージと.pyを解決。mtime/sizeで再解析する。"""
        result = dict(self.modules.get(name, {}))
        if self.runtime:
            live = self.runtime(name)
            if live is not None:
                result, filename = live
                # 読み込み済みモジュールは判明しているファイルだけ調べる。
                if filename and filename.endswith('.py'):
                    result.update(self.source(filename, name))
                return result
        # 実在する公開名の補完に、ネットワークドライブ等の走査を要求しない。
        if result:
            return result
        parts = name.split('.')
        if not all(part.isidentifier() for part in parts):
            return result
        for root in self.paths:
            base = os.path.join(root, *parts)
            filename = base + '.py'
            if os.path.isdir(base):
                filename = os.path.join(base, '__init__.py')
                try:
                    with os.scandir(base) as entries:
                        for entry in entries:
                            stem = entry.name[:-3] if entry.name.endswith('.py') else entry.name
                            if stem.isidentifier() and not stem.startswith('_') and (entry.is_dir() or entry.name.endswith('.py')):
                                result.setdefault(stem, {'target': name + '.' + stem})
                except OSError:
                    pass
            if not os.path.isfile(filename):
                continue
            try:
                stat = os.stat(filename)
                stamp = (stat.st_mtime_ns, stat.st_size)
                cached = self.cache.get(filename)
                if cached is None or cached[0] != stamp:
                    import tokenize
                    with tokenize.open(filename) as stream:
                        tree = ast.parse(stream.read())
                    cached = (stamp, self.symbols(tree, name + '.__init__' if os.path.basename(filename) == '__init__.py' else name))
                    self.cache[filename] = cached
                # 実行時の公開名を残しつつ関数シグネチャを静的情報で補う。
                result.update(cached[1])
            except (OSError, SyntaxError, UnicodeError):
                pass
            break
        return result

    def source(self, filename, name):
        """確定済みパスだけを再解析。編集中の構文エラーは最後の正常な候補を維持。"""
        cached = self.cache.get(filename)
        try:
            stat = os.stat(filename)
            stamp = (stat.st_mtime_ns, stat.st_size)
            if cached is None or cached[0] != stamp:
                import tokenize
                with tokenize.open(filename) as stream:
                    tree = ast.parse(stream.read())
                module = name + '.__init__' if os.path.basename(filename) == '__init__.py' else name
                cached = (stamp, self.symbols(tree, module))
                self.cache[filename] = cached
        except (OSError, SyntaxError, UnicodeError):
            pass
        return dict(cached[1]) if cached else {}

    def symbols(self, tree, module=''):
        result = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in getattr(node.args, 'posonlyargs', []) + node.args.args]
                if node.args.vararg:
                    args.append('*' + node.args.vararg.arg)
                args.extend(arg.arg for arg in node.args.kwonlyargs)
                if node.args.kwarg:
                    args.append('**' + node.args.kwarg.arg)
                result[node.name] = {'detail': node.name + '(' + ', '.join(args) + ')'}
            elif isinstance(node, ast.ClassDef):
                result[node.name] = {'members': self.symbols(node, module), 'detail': 'class ' + node.name}
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result[alias.asname or alias.name.split('.')[0]] = {'target': alias.name if alias.asname else alias.name.split('.')[0]}
            elif isinstance(node, ast.ImportFrom):
                parent = node.module or ''
                if node.level:
                    parent = '.'.join(module.split('.')[:-node.level] + ([parent] if parent else []))
                for alias in node.names:
                    if alias.name != '*':
                        # from . import nodes は親の同じ公開名を再解決すると循環する。
                        result[alias.asname or alias.name] = (
                            {'target': parent + '.' + alias.name} if node.level and not node.module
                            else {'from': parent, 'name': alias.name})
            elif isinstance(node, ast.If) and (
                    isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
                    or isinstance(node.test, ast.Attribute) and isinstance(node.test.value, ast.Name)
                    and node.test.value.id == 'typing' and node.test.attr == 'TYPE_CHECKING'):
                # 型宣言も静的に読む。対象パッケージをimport・実行することはない。
                result.update(self.symbols(node, module))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        result[target.id] = {}
        return result

    def resolve(self, item, depth=0):
        if depth > 8:
            return {}
        if 'from' in item:
            parent = self.module(item['from'])
            value = parent.get(item['name'], {'target': item['from'] + '.' + item['name']})
            if value == item:
                return self.module(item['from'] + '.' + item['name'])
            return self.resolve(value, depth + 1)
        if item.get('target'):
            return self.module(item['target'])
        return item.get('members', {})

    def complete(self, source):
        if len(source) > 200000:
            return []
        match = re.search(r'[A-Za-z_][\w.]*$|(?<=\.)$', source)
        token = match.group() if match else ''
        line = source.split('\n')[-1]
        if re.match(r'^\s*(import|from)\s+[\w.]*$', line):
            if '.' in token:
                parent, prefix = token.rsplit('.', 1)
                symbols = self.module(parent)
            else:
                self.scan_top()
                prefix, symbols = token, {name: {} for name in self.top | {n.split('.')[0] for n in self.modules}}
        else:
            # 編集途中の末尾行を順に除去し、確定した宣言を解析する。
            # 補完している最終行を除いた宣言部分は、文字を打つたびには変化しない。
            symbols = self.locals(source.rpartition('\n')[0])
            from_match = re.match(r'^\s*from\s+([\w.]+)\s+import\s+(\w*)$', line)
            if from_match:
                symbols, prefix = self.module(from_match.group(1)), from_match.group(2)
            elif '.' in token:
                parts = token.split('.')
                item = symbols.get(parts[0], {'target': parts[0]})
                for part in parts[1:-1]:
                    item = self.resolve(item).get(part, {})
                symbols, prefix = self.resolve(item), parts[-1]
            else:
                prefix = token
                base = {name: {'kind': 'builtin'} for name in vars(builtins)}
                base.update({name: {'kind': 'keyword'} for name in keyword.kwlist})
                symbols = dict(base, **symbols)
        return [dict({'name': name, 'detail': value.get('detail', '')}, **({'kind': value['kind']} if 'kind' in value else {}))
                for name, value in sorted(symbols.items())
                if name.startswith(prefix) and (prefix.startswith('_') or not name.startswith('_'))][:250]
)HEDIT_COMPLETION";

/** @brief hedit.bridge 相当。Maya出力履歴・タブ復元先・補完/静的解析の橋渡し。 */
inline const char* kBridgeSource = R"HEDIT_BRIDGE(
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
)HEDIT_BRIDGE";

/** @brief hedit.docking 相当。Maya標準ドッキングホスト(MayaQWidgetDockableMixin)。 */
inline const char* kDockingSource = R"HEDIT_DOCKING(
"""Maya標準のドッキングホスト。編集画面はC++製ウィジェットを使用する。"""
from maya import cmds, OpenMayaUI
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance, getCppPointer, isValid
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance, getCppPointer, isValid

from hedit import __version__

WINDOW_TITLE = f'hedit {__version__} - Python / MEL'
CONTROL = 'heditDockWorkspaceControl'
# 保存済みの旧ドックがある場合はその配置を再利用する。画面名はheditに更新する。
if (cmds.workspaceControl('HEditorDockWorkspaceControl', exists=True)
        and not cmds.workspaceControl(CONTROL, exists=True)):
    CONTROL = 'HEditorDockWorkspaceControl'
_host = globals().get('_host')
_opening = False


class heditDock(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """フローティングとMayaレイアウトへのドッキングを扱うホスト。"""
    def __init__(self):
        super(heditDock, self).__init__()
        self.setObjectName('heditDock')
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1050, 740)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        editor = wrapInstance(int(cmds.hedit()), QtWidgets.QMainWindow)
        editor.setWindowFlags(QtCore.Qt.Widget)
        layout.addWidget(editor)

    @property
    def editor(self):
        # Qt5ではMaya側のreparentで既存のPythonラッパーが無効化される。
        # Mayaコマンドが保持する生存中のQPointerから改めてラップする。
        return wrapInstance(int(cmds.hedit()), QtWidgets.QMainWindow)


def show(floating=None, restore=False):
    """一つのホストを再利用し、明示起動では閉じてから開き直す。

    Args:
        floating (bool | None): 指定時だけ浮動状態を変更する。
        restore (bool): Maya復元からの呼出。閉じ直す処理を行わない。

    Returns:
        QWidget: 未保存コードと配置を保持する唯一のホスト。
    """
    global _host, _opening
    if _opening:
        return _host
    _opening = True
    try:
        # Pythonのreloadや参照消失後も、Mayaが所有するホストを回収する。
        hosts = [widget for widget in QtWidgets.QApplication.allWidgets()
                 if isValid(widget) and widget.objectName() == 'heditDock']
        if _host is None or not isValid(_host):
            _host = next((widget for widget in hosts
                          if widget.findChild(QtWidgets.QMainWindow, 'hedit') is not None),
                         hosts[0] if hosts else None)
        for widget in hosts:
            if widget is not _host:
                widget.hide()
        if _host is not None and not restore:
            # 本体のcloseEventでタブを保存する。取消時は現在の画面をそのまま残す。
            # workspaceControlは破棄せず、Mayaのドッキング配置を維持する。
            if not _host.editor.close():
                return _host
            _host.hide()
        return _show(floating=floating, restore=restore)
    finally:
        _opening = False


def _show(floating=None, restore=False):
    """既存ホストを再利用する。通常の閉じる操作ではタブを保持する。"""
    global _host
    # 本体生成は内部reporterなどのMaya UIを作るため、生成前に復元先を確定する。
    # getCurrentParentを生成後に読むと、非表示reporter側へ誤挿入され得る。
    restore_parent = None
    if restore:
        restore_parent = OpenMayaUI.MQtUtil.findControl(CONTROL) or OpenMayaUI.MQtUtil.getCurrentParent()
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.workspaceControl(CONTROL, edit=True, label=WINDOW_TITLE)
    if _host is None or not isValid(_host):
        _host = heditDock()
        # 閉じたworkspaceControlのuiScriptは本体生成を遅延する。
        # 明示的なshowで初めて生成した場合、既存のMayaレイアウトへ挿入する。
        if not restore and cmds.workspaceControl(CONTROL, exists=True):
            parent = OpenMayaUI.MQtUtil.findControl(CONTROL)
            OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
    _host.setWindowTitle(WINDOW_TITLE)
    if restore:
        parent = restore_parent
        if not parent:
            raise RuntimeError('hedit workspaceControl was not found')
        OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
        _host.setVisible(True)
        _host.editor.show()
        return _host
    if cmds.workspaceControl(CONTROL, exists=True):
        if floating is not None:
            cmds.workspaceControl(CONTROL, edit=True, floating=floating)
        # 旧版で別レイアウトへ入ったホストも、明示的な再表示時に修復する。
        parent = OpenMayaUI.MQtUtil.findControl(CONTROL)
        control = wrapInstance(int(parent), QtWidgets.QWidget)
        if not control.isAncestorOf(_host):
            OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
        # Qt5ではuiScript直後の浮動ドックにrestoreを掛けるとネイティブ
        # ウィンドウ再生成で落ちる場合がある。保持中のコントロールを表示する。
        cmds.workspaceControl(CONTROL, edit=True, visible=True)
        _host.setVisible(True)
        _host.editor.show()
    else:
        _host.show(dockable=True, floating=True if floating is None else floating,
                   area='bottom', retain=True, width=1050, height=740, plugins=['hedit'],
                   uiScript='import hedit; hedit.restore()')
    return _host


def release():
    """プラグイン解除時に空のドックを残さない。タブの保存はC++側で行う。"""
    global _host
    if cmds.workspaceControl(CONTROL, exists=True):
        # deleteUI中のcloseCommandから配置を照会すると、Qt5では破棄中の
        # workspaceControlへ再入してクラッシュする。状態はuninstallで保存済み。
        cmds.workspaceControl(CONTROL, edit=True, closeCommand='')
        cmds.deleteUI(CONTROL)
    elif _host is not None and isValid(_host):
        _host.deleteLater()
    _host = None
)HEDIT_DOCKING";

/** @brief hedit.analysis 相当。compile()だけを使う構文・警告チェック。 */
inline const char* kAnalysisSource = R"HEDIT_ANALYSIS(
"""Maya同梱Pythonでコードを実行せずに構文・コンパイラ警告を調べる。"""
import json
import warnings


def analyze(source):
    """100万文字超/2万行以上を省略。型推論・外部import・ユーザーコード実行なし。"""
    if len(source) > 1_000_000 or source.count('\n') >= 20_000:
        return json.dumps({'diagnostics': [], 'skipped': 'File too large (limit: 1,000,000 characters / 20,000 lines)'})
    diagnostics = []
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always', SyntaxWarning)
            # コンパイルだけ行う。生成したcodeオブジェクトは実行しない。
            compile(source, '<hedit>', 'exec', dont_inherit=True)
        for warning in captured:
            if issubclass(warning.category, SyntaxWarning):
                diagnostics.append({'severity': 'warning', 'line': warning.lineno,
                                    'message': str(warning.message)})
    except SyntaxError as exc:
        diagnostics.append({'severity': 'error', 'line': exc.lineno or 1,
                            'message': exc.msg})
    except (ValueError, RecursionError, MemoryError) as exc:
        return json.dumps({'diagnostics': [], 'skipped': 'Analysis unavailable: ' + str(exc)})
    return json.dumps({'diagnostics': diagnostics[:100]}, ensure_ascii=True)
)HEDIT_ANALYSIS";

/** @brief hedit.startup 相当。Windowメニュー登録と前回画面の復元。 */
inline const char* kStartupSource = R"HEDIT_STARTUP(
"""Mayaのメニュー登録と、前回開いていたheditの復元。

ユーザーのSecurity設定・プラグイン自動ロード設定は変更しない。
開閉状態はhedit専用ui.json、ドック配置はMayaのワークスペースへ保存する。
"""
import json
import os
from pathlib import Path
from maya import cmds, utils

_timer = None
_quitting = False
_opened = False
_quit_job = None
_last = None


def state_path():
    """Path: 現在のMaya/隔離テストに対応するUI復元ファイル。"""
    from .bridge import session_path
    return Path(session_path()).with_name('ui.json')


def _debug_log(event, **fields):
    """開閉状態の変化を追記する調査用ログ(挙動には影響しない)。

    「再起動時に復元されない」不具合の原因(誰が何をきっかけに閉じた扱いにしたか)を
    次回の発生時に確認するための一時的な仕組み。失敗しても他の処理は継続する。
    """
    import time
    try:
        path = state_path().with_name('startup-debug.log')
        line = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'event': event}
        line.update(fields)
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + '\n')
    except OSError:
        pass


def previous_open():
    """bool: 保存済みの開閉状態。未保存の場合は明示的な復元を許可する。"""
    try:
        return bool(json.loads(state_path().read_text(encoding='utf-8')).get('open', True))
    except (OSError, ValueError):
        return True


def hide_if_closed():
    """Mayaが非表示ドックのuiScriptを呼んだ場合も、閉じた状態を維持する。"""
    from .docking import CONTROL
    if not _opened and cmds.workspaceControl(CONTROL, exists=True):
        # uiScript直後のcloseはQt5の浮動ウィンドウを破棄し、次のrestoreで
        # 無効なネイティブハンドルを参照し得る。復元済みUIを非表示に留める。
        cmds.workspaceControl(CONTROL, edit=True, visible=False)


def record():
    """現在のドック状態を原子的に保存する。終了処理中は上書きしない。"""
    global _last
    from .docking import CONTROL
    if _quitting or not cmds.workspaceControl(CONTROL, exists=True):
        return
    state = {'version': 1, 'open': _opened,
             'floating': cmds.workspaceControl(CONTROL, query=True, floating=True),
             'layout': cmds.workspaceLayoutManager(query=True, current=True)}
    if state == _last:
        return
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('ui.{}.tmp'.format(os.getpid()))
    try:
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        os.replace(str(temporary), str(path))
        _last = state
    except OSError as exc:
        cmds.warning('hedit layout could not be saved: {}'.format(exc))


def closed(*unused):
    """ユーザーが閉じた時だけ、次回の自動表示を停止する。"""
    global _opened
    from .docking import CONTROL
    _debug_log('closed', quitting=_quitting,
               control_exists=cmds.workspaceControl(CONTROL, exists=True))
    if not _quitting:
        _opened = False
        record()


def quitting(*unused):
    """MayaがUIを閉じる前に最終状態を保存し、以後の変更を凍結する。"""
    global _quitting
    _debug_log('quitting', opened=_opened)
    # ドックの入れ子・タブグループはMaya自身のワークスペースに保存する。
    # workspaceControl.stateStringは版によって空リストを返し、配置復元には使えない。
    cmds.workspaceLayoutManager(save=True)
    record()
    _quitting = True
    if _timer:
        _timer.stop()


def opened():
    """表示後に配置の監視を始める。タイマーと終了通知は重複させない。"""
    global _timer, _opened, _quit_job
    from .docking import CONTROL, QtCore, _host
    _opened = True
    cmds.workspaceControl(CONTROL, edit=True, closeCommand='import hedit.startup; hedit.startup.closed()')
    if _timer is None:
        _timer = QtCore.QTimer(_host)
        _timer.setInterval(1000)
        _timer.timeout.connect(record)
    _timer.start()
    if _quit_job is None:
        _quit_job = cmds.scriptJob(event=['quitApplication', quitting], runOnce=True)
    _debug_log('opened')
    record()


def restore_previous():
    """前回開いていた時だけ表示する。配置はMayaのワークスペース復元を優先する。"""
    if cmds.about(batch=True):
        return
    try:
        state = json.loads(state_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if state.get('version') != 1:
        return
    from .docking import CONTROL
    existing = cmds.workspaceControl(CONTROL, exists=True)
    visible = existing and cmds.workspaceControl(CONTROL, query=True, visible=True)
    _debug_log('restore_previous', state=state, existing=existing, visible=visible)
    if not state.get('open'):
        hide_if_closed()
        return
    if visible:
        # Mayaのワークスペース復元(保存済みworkspaceControlのuiScriptによる
        # hedit.restore()呼び出し)が、この時点で既に表示・状態記録まで済ませている。
        # ここで改めてhedit.show()を呼ぶと、既存の表示を一度close()してから
        # 開き直すため、ユーザーが閉じた場合と同じcloseCommandが発火し、
        # 「閉じた」記録が一瞬だけ残ってしまう。直後にMayaが終了する等
        # タイミングが悪いと、その記録のまま保存され、次回起動時に復元
        # されなくなる(再起動のたびに開かなくなる不具合の原因だった)。
        # 二重に開き直さず、状態の記録だけ行う。
        record()
        return
    if existing:
        # 保存済みworkspaceControlが空のまま残っている(hedit.mllのロード前はuiScriptの
        # import hedit が解決できず、Mayaが中身を作れなかった)。ここでhedit.show()により
        # 本体を差し込むと、表示した瞬間にMayaがuiScript(hedit.restore())で中身を作り直し、
        # 差し込んだ本体が破棄される。表示だけ行い、中身はMaya自身の復元経路に作らせる。
        from .docking import isValid
        from . import docking
        cmds.workspaceControl(CONTROL, edit=True, visible=True)
        if docking._host is not None and isValid(docking._host):
            record()
            return
    import hedit
    hedit.show(floating=None if existing else state.get('floating', True))
    if not existing and not state.get('floating', True):
        cmds.warning('hedit: saved workspace control is unavailable; docked at the bottom. Restore the saved Maya workspace for the original placement.')
    record()


def plugin_loaded():
    """initializePlugin(C++)がロード完了時に呼ぶ。前回画面の復元を次のidleへ送る。

    Windowメニューの登録自体はC++側(plugin.cppのinstallMenu、MEL経由)が別途行う。
    ここではPySide/MayaQWidgetDockableMixinが要るドッキング復元だけを担当する。
    userSetup.pyのような外部スクリプトを経由せず、プラグインがロードされた時点で
    この1系統だけが復元を行う。Plug-in Managerでの明示ロード・Mayaのプラグイン
    autoloadのいずれでも同じ経路になる。
    """
    if not cmds.about(batch=True):
        utils.executeDeferred(restore_previous)


def uninstall():
    """解除時にhedit専用のタイマー・終了通知を取り除く。Windowメニューの削除はC++側で行う。"""
    global _timer, _quit_job
    if not _quitting:
        closed()
    if _timer:
        _timer.stop()
        _timer.deleteLater()
        _timer = None
    if _quit_job is not None and cmds.scriptJob(exists=_quit_job):
        cmds.scriptJob(kill=_quit_job, force=True)
    _quit_job = None
)HEDIT_STARTUP";

/** @brief 旧パッケージ名``heditor``のuiScript互換入口。新規コードではhedit側を使う。 */
inline const char* kHeditorCompatSource = R"HEDIT_COMPAT(
"""旧ワークスペースのuiScript用互換入口。新規コードではheditを使う。"""

def restore():
    """保存済みの旧ドックを新しい実装で復元する。"""
    from maya import cmds
    import hedit
    from hedit import docking
    if cmds.workspaceControl('HEditorDockWorkspaceControl', exists=True):
        docking.CONTROL = 'HEditorDockWorkspaceControl'
    return hedit.restore()
)HEDIT_COMPAT";

/** @brief Python側へ渡す際の引用符・バックスラッシュ衝突を避けるためのhex変換。
 * @param text 変換対象(モジュールソース本体。トリプルクォートや改行を含み得る)。
 * @return 16進数文字列(0-9a-fのみ)。Python文字列リテラルへそのまま埋め込める。
 * @details ソース中の引用符・バックスラッシュ・改行を個別にエスケープする代わりに、
 * 常に安全な文字集合へ変換してからPython側でbinascii.unhexlifyへ戻す。
 */
inline std::string hexEncode(const char* text) {
    static const char* digits = "0123456789abcdef";
    std::string buffer;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
        buffer += digits[(*p) >> 4];
        buffer += digits[(*p) & 0x0F];
    }
    return buffer;
}

/** @brief 埋め込みPythonソースを配るimportフックをsys.meta_pathの先頭へ登録する。
 * @return 登録結果。失敗時は例外内容がScript Editorへ出力される。
 * @details ``import hedit``・``from . import docking``等は通常の.pyと同じくimport時に
 * 初めて実行される。先頭へ置くのは、PYTHONPATH上に同名のフォルダー(旧版の
 * ``__pycache__``だけが残った``scripts/hedit``等)があっても、名前空間パッケージとして
 * 先に解決されないようにするため。そうした埋め込み以外で読まれた同名モジュールは除く。
 * 再ロード時に埋め込み由来の読み込み済みモジュールは残す(旧版の.pyと同じく、ドックの
 * ホスト・タイマー等の状態をアンロード/ロードで失わない)。
 * ソース本体は引用符衝突を避けるためhexで渡す。
 * 一時関数は``__main__``(Script Editorの名前空間)へ名前を残さないよう実行後に削除する。
 */
inline MStatus installModules() {
    std::string script =
        "def __hedit_bootstrap(encoded):\n"
        "    import sys, binascii, importlib.abc, importlib.util\n"
        "    sources = {name: binascii.unhexlify(value).decode('utf-8') for name, value in encoded.items()}\n"
        "    class HeditEmbeddedImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):\n"
        "        def find_spec(self, fullname, path=None, target=None):\n"
        "            if fullname not in sources:\n"
        "                return None\n"
        "            return importlib.util.spec_from_loader(fullname, self, origin='hedit.mll', is_package=fullname == 'hedit')\n"
        "        def create_module(self, spec):\n"
        "            return None\n"
        "        def exec_module(self, module):\n"
        "            filename = '<hedit.mll>/' + module.__name__.replace('.', '/') + '.py'\n"
        "            exec(compile(sources[module.__name__], filename, 'exec'), module.__dict__)\n"
        "    sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__name__ != 'HeditEmbeddedImporter']\n"
        "    for name in [name for name in sys.modules if name in sources or name.startswith('hedit.')]:\n"
        "        if getattr(getattr(sys.modules[name], '__spec__', None), 'origin', None) != 'hedit.mll':\n"
        "            del sys.modules[name]\n"
        "    sys.meta_path.insert(0, HeditEmbeddedImporter())\n"
        "__hedit_bootstrap({\n";
    const std::pair<const char*, const char*> modules[] = {
        {"hedit", kInitSource}, {"hedit.completion", kCompletionSource}, {"hedit.bridge", kBridgeSource},
        {"hedit.docking", kDockingSource}, {"hedit.analysis", kAnalysisSource}, {"hedit.startup", kStartupSource},
        // 旧パッケージ名heditorのuiScript互換(保存済みワークスペースからのみ参照される)。
        {"heditor", kHeditorCompatSource},
    };
    for (const auto& module : modules)
        script += std::string("    '") + module.first + "': '" + hexEncode(module.second) + "',\n";
    script += "})\ndel __hedit_bootstrap\n";
    MString command; command.setUTF8(script.c_str());
    return MGlobal::executePythonCommand(command, false, false);
}

} // namespace embedded
} // namespace hedit
