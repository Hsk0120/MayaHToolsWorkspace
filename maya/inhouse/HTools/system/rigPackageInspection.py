"""リグアセットの公開ポート・シーン単位・依存と参照元を読み取りで確認する。"""

from pathlib import Path

import maya.cmds as cmds

from HTools.system.pluginDependencies import dependencies, savedRequirements


def inspect(root):
    """選択ルートの定義と現在のシーン全体の依存情報をまとめる。"""
    from mlrig.publishedChannels import getPorts, resolveChannels

    ports = getPorts(root)
    resolved, missing = resolveChannels(root, {role: (port["path"], port["attribute"]) for role, port in ports.items()})
    rows = [f"Rig: {root}", "Time unit: " + cmds.currentUnit(query=True, time=True),
            "Maya version: " + cmds.about(version=True)]
    version_attr = root + ".version"
    rows.append("Asset version: " + (str(cmds.getAttr(version_attr)) if cmds.objExists(version_attr) else "Not declared"))
    rows.append("Published ports:")
    rows.extend(f"  {role}: {plug}" for role, plug in sorted(resolved.items()))
    rows.extend(f"  {role}: Missing target" for role in sorted(missing))
    rows.append("Scene references:")
    for ref in cmds.ls(type="reference") or []:
        if ref == "sharedReferenceNode":
            continue
        try:
            path = cmds.referenceQuery(ref, filename=True, withoutCopyNumber=True)
        except RuntimeError:
            rows.append("  Unresolved: " + ref)
            continue
        state = "loaded" if cmds.referenceQuery(ref, isLoaded=True) else "unloaded"
        rows.append(f"  {ref}: {path} ({state}, {'present' if Path(path).is_file() else 'missing'})")
    rows.append("Plug-ins used by scene nodes:")
    rows.extend("  " + owner for owner in sorted({owner for owner, _, _ in dependencies()}))
    rows.extend(["Saved file requires:", savedRequirements()])
    return rows


def run():
    """リグルートを選択してアセット検査結果を表示する。"""
    window = "HToolsRigPackageInspection"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect Rig Package")
    cmds.columnLayout(adjustableColumn=True)
    report = cmds.scrollField(editable=False, height=240)

    def refresh(*_):
        roots = cmds.ls(selection=True, long=True, transforms=True) or []
        rows = inspect(roots[0]) if len(roots) == 1 else ["Select one rig root."]
        cmds.scrollField(report, edit=True, text="\n".join(rows))

    cmds.button(label="Inspect selected rig and scene dependencies", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
