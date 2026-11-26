"""シーン内のモジュール型を共通のUIから解決する。"""

import json

from maya import cmds

import mlib


class ModuleRegistry:
    """保存済みの識別属性からモジュールを取得する。"""

    @staticmethod
    def showInspector():
        """選択項目の最も近いモジュールと定義上のレイヤー依存を表示する。"""
        window = "mlrigUnitInspector"
        if cmds.window(window, exists=True):
            cmds.deleteUI(window)
        cmds.window(window, title="ユニット探索")
        cmds.columnLayout(adjustableColumn=True)
        output = cmds.scrollField(editable=False, wordWrap=False, height=230)

        def refresh(*_):
            """現在の選択と親階層から表示を更新する。"""
            lines = []
            for item in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
                root = item
                while root.startswith("|"):
                    if any(cmds.objExists(root + "." + marker) for marker in ModuleRegistry.MARKERS):
                        break
                    root = root.rpartition("|")[0]
                else:
                    lines.append(item + "  (所属ユニットなし)")
                    continue
                lines.append(item + " → " + root)
                if cmds.objExists(root + ".mlrigDefinition"):
                    from .definition import RigDefinition

                    definition = RigDefinition.from_data(json.loads(cmds.getAttr(root + ".mlrigDefinition")))
                    for layer in definition.layers:
                        lines.append("  {}  依存: {}".format(layer.id, ", ".join(layer.dependencies) or "なし"))
            cmds.scrollField(output, edit=True, text="\n".join(lines))

        cmds.button(label="現在の選択で更新", command=refresh)
        cmds.scriptJob(event=["SelectionChanged", refresh], parent=window)
        refresh()
        cmds.showWindow(window)
        return window

    MARKERS = ("mlrigDefinition", "mlrigSkirtDefinition", "mlrigSplineDefinition", "mlrigControlDefinition")

    @staticmethod
    def get(root):
        """ルートに対応する操作オブジェクトを取得する。

        Args:
            root (str | Node): モジュールルート。

        Returns:
            LimbRig | SkirtRig | SplineRig: 保存されたモジュール。
        """
        from .limb import LimbRig
        from .skirtRig import SkirtRig
        from .splineRig import SplineRig

        node = mlib.Node(root)
        if node.hasAttr("mlrigControlDefinition"):
            from .controlRig import ControlRig
            from .fingerRig import FingerRig
            from .aimRig import AimRig

            return FingerRig(node) if ControlRig(node).kind() == "finger" else AimRig(node)
        if node.hasAttr("mlrigSplineDefinition"):
            return SplineRig(node)
        return SkirtRig(node) if node.hasAttr("mlrigSkirtDefinition") else LimbRig(node)

    @staticmethod
    def roots():
        """登録済みモジュールのルートを列挙する。

        Returns:
            list[str]: モジュールルート。
        """
        return [
            attr.rsplit(".", 1)[0]
            for marker in ModuleRegistry.MARKERS
            for attr in (
                [item.getName(full=True) for item in mlib.ls("*." + marker, recursive=True)] or []
            )
        ]
