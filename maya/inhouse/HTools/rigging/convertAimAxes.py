"""選択したaimConstraintの1〜2軸変換を比較するMaya標準UI。"""

import math

import maya.cmds as cmds

import hlib
from hlib.json import JsonText
from hlib.utils import logger
from hrig.setups.aimAxisConversion import AimAxisConversion


_WINDOW = "HToolsConvertAimAxes"
_MODES = ("euler", "direction", "twist")
_HELP = (
    "1: Pick one equivalent XYZ solution by the reference angles and tolerance half-width, then output the chosen axes.\n"
    "   valid=0 means no candidate or two candidates. Use it where the range of motion gives a unique solution.\n"
    "2: Transform the aim direction by the full Aim rotation and recompute it as a 1-axis hinge or 2-axis angles.\n"
    "   The aim axis must not be a rotation axis. Two axes follow the Rotate Order; the first angle is within ±90°.\n"
    "   Computed with the other axes at 0. The direction may not match after fixed angles or pose offsets are added.\n"
    "3: Extract the twist of each chosen axis from the full rotation quaternion. Two axes are independent angles.\n"
    "   They are not the two swing components and may not match the original Euler values.\n\n"
    "Aim connections of unselected axes are removed and fixed at their current values. Other inputs are kept.\n"
    "Restore returns to the original Aim settings and direct connections and deletes all conversion nodes.\n"
    "The original Aim is kept and relayed. Connection cycles and World Up flips are not fixed.\n"
    "Methods 2 and 3 give 0 at singularities (the fixed offset when keeping the pose). ±180° wrapping and multiple turns are not supported.\n"
    "Convert again after changing the Rotate Order. Restore is refused after connections are edited by hand."
)


#: 入力欄の左のラベルの列の幅(英語のラベルが切れない幅)。
_LABEL_WIDTH = 240

class AimAxisConversionWindow:
    """1つのAimを登録し、設定変更・変換・復元・結果確認を行う画面。"""

    def __init__(self):
        """既存ウィンドウを置き換え、選択したAimを読み込む。"""
        self.constraint = None
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        self.window = cmds.window(_WINDOW, title="Compare 1-2 Axis Aim Conversions", widthHeight=(820, 780))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.button(label="Load Selected aimConstraint", command=self.loadSelection)
        self.source = cmds.text(label="Nothing loaded", align="left")
        self.mode = cmds.optionMenuGrp(label="Method", columnWidth=[(1, _LABEL_WIDTH)])
        for label in ("1  Equivalent Euler solution", "2  Hinge / 2-axis direction", "3  Per-axis twist"):
            cmds.menuItem(label=label)
        self.axes = cmds.optionMenuGrp(label="Output rotation axes", columnWidth=[(1, _LABEL_WIDTH)],
                                       changeCommand=self._syncDirection)
        for label in ("X", "Y", "Z", "XY", "XZ", "YZ"):
            cmds.menuItem(label=label)
        self.direction = cmds.optionMenuGrp(label="Method 2: local aim direction", columnWidth=[(1, _LABEL_WIDTH)])
        for label in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            cmds.menuItem(label=label)
        cmds.optionMenuGrp(self.direction, edit=True, value="Y")
        self.reference = cmds.floatFieldGrp(numberOfFields=3, label="Method 1: reference XYZ (deg)",
                                            columnWidth=[(1, _LABEL_WIDTH)],
                                            value1=0, value2=0, value3=0, precision=3)
        self.width = cmds.floatFieldGrp(numberOfFields=1, label="Method 1: tolerance half-width (deg)",
                                        columnWidth=[(1, _LABEL_WIDTH)], value1=85)
        self.preserve = cmds.checkBox(label="Methods 2 and 3: keep the current angles (add fixed offsets)", value=True)
        self.useContainer = cmds.checkBox(label="Put generated nodes in a container", value=True,
                                         annotation="When off, the math nodes connect directly and the restore data is stored on a network node.")
        cmds.button(label="Convert / Switch Method (one Undo reverts it)", command=self.convert)
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(label="Restore Original Aim and Settings", command=self.restore)
        cmds.button(label="Refresh Result", command=self.refresh)
        cmds.setParent("..")
        self.status = cmds.scrollField(editable=False, wordWrap=True, height=160, text="Not converted")
        cmds.scrollField(editable=False, wordWrap=True, height=300, text=_HELP)
        cmds.showWindow(self.window)
        self.loadSelection()

    def loadSelection(self, *_):
        """選択中の単一Aimを保持する。変換の管理ノードの選択も受け付ける。"""
        try:
            selected = hlib.ls(selection=True)
            if len(selected) != 1:
                raise ValueError("Select one aimConstraint node and load it.")
            node = selected[0]
            if node.type() in ("container", "network") and node.hasAttr("hrigAimAxisConversion"):
                link = node.plug("sourceConstraint").sourceWithConversion()
                node = link.node() if link is not None else node
            if node.type() != "aimConstraint":
                raise ValueError("Select the aimConstraint node, not the joint.")
            self.constraint = node
            cmds.text(self.source, edit=True, label=node.fullName())
            graph = AimAxisConversion.find(node)
            if graph is not None:
                data = JsonText.loads(graph.container.plug("settings").get())
                cmds.optionMenuGrp(self.mode, edit=True, select=(
                    _MODES.index(data["mode"]) + 1 if data["mode"] in _MODES else 1))
                if data["axes"] in ("x", "y", "z", "xy", "xz", "yz"):
                    cmds.optionMenuGrp(self.axes, edit=True, value=data["axes"].upper())
                cmds.optionMenuGrp(self.direction, edit=True, value=data["direction"].upper())
                angles = [math.degrees(a) for a in data["reference"]]
                cmds.floatFieldGrp(self.reference, edit=True, value1=angles[0], value2=angles[1], value3=angles[2])
                cmds.floatFieldGrp(self.width, edit=True, value1=math.degrees(data["halfRange"]))
                cmds.checkBox(self.preserve, edit=True, value=data["preservePose"])
                cmds.checkBox(self.useContainer, edit=True, value=data.get("useContainer", True))
            self.refresh()
        except (RuntimeError, ValueError, TypeError, AttributeError) as error:
            self.constraint = None
            cmds.text(self.source, edit=True, label="Nothing loaded")
            self._error(error)

    def convert(self, *_):
        """指定方式で接続を変換する。失敗は表示し、シーンはトランザクションで戻す。"""
        try:
            self._requireSource()
            values = cmds.floatFieldGrp(self.reference, query=True, value=True)
            AimAxisConversion.create(
                self.constraint,
                axes=cmds.optionMenuGrp(self.axes, query=True, value=True).lower(),
                mode=_MODES[cmds.optionMenuGrp(self.mode, query=True, select=True) - 1],
                direction=cmds.optionMenuGrp(self.direction, query=True, value=True).lower(),
                reference=tuple(math.radians(v) for v in values),
                half_range=math.radians(cmds.floatFieldGrp(self.width, query=True, value1=True)),
                preserve_pose=cmds.checkBox(self.preserve, query=True, value=True),
                use_container=cmds.checkBox(self.useContainer, query=True, value=True))
            self.refresh()
        except (RuntimeError, ValueError, TypeError) as error:
            self._error(error)

    def restore(self, *_):
        """変換ノードを除去し、元Aimの構造と設定値を復元する。"""
        try:
            self._requireSource()
            graph = AimAxisConversion.find(self.constraint)
            if graph is None:
                raise ValueError("This Aim has not been converted.")
            graph.restore()
            self.refresh()
        except (RuntimeError, ValueError, TypeError) as error:
            self._error(error)

    def refresh(self, *_):
        """元Aimと変換出力を度表示で比較し、現在フレームの診断を示す。"""
        try:
            self._requireSource()
            graph = AimAxisConversion.find(self.constraint)
            angles = [math.degrees(value) for value in self.constraint.getOutputRotation()]
            lines = ["Aim XYZ (deg): {:.3f}, {:.3f}, {:.3f}".format(*angles)]
            if graph is None:
                lines.append("Original Aim connections.")
            else:
                owner = graph.container
                data = JsonText.loads(owner.plug("settings").get())
                if data["mode"] == "rest":
                    lines.append("This is a corrected restore from an older version. Remove it with 'Restore Original Aim and Settings'.")
                converted = [math.degrees(owner.plug("output" + a).get()) for a in "XYZ"]
                lines.append("Output XYZ (deg): {:.3f}, {:.3f}, {:.3f}".format(*converted))
                lines.append("Owner node: " + owner.fullName())
                lines.append("Layout: " + ("container" if owner.type() == "container" else "direct connections (restore data on a network node)"))
                valid = owner.plug("valid").get() > 0.5
                lines.append("Diagnosis: " + ("valid" if valid else "check needed (ambiguous range, singularity or Rotate Order change)"))
            lines.append("Press 'Refresh Result' after moving the timeline or the targets.")
            cmds.scrollField(self.status, edit=True, text="\n".join(lines))
        except (RuntimeError, ValueError, TypeError) as error:
            self._error(error)

    def _requireSource(self):
        """保持しているAimの生存を確認する。"""
        if self.constraint is None or not self.constraint.isValid():
            raise ValueError("Load the selected aimConstraint first.")

    def _syncDirection(self, *_):
        """軸選択を変えた際、方式2で使える未選択軸を初期設定にする。"""
        axes = cmds.optionMenuGrp(self.axes, query=True, value=True)
        direction = cmds.optionMenuGrp(self.direction, query=True, value=True)
        if direction[-1] in axes:
            remaining = next(a for a in "XYZ" if a not in axes)
            cmds.optionMenuGrp(self.direction, edit=True, value=remaining)

    def _error(self, error):
        """エラーを画面と共通通知へ表示する。"""
        cmds.scrollField(self.status, edit=True, text=str(error))
        logger.warning(str(error))


def run():
    """変換比較ウィンドウを表示する。

    Returns:
        AimAxisConversionWindow: 表示した画面。
    """
    return AimAxisConversionWindow()


if __name__ == "__main__":
    run()
