"""二つの案件のMayaファイル規則とJSON設定を読み取り、差分を表示する。"""

import json
from pathlib import Path
import re

import maya.cmds as cmds


def _settings(filename):
    """MayaプロジェクトまたはJSONファイルから比較値を取得する。"""
    path = Path(filename).expanduser().resolve()
    if path.is_dir():
        path = path / "workspace.mel"
    if not path.is_file():
        raise ValueError("Project settings file not found: " + str(path))
    contents = path.read_text(encoding="utf-8-sig")
    if path.name.lower() == "workspace.mel":
        # シェルやMELを実行せず標準のworkspace -fr宣言だけを読む。
        expr = r'(?m)^\s*workspace\s+-(?:fr|fileRule)\s+"((?:\\.|[^"\\])*)"\s+"((?:\\.|[^"\\])*)"\s*;'
        result = {"fileRule/" + name: value for name, value in re.findall(expr, contents)}
        if not result:
            raise ValueError("No literal Maya file rules found in " + str(path))
        return path, result
    if path.suffix.lower() != ".json":
        raise ValueError("Choose a project JSON file or workspace.mel.")
    settings = json.loads(contents)
    if not isinstance(settings, dict):
        raise ValueError("Project JSON must contain an object.")
    rows = {}

    def collect(prefix, value):
        if isinstance(value, dict) and value:
            for key, child in value.items():
                collect(prefix + "/" + key.replace("~", "~0").replace("/", "~1"), child)
        else:
            rows[prefix] = json.dumps(value, ensure_ascii=False, sort_keys=True)

    collect("", settings)
    return path, rows


def compare(first, second):
    """設定元のファイル名と、値・登録有無が異なるキーを返す。"""
    left_path, left = _settings(first)
    right_path, right = _settings(second)
    if left_path.suffix.lower() != right_path.suffix.lower():
        raise ValueError("Choose two projects with the same settings format.")
    missing = "<missing>"
    rows = [(key, left.get(key, missing), right.get(key, missing)) for key in sorted(set(left) | set(right))
            if key not in left or key not in right or left[key] != right[key]]
    return left_path, right_path, rows


def run():
    """案件設定の値と欠落をファイル別に表示する。"""
    window = "HToolsCompareProjectSettings"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Compare Project Settings")
    cmds.columnLayout(adjustableColumn=True)

    def field(label):
        def browse(*_):
            files = cmds.fileDialog2(fileMode=1, fileFilter="Project settings (workspace.mel *.json)")
            if files:
                cmds.textFieldButtonGrp(control, edit=True, text=files[0])
        control = cmds.textFieldButtonGrp(label=label, buttonLabel="Browse", buttonCommand=browse)
        return control

    first, second = field("Project A"), field("Project B")
    report = cmds.scrollField(editable=False, height=220)

    def inspect(*_):
        a, b, rows = compare(*(cmds.textFieldButtonGrp(f, query=True, text=True) for f in (first, second)))
        lines = [f"A: {a}", f"B: {b}"] + [f"{key}   A: {before}   B: {after}" for key, before, after in rows]
        cmds.scrollField(report, edit=True, text="\n".join(lines if rows else lines + ["No differing settings."]))

    cmds.button(label="Compare settings", command=inspect)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
