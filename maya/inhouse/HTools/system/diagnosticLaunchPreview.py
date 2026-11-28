"""同じ診断スクリプトを複数のMayaで起動する設定を読み取り専用で比較する。"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import maya.cmds as cmds


def commands(install_root, script, project, output):
    """Maya版ごとの実行ファイル、プロジェクト、診断スクリプト、ログを組み立てる。"""
    script, project, output = (Path(value).resolve() for value in (script, project, output))
    if script.suffix.lower() != ".py" or not script.is_file() or not project.is_dir():
        raise ValueError("Choose an existing Python diagnostic and project directory.")
    code = f"import runpy; runpy.run_path({str(script)!r}, run_name='__main__')"
    command = "python(" + json.dumps(code, ensure_ascii=False) + ")"
    result = []
    for folder in sorted(Path(install_root).glob("Maya[0-9][0-9][0-9][0-9]")):
        executable = folder / "bin" / "maya.exe"
        if executable.is_file():
            result.append((folder.name, [str(executable), "-proj", str(project), "-log",
                                         str(output / (folder.name + ".log")), "-command", command]))
    return result


def saveLaunch(directory, name, install_root, script, project, output):
    """起動せずに診断条件を時刻付きの独立した履歴ファイルに記録する。"""
    if not name.strip():
        raise ValueError("Enter a history label.")
    rows = commands(install_root, script, project, output)
    if not rows:
        raise ValueError("No Maya installations found.")
    data = dict(label=name.strip(), saved=datetime.now(timezone.utc).isoformat(),
                settings={k: str(Path(v).resolve()) for k, v in
                          zip(("installRoot", "script", "project", "logs"), (install_root, script, project, output))},
                commands=dict(rows))
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (uuid4().hex + ".json")
    temporary = target.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def compareLaunch(first, second):
    """二つの保存履歴の版別コマンドと基準フォルダーの違いを表示する。"""
    a, b = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (first, second)]
    result = [a["label"] + " -> " + b["label"]]
    for group in ("settings", "commands"):
        for key in sorted(set(a[group]) | set(b[group])):
            values = [item[group].get(key, "<missing>") for item in (a, b)]
            if values[0] != values[1]:
                result.append(key + "\n" + "\n".join(subprocess.list2cmdline(v) if isinstance(v, list) else v for v in values))
    return result if len(result) > 1 else result + ["Identical launch conditions."]


def run():
    """既存のインストールを探し、起動時の引数を比較画面に表示する。"""
    window = "HToolsDiagnosticLaunchPreview"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Compare Maya Diagnostic Launch Settings")
    cmds.columnLayout(adjustableColumn=True)
    root = cmds.textFieldGrp(label="Install root", text=str(Path(os.environ["MAYA_LOCATION"]).parent))
    script = cmds.textFieldGrp(label="Diagnostic Python file")
    project = cmds.textFieldGrp(label="Project", text=cmds.workspace(query=True, rootDirectory=True))
    output = cmds.textFieldGrp(label="Log directory", text=str(Path(cmds.internalVar(userTmpDir=True))))
    report = cmds.scrollField(editable=False, height=220, wordWrap=True)

    def inspect(*_):
        fields = [cmds.textFieldGrp(control, query=True, text=True) for control in (root, script, project, output)]
        rows = commands(*fields)
        text = "\n\n".join(name + "\n" + subprocess.list2cmdline(argv) for name, argv in rows)
        cmds.scrollField(report, edit=True, text=text or "No Maya installations found.")

    cmds.button(label="Compare launch settings", command=inspect)
    folder = Path(cmds.internalVar(userPrefDir=True)) / "HToolsDiagnosticHistory"
    label = cmds.textFieldGrp(label="History label")
    history = cmds.textScrollList(allowMultiSelection=True, height=110)
    paths = []

    def refresh():
        paths[:] = sorted(folder.glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name))
        cmds.textScrollList(history, edit=True, removeAll=True)
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            cmds.textScrollList(history, edit=True, append=data["saved"] + "  " + data["label"])

    def save(*_):
        saveLaunch(folder, cmds.textFieldGrp(label, query=True, text=True),
                   *(cmds.textFieldGrp(c, query=True, text=True) for c in (root, script, project, output)))
        refresh()

    def view(compare):
        picks = cmds.textScrollList(history, query=True, selectIndexedItem=True) or []
        if len(picks) != (2 if compare else 1):
            raise ValueError("Choose two records to compare or one to restore.")
        selected = [paths[i - 1] for i in picks]
        if compare:
            lines = compareLaunch(*selected)
        else:
            data = json.loads(selected[0].read_text(encoding="utf-8"))
            lines = []
            for control, key in zip((root, script, project, output), ("installRoot", "script", "project", "logs")):
                value = data["settings"][key]
                cmds.textFieldGrp(control, edit=True, text=value)
                lines.append(f"{key}: {value}" + ("" if Path(value).exists() else " (missing)"))
            lines.extend(subprocess.list2cmdline(argv) for argv in data["commands"].values())
        cmds.scrollField(report, edit=True, text="\n".join(lines))

    cmds.button(label="Save current preview to history", command=save)
    cmds.button(label="Restore selected history to preview", command=lambda *_: view(False))
    cmds.button(label="Compare two saved records", command=lambda *_: view(True))
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
