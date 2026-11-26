"""回転の合成に影響する入力を読み取り表示する。"""

from maya import cmds


def show():
    """選択したトランスフォームの回転設定と接続元を表示する。"""
    window = "mlrigRotationInspector"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="回転合成の入力")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.scrollField(editable=False, wordWrap=False, height=260)

    def refresh(*_):
        """値はシーンの角度単位で表示する。"""
        lines = []
        for node in cmds.ls(selection=True, long=True, transforms=True) or []:
            lines.append(node)
            for attr in ("rotateOrder", "rotate", "rotateAxis", "jointOrient"):
                plug = node + "." + attr
                if not cmds.objExists(plug):
                    continue
                value = cmds.getAttr(plug, asString=True) if attr == "rotateOrder" else cmds.getAttr(plug)[0]
                lines.append("  {} = {}".format(attr, value))
                children = cmds.attributeQuery(attr, node=node, listChildren=True) or []
                for name in [attr] + children:
                    source = cmds.connectionInfo(node + "." + name, sourceFromDestination=True)
                    if source:
                        lines.append("    {} ← {}".format(name, source))
        cmds.scrollField(field, edit=True, text="\n".join(lines))

    cmds.button(label="現在の選択で更新", command=refresh)
    refresh()
    cmds.showWindow(window)
    return window
