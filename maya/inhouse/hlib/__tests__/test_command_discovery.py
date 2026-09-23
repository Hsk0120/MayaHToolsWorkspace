"""一時コピー上でコマンドの追加・変更・削除と再読み込みを検証する。

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
            "docs", "__tests__", "__pycache__"))
        script = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
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
for name in ("ls", "createNode", "constraint"):
    assert callable(getattr(hlib.cmds, name))

path = commands / "example_command.py"
path.write_text("def example_command():\n    return 1\n", encoding="utf-8")
hlib.reload()
assert hlib.example_command() == 1
assert hlib.example_command is hlib.cmds.example_command

path.write_text("def example_command():\n    return 2026\n", encoding="utf-8")
hlib.reload()
assert hlib.example_command() == 2026
assert hlib.example_command is hlib.cmds.example_command

path.write_text("def different_name():\n    return None\n", encoding="utf-8")
hlib.reload()
assert not hasattr(hlib.cmds, "example_command")
assert not hasattr(hlib, "example_command")

path.write_text("def example_command():\n    return 30000\n", encoding="utf-8")
hlib.reload()
assert hlib.cmds.example_command() == 30000
path.unlink()
hlib.reload()
assert not hasattr(hlib.cmds, "example_command")
assert not hasattr(hlib, "example_command")

(commands / "_hidden.py").write_text("def _hidden():\n    return 1\n", encoding="utf-8")
(commands / "helper.py").write_text("from os import getcwd as helper\n", encoding="utf-8")
hlib.reload()
assert "_hidden" not in hlib.cmds.__all__
assert "helper" not in hlib.cmds.__all__
assert hlib.cmds.__all__ == sorted(hlib.cmds.__all__)
(commands / "reload.py").write_text("def reload():\n    return 'command'\n", encoding="utf-8")
hlib.reload()
assert hlib.cmds.reload() == 'command'
assert hlib.reload is not hlib.cmds.reload
hlib.reload()
print("PASS: existing commands, addition, modification, removal, missing function, exclusions, root exports")
'''
        script_path = Path(directory) / "verify.py"
        script_path.write_text(script, encoding="utf-8")
        subprocess.run([sys.executable, str(script_path), directory], check=True)


if __name__ == "__main__":
    run()
