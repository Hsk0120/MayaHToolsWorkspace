"""一時コピー上で明示的なコマンド公開・追加漏れ検査・再読み込みを検証する。

Maya の Python 環境から、このファイルを独立したスクリプトとして実行する。
シーンおよび作業中の hlib ファイルは変更しない。
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run():
    """一時パッケージを別プロセスで読み込み、公開 API を検証する。"""
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="hlib_commands_") as directory:
        package = Path(directory) / "hlib"
        shutil.copytree(source, package, ignore=shutil.ignore_patterns(
            "_docs", "__tests__", "__pycache__"))
        script = r'''
import ast
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from check_hlib_exports import check
import maya.standalone
maya.standalone.initialize(name="python")
import hlib
from importlib import reload
from hlib._core import bootstrap
# Simulate a bootstrap module retained from the old release.
exec("def initialize_node_api(package_name, target_globals):\n    raise AssertionError('stale bootstrap')\ndef initialize_plug_api(package_name, target_globals):\n    raise AssertionError('stale bootstrap')", bootstrap.__dict__)
hlib.core = hlib._core
sys.modules["hlib.core"] = hlib._core
reload(hlib)
hlib.reload()
assert not hasattr(hlib, "core")
assert "hlib.core" not in sys.modules
assert callable(hlib.cmds.ls)
assert hlib.ls is hlib.cmds.ls
commands = Path(sys.argv[1]) / "hlib" / "cmds"
package = commands.parent
command_init = commands / "__init__.py"
root_init = package / "__init__.py"
original_cmds = command_init.read_text(encoding="utf-8")
original_root = root_init.read_text(encoding="utf-8")

def publish(path, statement, name):
    """一時コピーの通常importと明示__all__へ同じ公開名を追加する。"""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets))
    names = ast.literal_eval(node.value) + [name]
    lines = text.splitlines()
    end_line = getattr(node, "end_lineno", None) or node.value.elts[-1].lineno
    while "]" not in lines[end_line - 1]:
        end_line += 1
    lines[node.lineno - 1:end_line] = [statement, "__all__ = " + repr(names)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

# 旧版を読み込み済みのセッションから移行しても再公開名を残さない。
hlib.Node = hlib.nodes.Node
hlib.createNode = hlib.cmds.createNode
hlib.__all__ += ["Node", "createNode"]
hlib.reload()
assert not hasattr(hlib, "Node")
assert hlib.createNode is hlib.cmds.createNode
assert not hasattr(hlib, "NODE_REGISTRY")
assert hlib.nodes.Node._registry is not None
assert hlib.plugs.Plug._registry is not None
for name in ("ls", "createNode", "addConstraint"):
    assert callable(getattr(hlib.cmds, name))

path = commands / "exampleCommand.py"
path.write_text("def exampleCommand():\n    return 1\n", encoding="utf-8")
hlib.reload()
# 通常のimportは親パッケージに実装モジュールを置く場合がある。
# 公開関数と__all__への追加は、__init__.pyで明示するまで発生しない。
assert "exampleCommand" not in hlib.cmds.__all__
assert not callable(getattr(hlib.cmds, "exampleCommand", None))
assert not hasattr(hlib, "exampleCommand")
assert {"E015", "E016"}.issubset({issue.code for issue in check(package)})

publish(command_init, "from .exampleCommand import exampleCommand", "exampleCommand")
publish(root_init, "from .cmds import exampleCommand", "exampleCommand")
assert not check(package), check(package)
hlib.reload()
assert hlib.exampleCommand() == 1
assert hlib.exampleCommand is hlib.cmds.exampleCommand

path.write_text("def exampleCommand():\n    return 2026\n", encoding="utf-8")
hlib.reload()
assert hlib.exampleCommand() == 2026
assert hlib.exampleCommand is hlib.cmds.exampleCommand

path.write_text("def differentName():\n    return None\n", encoding="utf-8")
assert {"E009", "E014"}.issubset({issue.code for issue in check(package)})

path.write_text("def exampleCommand():\n    return 30000\n", encoding="utf-8")
hlib.reload()
assert hlib.cmds.exampleCommand() == 30000
command_init.write_text(original_cmds, encoding="utf-8")
root_init.write_text(original_root, encoding="utf-8")
path.unlink()
hlib.reload()
assert not hasattr(hlib.cmds, "exampleCommand")
assert not hasattr(hlib, "exampleCommand")
assert not check(package), check(package)

(commands / "_hidden.py").write_text("def _hidden():\n    return 1\n", encoding="utf-8")
(commands / "helper.py").write_text("from os import getcwd as helper\n", encoding="utf-8")
hlib.reload()
assert "_hidden" not in hlib.cmds.__all__
assert "helper" not in hlib.cmds.__all__
assert "E014" in {issue.code for issue in check(package)}
(commands / "helper.py").unlink()
(commands / "reload.py").write_text("def reload():\n    return 'command'\n", encoding="utf-8")
hlib.reload()
assert "reload" not in hlib.cmds.__all__
assert callable(hlib.reload)
assert "E015" in {issue.code for issue in check(package)}
publish(command_init, "from .reload import reload", "reload")
hlib.reload()
assert hlib.cmds.reload() == "command"
assert hlib.reload is not hlib.cmds.reload
assert callable(hlib.reload)
assert not check(package), check(package)
command_init.write_text(original_cmds, encoding="utf-8")
(commands / "reload.py").unlink()
hlib.reload()
print("PASS: explicit commands, omitted export detection, modification, removal, definition errors, root exports")
maya.standalone.uninitialize()
'''
        script_path = Path(directory) / "verify.py"
        script_path.write_text(script, encoding="utf-8")
        tools = Path(__file__).resolve().parents[4] / "tools"
        subprocess.run([sys.executable, str(script_path), directory, str(tools)], check=True, timeout=120)


if __name__ == "__main__":
    run()
