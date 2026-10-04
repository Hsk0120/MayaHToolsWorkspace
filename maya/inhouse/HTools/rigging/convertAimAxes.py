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
    "1: XYZ一組の等価解を基準角・許容半幅で選び、その後に指定軸を出力。\n"
    "   valid=0は候補なし／両方候補。範囲内が一意に決まる可動域で使います。\n"
    "2: Aimの全回転で『狙う方向』を変換し、1軸ヒンジ／2軸角として再計算。\n"
    "   狙う軸は回転軸以外。2軸の適用順はRotate Order、先に適用する角は±90°。\n"
    "   他軸0を基準に計算。他軸の固定角や姿勢維持の加算後は方向一致を保証しません。\n"
    "3: 全回転のQuaternionから選択軸ごとのTwistを抽出。2軸は独立した角度です。\n"
    "   Swingの2成分ではなく、元のEuler値とも一致するとは限りません。\n\n"
    "未選択軸のAim接続は外して現在値へ固定。他の入力は維持します。\n"
    "復元は元Aimの設定と直接接続へ戻し、変換・補正ノードを全て削除します。\n"
    "元Aimを残した中継変換です。接続サイクルやWorld Upの反転は修復しません。\n"
    "2・3は特異点で0角（姿勢維持時は固定加算値）。±180°のwrap／多回転は未対応。\n"
    "Rotate Order変更後は再変換してください。接続の手編集後は復元を拒否します。"
)


class AimAxisConversionWindow:
    """1つのAimを登録し、設定変更・変換・復元・結果確認を行う画面。"""

    def __init__(self):
        """既存ウィンドウを置き換え、選択したAimを読み込む。"""
        self.constraint = None
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        self.window = cmds.window(_WINDOW, title="Aimの1〜2軸変換を比較", widthHeight=(820, 780))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.button(label="選択したaimConstraintを読み込む", command=self.loadSelection)
        self.source = cmds.text(label="未選択", align="left")
        self.mode = cmds.optionMenuGrp(label="変換方式")
        for label in ("1  Eulerの等価解を選択", "2  ヒンジ／2軸方向", "3  軸別Twist抽出"):
            cmds.menuItem(label=label)
        self.axes = cmds.optionMenuGrp(label="出力する回転軸", changeCommand=self._syncDirection)
        for label in ("X", "Y", "Z", "XY", "XZ", "YZ"):
            cmds.menuItem(label=label)
        self.direction = cmds.optionMenuGrp(label="方式2: 狙うローカル方向")
        for label in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            cmds.menuItem(label=label)
        cmds.optionMenuGrp(self.direction, edit=True, value="Y")
        self.reference = cmds.floatFieldGrp(numberOfFields=3, label="方式1: 基準XYZ（度）",
                                            value1=0, value2=0, value3=0, precision=3)
        self.width = cmds.floatFieldGrp(numberOfFields=1, label="方式1: 許容半幅（度）", value1=85)
        self.preserve = cmds.checkBox(label="方式2・3: 変換時の角度を維持（固定角を加算）", value=True)
        self.useContainer = cmds.checkBox(label="生成ノードをコンテナ化する", value=True,
                                         annotation="オフでは演算ノードから直接接続し、networkノードに復元情報を保存します。")
        cmds.button(label="変換／方式を切替（1回のUndoで戻せます）", command=self.convert)
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(label="元のAim構造・設定へ戻す", command=self.restore)
        cmds.button(label="結果を再確認", command=self.refresh)
        cmds.setParent("..")
        self.status = cmds.scrollField(editable=False, wordWrap=True, height=160, text="未変換")
        cmds.scrollField(editable=False, wordWrap=True, height=300, text=_HELP)
        cmds.showWindow(self.window)
        self.loadSelection()

    def loadSelection(self, *_):
        """選択中の単一Aimを保持する。変換の管理ノードの選択も受け付ける。"""
        try:
            selected = hlib.ls(selection=True)
            if len(selected) != 1:
                raise ValueError("aimConstraintノードを1つ選択して読み込んでください。")
            node = selected[0]
            if node.type() in ("container", "network") and node.hasAttribute("hrigAimAxisConversion"):
                link = node.plug("sourceConstraint").source()
                node = link.node if link is not None else node
            if node.type() != "aimConstraint":
                raise ValueError("ジョイントではなくaimConstraintノードを選択してください。")
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
            cmds.text(self.source, edit=True, label="未選択")
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
                raise ValueError("このAimは変換されていません。")
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
            lines = ["Aim XYZ（度）: {:.3f}, {:.3f}, {:.3f}".format(*angles)]
            if graph is None:
                lines.append("元のAim接続です。")
            else:
                owner = graph.container
                data = JsonText.loads(owner.plug("settings").get())
                if data["mode"] == "rest":
                    lines.append("旧版の補正付き復元です。『元のAim構造・設定へ戻す』で除去できます。")
                converted = [math.degrees(owner.plug("output" + a).get()) for a in "XYZ"]
                lines.append("出力 XYZ（度）: {:.3f}, {:.3f}, {:.3f}".format(*converted))
                lines.append("所有ノード: " + owner.fullName())
                lines.append("構成: " + ("コンテナ" if owner.type() == "container" else "直接接続（networkに復元情報）"))
                valid = owner.plug("valid").get() > 0.5
                lines.append("診断: " + ("有効" if valid else "要確認（範囲の曖昧さ・特異点・Rotate Order変更）"))
            lines.append("タイムラインやターゲットを動かした後は『結果を再確認』を押してください。")
            cmds.scrollField(self.status, edit=True, text="\n".join(lines))
        except (RuntimeError, ValueError, TypeError) as error:
            self._error(error)

    def _requireSource(self):
        """保持しているAimの生存を確認する。"""
        if self.constraint is None or not self.constraint.isValid():
            raise ValueError("選択したaimConstraintを読み込んでください。")

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
