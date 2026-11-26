"""保存・再読込前後のスクリプトノードを同じシーンで比較する。"""

import hashlib

import maya.cmds as cmds


def capture():
    """スクリプト本文を実行せず名前・UUID・設定と本文の指紋を記録する。"""
    nodes = {}
    for name in cmds.ls(type="script") or []:
        attributes = ("scriptType", "sourceType", "before", "after")
        values = tuple(cmds.getAttr(name + "." + attr) for attr in attributes)
        digest = hashlib.sha256(repr(values).encode("utf-8")).hexdigest()
        nodes[name] = (cmds.ls(name, uuid=True)[0], digest)
    return nodes


def compare(before, after):
    """追加・消失・同名の再作成・内容の変更を一覧にする。"""
    rows = []
    for name in sorted(before.keys() | after.keys()):
        if name not in before:
            state = "Added"
        elif name not in after:
            state = "Removed"
        elif before[name][0] != after[name][0]:
            state = "Recreated"
        elif before[name][1] != after[name][1]:
            state = "Modified"
        else:
            continue
        category = "Maya configuration name" if name in ("uiConfigurationScriptNode", "sceneConfigurationScriptNode") else "Other script"
        rows.append((name, state, category))
    return rows


def run():
    """比較元を記憶し、利用者が再読込した後に差分を表示する。"""
    window = "HToolsScriptNodeAudit"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Script Node Reload Audit")
    cmds.columnLayout(adjustableColumn=True)
    baseline = capture()
    scene = cmds.file(query=True, sceneName=True)
    cmds.text(label="Captured scene: " + (scene or "(untitled)"))
    report = cmds.scrollField(editable=False, height=180)

    def refresh(*_):
        if cmds.file(query=True, sceneName=True) != scene:
            text = "Reopen the captured scene to compare."
        else:
            rows = compare(baseline, capture())
            text = "\n".join("  |  ".join(row) for row in rows) or "No script node differences."
        cmds.scrollField(report, edit=True, text=text)

    cmds.button(label="Compare with captured state", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
