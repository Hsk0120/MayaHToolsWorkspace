"""2つのジョイントの間に、ツイスト用のジョイントを均等な間隔で作るツール。

根本(Root)と末端(End)のジョイントを指定し、その間を ``個数 + 1`` 等分した位置へジョイントを作る。
作ったジョイントはすべて根本の子にし、回転・ジョイントの向き(jointOrient)・回転軸(rotateAxis)は 0 にする
(向きは根本と同じになる)。末端が根本の直下でなくても、2点を結ぶ直線上に並べる。

使い方:
    根本→末端の順に2つのジョイントを選んで HTools > rigging > createTwistJoints を開き、
    個数を決めて Create を押す。スクリプトからは ``createTwistJoints(root, end, count)`` を呼ぶ。

``HTools.rigging.createTwistJoints`` を mlib で書いた版。ノード・アトリビュート・位置の操作は mlib のオブジェクトで行い、
画面(Maya標準UI)は maya.cmds のまま。
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
from mlib.decorator import preservedSelection, undoChunk

from HTools import toolHelp


_WINDOW = "HToolsCreateTwistJoints"
#: 名前の既定の書式。``{root}`` は根本の短い名前(名前空間なし)、``{index}`` は 1 から始まる番号。
DEFAULT_NAME = "{root}_twist{index:02d}"
#: 一度に作れる個数の上限(入力の誤りで大量に作らないため)。
MAX_COUNT = 100
_LABEL_WIDTH = 110


def _warn(message):
    """警告をScript Editorとビューポートへ表示する。

    Args:
        message (str): 表示する英語のメッセージ。
    """
    cmds.warning(message)
    text = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    try:
        cmds.inViewMessage(amg='<font color="#ffcc00">{}</font>'.format(text), pos="midCenter", fade=True)
    except RuntimeError:
        pass


def _getNode(name):
    """ノード名から DAG ノードを取得する。

    Args:
        name (str): ノード名。

    Returns:
        mlib.DagNode: DAG ノード。

    Raises:
        ValueError: ノードが無い、名前が一意でない、DAG ノードでない場合。
    """
    try:
        node = mlib.getNode(name)
    except RuntimeError:
        raise ValueError("Node not found or not unique: {}".format(name))
    if not node.isType("dagNode"):
        raise ValueError("Not a DAG node: {}".format(name))
    return node


def _worldPosition(node):
    """DAG ノードのワールド位置(ピボットではなく移動の位置)を取得する。

    Args:
        node (mlib.DagNode): 対象のノード。

    Returns:
        mlib.Vector: ワールド座標の位置。
    """
    return node.getMatrix(ws=True).translate


def twistPositions(start, end, count):
    """2点の間を ``count + 1`` 等分した位置(両端を除く)を返す。

    Args:
        start (mlib.Vector): 根本の位置。
        end (mlib.Vector): 末端の位置。
        count (int): 作る個数。

    Returns:
        list[mlib.Vector]: 根本側から順に並べた位置。
    """
    offset = end - start
    return [start + offset * (index / float(count + 1)) for index in range(1, count + 1)]


def createTwistJoints(root, end, count=3, name=DEFAULT_NAME, radius=None):
    """根本と末端の間に、根本の子のツイストジョイントを均等に作る。

    作ったジョイントの回転・jointOrient・rotateAxis は 0 で、rotateOrder は根本に合わせる。
    操作全体を1回のUndoにまとめ、終わったら元の選択に戻す。

    Args:
        root (str): 根本のジョイント。
        end (str): 末端のジョイント(位置だけを使う。ジョイント以外のtransformも可)。
        count (int): 作る個数(1〜100)。
        name (str): 名前の書式。``{root}`` と ``{index}`` を使える。既定は ``{root}_twist{index:02d}``。
        radius (float | None): ジョイントの半径。None なら根本と同じ。

    Returns:
        list[str]: 作ったジョイント(根本側から順、フルパス)。

    Raises:
        ValueError: 入力が不正な場合(根本がジョイントでない、根本と末端が同じ、個数が範囲外、
            2点が同じ位置、名前の書式が不正)。
    """
    count = int(count)
    if not 1 <= count <= MAX_COUNT:
        raise ValueError("Count must be between 1 and {}.".format(MAX_COUNT))
    rootNode = _getNode(root)
    endNode = _getNode(end)
    if rootNode == endNode:
        raise ValueError("Root and End must be different nodes.")
    if not rootNode.isType("joint"):
        raise ValueError("Root must be a joint: {}".format(root))
    if not endNode.isType("transform"):
        raise ValueError("End must be a joint or transform: {}".format(end))
    start = _worldPosition(rootNode)
    finish = _worldPosition(endNode)
    if start.distanceTo(finish) < 1.0e-6:
        raise ValueError("Root and End are at the same position.")
    # 名前空間とDAGのパスを除いた短い名前。
    baseName = rootNode.getName(node=True, removeNamespace=True)
    try:
        names = [name.format(root=baseName, index=index) for index in range(1, count + 1)]
    except (KeyError, IndexError, ValueError) as error:
        raise ValueError("Invalid name pattern '{}': {}".format(name, error))
    if radius is None:
        radius = rootNode.getRadius()
    rotateOrder = rootNode.getPlug("rotateOrder").get()

    created = []
    # 選択の復元も含めて1回のUndoにまとめる(外側のチャンク名が表示名になる)。
    with undoChunk("createTwistJoints"), preservedSelection():
        for jointName, position in zip(names, twistPositions(start, finish, count)):
            joint = mlib.createNode("joint", name=jointName, parent=rootNode)
            # createNode の親付けだけでは inverseScale がつながらないので、親の scale をつなぐ。
            joint.connectInverseScale()
            joint.setRadius(radius)
            joint.getPlug("rotateOrder").set(rotateOrder)
            for attr in ("rotate", "jointOrient", "rotateAxis"):
                joint.getPlug(attr).set((0, 0, 0))
            # ワールド座標で置く。根本のスケールと segmentScaleCompensate は Maya が考慮する。
            joint.setTranslation(position, ws=True)
            created.append(joint.getFullName())
    return created


class CreateTwistJointsWindow:
    """根本・末端・個数を指定してツイストジョイントを作る画面(Maya標準UI)。"""

    def __init__(self):
        """既存のウィンドウを置き換え、選択から根本と末端を読み込む。"""
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        self.window = cmds.window(_WINDOW, title="Create Twist Joints", widthHeight=(420, 230))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
        cmds.separator(style="none", height=4)
        self.root = cmds.textFieldButtonGrp(label="Root joint", buttonLabel="<<",
                                            columnWidth=[(1, _LABEL_WIDTH)], adjustableColumn=2,
                                            buttonCommand=lambda *_: self._load(self.root))
        self.end = cmds.textFieldButtonGrp(label="End joint", buttonLabel="<<",
                                           columnWidth=[(1, _LABEL_WIDTH)], adjustableColumn=2,
                                           buttonCommand=lambda *_: self._load(self.end))
        self.count = cmds.intSliderGrp(label="Count", field=True, minValue=1, maxValue=10,
                                       fieldMinValue=1, fieldMaxValue=MAX_COUNT, value=3,
                                       columnWidth=[(1, _LABEL_WIDTH)])
        self.name = cmds.textFieldGrp(label="Name", text=DEFAULT_NAME, columnWidth=[(1, _LABEL_WIDTH)],
                                      adjustableColumn=2,
                                      annotation="{root}: root joint name, {index}: number from 1")
        cmds.text(label="Joints are evenly spaced, parented to Root, with zero rotation.", align="left")
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                       columnAttach=[(1, "both", 0), (2, "both", 4), (3, "both", 4)])
        cmds.button(label="Load Selection (Root, End)", command=lambda *_: self.loadSelection())
        cmds.button(label="Create", width=120, command=lambda *_: self.create())
        # 説明ページ(Sphinx)を開く。runpyで__main__として動くため名前を明示する。
        cmds.button(label="Help", width=60, command=lambda *_: toolHelp.openHelp("rigging", "createTwistJoints"))
        cmds.setParent("..")
        cmds.showWindow(self.window)
        self.loadSelection(quiet=True)

    def _load(self, field):
        """選択している最初のノードを入力欄へ入れる。

        Args:
            field (str): 入力欄(textFieldButtonGrp)。
        """
        selection = mlib.ls(selection=True)
        if not selection:
            _warn("Select a node first.")
            return
        cmds.textFieldButtonGrp(field, edit=True, text=str(selection[0]))

    def loadSelection(self, quiet=False):
        """選択した2つのノードを、選んだ順に根本・末端として入力欄へ入れる。

        Args:
            quiet (bool): True なら、2つ選ばれていなくても警告しない(開いたときの読み込み)。
        """
        selection = mlib.ls(orderedSelection=True) or mlib.ls(selection=True)
        if len(selection) < 2:
            if not quiet:
                _warn("Select the root joint, then the end joint.")
            return
        cmds.textFieldButtonGrp(self.root, edit=True, text=str(selection[0]))
        cmds.textFieldButtonGrp(self.end, edit=True, text=str(selection[1]))

    def create(self):
        """入力欄の内容でツイストジョイントを作る。

        Returns:
            list[str]: 作ったジョイント。失敗した場合は空のリスト。
        """
        root = cmds.textFieldButtonGrp(self.root, query=True, text=True).strip()
        end = cmds.textFieldButtonGrp(self.end, query=True, text=True).strip()
        if not root or not end:
            _warn("Set both Root joint and End joint.")
            return []
        try:
            joints = createTwistJoints(root, end, cmds.intSliderGrp(self.count, query=True, value=True),
                                       name=cmds.textFieldGrp(self.name, query=True, text=True).strip()
                                       or DEFAULT_NAME)
        except ValueError as error:
            _warn(str(error))
            return []
        om2.MGlobal.displayInfo("Created {} twist joint(s) under {}.".format(len(joints), root))
        return joints


def run():
    """ツイストジョイント作成の画面を表示する。

    Returns:
        CreateTwistJointsWindow: 表示した画面。
    """
    return CreateTwistJointsWindow()


if __name__ == "__main__":
    run()
