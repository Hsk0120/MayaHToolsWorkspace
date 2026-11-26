"""同じ診断スクリプトを複数のMayaで起動する設定を読み取り専用で比較する。"""

import json
import os
from pathlib import Path
import subprocess

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
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
