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

/** @brief hedit.__init__ 相当。PythonからC++のheditコマンドを呼ぶ互換用の窓口。
 * @details ドッキング・開閉状態の保存と復元はdock.cpp(C++)が行う。ここはPythonの
 * スクリプトや、旧版で保存されたworkspaceControlのuiScript(``import hedit; hedit.restore()``)の入口。
 */
inline const char* kInitSource = R"HEDIT_INIT(
__version__ = '0.2.10'


def _load():
    from maya import cmds
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('hedit')
    return cmds


def show(floating=None):
    """編集画面を開く(MELの hedit -show と同じ)。

    Args:
        floating (bool | None): 指定時だけフローティング状態を変更する。
    """
    cmds = _load()
    if floating is None:
        cmds.hedit(show=True)
    else:
        cmds.hedit(show=True, floating=bool(floating))


def restore():
    """旧版で保存されたworkspaceControlのuiScriptから呼ばれる(MELの hedit -restore と同じ)。"""
    _load().hedit(restore=True)
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


class Index:
    """モジュールの中身・ローカルの宣言の補完。

    ``import xxx`` / ``from xxx`` のトップレベル名(sys.pathのフォルダー走査)はC++
    (modulescan.cpp)が扱う。ここでの ``import`` の補完は組み込み・読み込み済みの名前だけ。
    """
    def __init__(self, paths, modules=None, runtime=None):
        self.paths = paths
        self.modules = modules or {}
        self.cache = {}
        self.runtime = runtime
        self.top = set(sys.builtin_module_names)
        self.top.update(name.split('.')[0] for name in self.modules)
        self.local_source = None
        self.local_symbols = {}

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

/** @brief hedit.bridge 相当。補完の橋渡しと、C++が決めるタブ復元先の参照。
 * @details 出力履歴の取得・整形、出力用reporterの作成/破棄、復元先の決定はplugin.cppへ移した。
 */
inline const char* kBridgeSource = R"HEDIT_BRIDGE(
"""Mayaメインスレッド専用。補完のためのeval/importは行わない。"""
import json
import os
import sys
import types
from .completion import Index

_index = None


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
    _index = Index(data["paths"], modules=modules, runtime=runtime_module)
    return json.dumps({'ready': True})


def module_names():
    """str: C++のimport補完へ渡す検索パスと、組み込み・読み込み済みのトップレベル名(JSON)。

    sys.pathのフォルダー走査はC++(modulescan.cpp)がGILを取らないスレッドで行う。
    """
    paths = [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)]
    names = set(sys.builtin_module_names)
    names.update(name.split('.')[0] for name in list(sys.modules))
    return json.dumps({'paths': paths, 'names': sorted(names)}, ensure_ascii=True)



def complete(source):
    """Mayaの同一プロセス内で候補を返す。補完対象はimportしない。"""
    try:
        if _index is None:
            configuration()
        if _index.runtime:
            _index.paths = [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)]
            _index.modules = {name: {} for name in sys.modules}
        items = _index.complete(source)
        return json.dumps({'items': items, 'pending': False}, ensure_ascii=True)
    except Exception as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=True)
)HEDIT_BRIDGE";

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

/** @brief 旧パッケージ名``heditor``のuiScript互換入口。新規コードではhedit側を使う。 */
inline const char* kHeditorCompatSource = R"HEDIT_COMPAT(
"""旧ワークスペースのuiScript用互換入口。新規コードではheditを使う。"""

def restore():
    """保存済みの旧ドックを新しい実装で復元する。旧名のドックの引き継ぎはC++(dock.cpp)が行う。"""
    import hedit
    hedit.restore()
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
 * @details ``import hedit``・``from .completion import Index``等は通常の.pyと同じくimport時に
 * 初めて実行される。先頭へ置くのは、PYTHONPATH上に同名のフォルダー(旧版の
 * ``__pycache__``だけが残った``scripts/hedit``等)があっても、名前空間パッケージとして
 * 先に解決されないようにするため。そうした埋め込み以外で読まれた同名モジュールは除く。
 * 再ロード時に埋め込み由来の読み込み済みモジュールは残す(旧版の.pyと同じく、補完の
 * キャッシュ等の状態をアンロード/ロードで失わない)。
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
        {"hedit.analysis", kAnalysisSource},
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
