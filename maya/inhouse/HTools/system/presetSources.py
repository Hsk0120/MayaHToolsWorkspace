"""個人・現在のプロジェクト・共通フォルダーにある同名プリセットを比較する。"""

import os
from pathlib import Path

import maya.cmds as cmds


def sources(relative):
    """指定した相対名の既存ファイルを、この検査での優先順に返す。"""
    name = Path(relative)
    if not relative.strip() or name.anchor or ".." in name.parts:
        raise ValueError("Enter a relative preset filename.")
    directories = [("Personal", Path(cmds.internalVar(userPrefDir=True)).parent / "presets"),
                   ("Project", Path(cmds.workspace(query=True, rootDirectory=True)) / "presets")]
    directories.extend(("Shared", Path(entry)) for entry in os.environ.get("MAYA_PRESET_PATH", "").split(os.pathsep) if entry)
    directories.append(("Installation", Path(os.environ["MAYA_LOCATION"]) / "presets"))
    rows = []
    seen = set()
    for scope, directory in directories:
        path = (directory / name).resolve()
        if path.is_file() and path not in seen:
            rows.append((scope, path))
            seen.add(path)
    return rows


def run():
    """現在のワークスペースでプリセットの候補ファイルと優先順位を表示する。"""
    window = "HToolsPresetSources"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect Preset Sources")
    cmds.columnLayout(adjustableColumn=True)
    name = cmds.textFieldGrp(label="Relative preset file")
    output = cmds.scrollField(editable=False, height=180)

    def refresh(*_):
        rows = sources(cmds.textFieldGrp(name, query=True, text=True))
        project = cmds.workspace(query=True, rootDirectory=True)
        lines = [f"Project: {project}", "Inspection order: personal, project, shared, installation"]
        lines.extend(f"{i}. {scope}: {path}" for i, (scope, path) in enumerate(rows, 1))
        if not rows:
            lines.append("No matching files.")
        cmds.scrollField(output, edit=True, text="\n".join(lines))

    cmds.button(label="Resolve in current project", command=refresh)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
