"""リグアセットの公開ポート・シーン単位・依存と参照元を読み取りで確認する。"""

from pathlib import Path

import maya.cmds as cmds

from mlib.decorator import undoTransaction

from HTools.system.pluginDependencies import dependencies, savedRequirements


def displayInfo(root):
    """ローカルのリグルートに保存した表示ラベルと版を取得する。"""
    if not cmds.objExists(root + ".mlrigDefinition"):
        raise ValueError("Choose a rig root containing mlrigDefinition.")
    result = []
    for attr in ("htAssetLabel", "htAssetVersion"):
        plug = root + "." + attr
        if cmds.objExists(plug) and cmds.getAttr(plug, type=True) != "string":
            raise ValueError("Unexpected metadata type: " + plug)
        result.append((cmds.getAttr(plug) or "") if cmds.objExists(plug) else "")
    return tuple(result)


@undoTransaction("Update Rig Display Information")
def updateInfo(root, label, version):
    """シーン保存の対象となるリグの表示情報だけを更新する。"""
    displayInfo(root)
    if not label.strip() or not version.strip():
        raise ValueError("Enter a label and version.")
    if cmds.referenceQuery(root, isNodeReferenced=True) or cmds.lockNode(root, query=True, lock=True)[0]:
        raise ValueError("Choose an editable local rig root.")
    for attr in ("htAssetLabel", "htAssetVersion"):
        plug = root + "." + attr
        if cmds.objExists(plug) and (not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True)):
            raise ValueError("Metadata is locked or driven: " + plug)
    for attr, value in (("htAssetLabel", label), ("htAssetVersion", version)):
        plug = root + "." + attr
        if not cmds.objExists(plug):
            cmds.addAttr(root, longName=attr, dataType="string")
        cmds.setAttr(plug, value, type="string")
    return displayInfo(root)


def inspect(root):
    """選択ルートの定義と現在のシーン全体の依存情報をまとめる。"""
    from mlrig.publishedChannels import getPorts, resolveChannels

    ports = getPorts(root)
    resolved, missing = resolveChannels(root, {role: (port["path"], port["attribute"]) for role, port in ports.items()})
    rows = [f"Rig: {root}", "Time unit: " + cmds.currentUnit(query=True, time=True),
            "Maya version: " + cmds.about(version=True)]
    version_attr = root + ".version"
    rows.append("Asset version: " + (str(cmds.getAttr(version_attr)) if cmds.objExists(version_attr) else "Not declared"))
    if cmds.objExists(root + ".mlrigDefinition"):
        label, display_version = displayInfo(root)
        rows.extend(["Display label: " + label, "Display version: " + display_version])
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
    label = cmds.textFieldGrp(label="Display label")
    version = cmds.textFieldGrp(label="Display version")

    def metadata(save):
        roots = cmds.ls(selection=True, long=True, transforms=True) or []
        if len(roots) != 1:
            raise ValueError("Select one rig root.")
        if save:
            updateInfo(roots[0], cmds.textFieldGrp(label, query=True, text=True),
                       cmds.textFieldGrp(version, query=True, text=True))
        for control, value in zip((label, version), displayInfo(roots[0])):
            cmds.textFieldGrp(control, edit=True, text=value)
        refresh()

    cmds.button(label="Read selected rig display information", command=lambda *_: metadata(False))
    cmds.button(label="Update selected rig display information", command=lambda *_: metadata(True))
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
