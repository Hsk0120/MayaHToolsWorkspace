"""Mayaメインスレッド専用。補完のためのeval/importは行わない。"""
import json
import os
import sys
import types
from pathlib import Path



def configuration():
    """有効な検索パスとロード済みモジュールの実在する名前を渡す。"""
    modules = {}
    for name, module in list(sys.modules.items()):
        if not isinstance(module, types.ModuleType):
            continue
        members = {}
        for key, value in list(vars(module).items()):
            if key.startswith("_"):
                continue
            target = value.__name__ if isinstance(value, types.ModuleType) else ""
            members[key] = {"target": target}
        modules[name] = members
    return json.dumps({
        "python": str(Path(os.environ["MAYA_LOCATION"]) / "bin" / "mayapy.exe"),
        "worker": str(Path(__file__).with_name("worker.py")),
        "paths": [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)],
        "modules": modules,
    }, ensure_ascii=True)

