"""スキニング前の形状を維持してジョイントを編集するMaya標準UI。

開始・完了はそれぞれ1回のUndoで戻る。ユーザーの骨操作は通常のUndoを使う。
編集中の状態はnetworkノードに保存し、画面を閉じても再開できる。
階層・接続・名前・時間の変更は編集対象外。ウェイトは変更しない。
"""

import json
import math
from contextlib import contextmanager

import maya.cmds as cmds
import maya.api.OpenMaya as om


_WINDOW = "HToolsEditSkinJoints"
_SESSION = "HToolsSkinJointEditSession"
_DATA = "skinJointEditData"


@contextmanager
def _transaction(label):
    """Mayaコマンドの変更を1回のUndoにまとめる。"""
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Undo before running this tool.")
    cmds.undoInfo(openChunk=True, chunkName=label)
    try:
        yield
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True, undoName=True) == label:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)


def _writable(plug):
    """接続・ロックされたアトリビュートへの上書きを防ぐ。"""
    if (cmds.getAttr(plug, lock=True)
            or cmds.listConnections(plug, source=True, destination=False)
            or not cmds.getAttr(plug, settable=True)):
        raise RuntimeError("Attribute is locked, connected, or not writable: " + plug)


def _signature(skin):
    """インフルエンスの実インデックスと入力接続を記録する。"""
    return [[i, cmds.connectionInfo("{}.matrix[{}]".format(skin, i),
                                    sourceFromDestination=True)]
            for i in cmds.getAttr(skin + ".matrix", multiIndices=True) or []]


def _poseMembers(pose):
    """共有姿勢の構成と階層を検証するため長名で取得する。"""
    return sorted(cmds.ls(cmds.dagPose(pose, query=True, members=True) or [], long=True))


def _readSession():
    """シーンに保存した編集状態を読み込む。"""
    if not cmds.objExists(_SESSION + "." + _DATA):
        raise RuntimeError("Click Begin Edit first.")
    return json.loads(cmds.getAttr(_SESSION + "." + _DATA))


def _expandSharedSkins(skins):
    """共有bindPoseでつながるskinClusterを重複なく再帰的に収集する。

    Args:
        skins (set[str]): 選択階層から検出したskinCluster。

    Returns:
        tuple[set[str], set[str]]: 拡張後のskinClusterと関連bindPose。
    """
    skins = set(skins)
    pending = list(skins)
    poses = set()
    while pending:
        skin = pending.pop()
        for pose in cmds.listConnections(skin + ".bindPose", source=True,
                                         destination=False, type="dagPose") or []:
            if pose in poses:
                continue
            poses.add(pose)
            for plug in cmds.listConnections(pose + ".message", source=False,
                                             destination=True, plugs=True,
                                             type="skinCluster") or []:
                if not plug.endswith(".bindPose"):
                    continue
                shared_skin = plug.rsplit(".", 1)[0]
                if shared_skin not in skins:
                    skins.add(shared_skin)
                    pending.append(shared_skin)
    return skins, poses


def beginEdit():
    """選択ジョイントと子孫に接続したskinClusterの変形を無効にする。

    Returns:
        list[str]: 編集対象のskinCluster名。
    """
    if cmds.objExists(_SESSION):
        raise RuntimeError("An edit session already exists. Finish it before starting another.")
    joints = set(cmds.ls(selection=True, long=True, type="joint") or [])
    if not joints:
        raise RuntimeError("Select one or more joints.")
    for joint in list(joints):
        joints.update(cmds.listRelatives(joint, allDescendents=True,
                                        fullPath=True, type="joint") or [])
    skins = set()
    for joint in joints:
        skins.update(cmds.listConnections(joint + ".worldMatrix", source=False,
                                          destination=True, type="skinCluster") or [])
    if not skins:
        raise RuntimeError("No skinClusters were found in the selected joint hierarchies.")
    skins, poses = _expandSharedSkins(skins)
    records = []
    for skin in sorted(skins):
        if cmds.referenceQuery(skin, isNodeReferenced=True):
            raise RuntimeError("Referenced skinClusters are not supported: " + skin)
        _writable(skin + ".envelope")
        signature = _signature(skin)
        for index, source in signature:
            if not source:
                raise RuntimeError("Disconnected influences are not supported: " + skin)
            _writable("{}.bindPreMatrix[{}]".format(skin, index))
        records.append(dict(name=skin, uuid=cmds.ls(skin, uuid=True)[0],
                            envelope=cmds.getAttr(skin + ".envelope"),
                            signature=signature))
    for pose in poses:
        if cmds.lockNode(pose, query=True, lock=True)[0]:
            raise RuntimeError("The bindPose is locked: " + pose)
        if cmds.referenceQuery(pose, isNodeReferenced=True):
            raise RuntimeError("Referenced bindPoses are not supported: " + pose)
    data = dict(skins=records, poses={pose: _poseMembers(pose) for pose in sorted(poses)},
                time=cmds.currentTime(query=True))
    with _transaction("HTools: Begin Skin Joint Edit"):
        node = cmds.createNode("network", name=_SESSION, skipSelect=True)
        cmds.addAttr(node, longName=_DATA, dataType="string")
        cmds.setAttr(node + "." + _DATA, json.dumps(data), type="string")
        for record in records:
            cmds.setAttr(record["name"] + ".envelope", 0)
    return sorted(skins)


def finishEdit():
    """現在の骨の姿勢を基準に再設定し、元のenvelopeへ戻す。

    Returns:
        list[str]: 更新したskinCluster名。
    """
    data = _readSession()
    if cmds.currentTime(query=True) != data["time"]:
        raise RuntimeError("Return to the frame where editing started.")
    matrices = []
    for record in data["skins"]:
        skin = record["name"]
        if (not cmds.objExists(skin)
                or cmds.ls(skin, uuid=True) != [record["uuid"]]
                or _signature(skin) != record["signature"]):
            raise RuntimeError("An editing target was renamed, replaced, or reconnected: " + skin)
        _writable(skin + ".envelope")
        for index, source in record["signature"]:
            plug = "{}.bindPreMatrix[{}]".format(skin, index)
            _writable(plug)
            # envelope=0ではskinCluster側の評価が省略されるため接続元を評価する。
            matrix = om.MMatrix(cmds.getAttr(source))
            if (matrix.isSingular() or abs(matrix.det4x4()) < 1e-10
                    or not all(math.isfinite(value) for value in matrix)):
                raise RuntimeError("Cannot invert the influence matrix. Check its scale: " + skin)
            matrices.append((plug, list(matrix.inverse())))
    for pose in data["poses"]:
        if not cmds.objExists(pose):
            raise RuntimeError("The bindPose was deleted: " + pose)
        if _poseMembers(pose) != data["poses"][pose]:
            raise RuntimeError("The bindPose membership or hierarchy has changed: " + pose)
        shared = set(cmds.listConnections(pose + ".message", source=False,
                                          destination=True, type="skinCluster") or [])
        if shared - {record["name"] for record in data["skins"]}:
            raise RuntimeError("The bindPose sharing connections have changed: " + pose)
    # 全対象の検証・計算後に変更する。APIは計算のみ、書き込みはUndo対応cmds。
    with _transaction("HTools: Finish Skin Joint Edit"):
        for plug, values in matrices:
            cmds.setAttr(plug, *values, type="matrix")
        for pose in data["poses"]:
            members = cmds.dagPose(pose, query=True, members=True) or []
            if members:
                cmds.dagPose(members, reset=True, name=pose)
        for record in data["skins"]:
            cmds.setAttr(record["name"] + ".envelope", record["envelope"])
        cmds.delete(_SESSION)
    return [record["name"] for record in data["skins"]]


def freezeSelectedJoints():
    """選択ジョイントの回転だけをフリーズし、対応するバインド情報を更新する。

    rotateをjointOrientへ合成し、子のチャンネル・位置・スケールは変更しない。
    選択インフルエンスの現在姿勢を新しい基準とする。編集中のenvelopeは保持する。

    Returns:
        list[str]: フリーズしたジョイントの長名。
    """
    joints = sorted(set(cmds.ls(selection=True, long=True, type="joint") or []))
    if not joints:
        raise RuntimeError("Select one or more joints to freeze.")
    rotations = []
    matrices = {}
    poses = {}
    for joint in joints:
        if cmds.referenceQuery(joint, isNodeReferenced=True):
            raise RuntimeError("Referenced joints are not supported: " + joint)
        for attr in ("rotate", "jointOrient"):
            for axis in "XYZ":
                _writable(joint + "." + attr + axis)
        unit = om.MAngle.uiUnit()
        rotation = om.MEulerRotation(
            *[om.MAngle(v, unit).asRadians() for v in cmds.getAttr(joint + ".rotate")[0]],
            cmds.getAttr(joint + ".rotateOrder"))
        orient = om.MEulerRotation(
            *[om.MAngle(v, unit).asRadians() for v in cmds.getAttr(joint + ".jointOrient")[0]])
        combined = om.MTransformationMatrix(rotation.asMatrix() * orient.asMatrix()).rotation()
        rotations.append((joint, [om.MAngle(v).asUnits(unit) for v in combined]))
        for skin in set(cmds.listConnections(joint + ".worldMatrix", source=False,
                                             destination=True, type="skinCluster") or []):
            if cmds.referenceQuery(skin, isNodeReferenced=True):
                raise RuntimeError("Referenced skinClusters are not supported: " + skin)
            for index, source in _signature(skin):
                if not source or cmds.ls(source.rsplit(".", 1)[0], long=True) != [joint]:
                    continue
                plug = "{}.bindPreMatrix[{}]".format(skin, index)
                _writable(plug)
                matrix = om.MMatrix(cmds.getAttr(source))
                if (matrix.isSingular() or abs(matrix.det4x4()) < 1e-10
                        or not all(math.isfinite(value) for value in matrix)):
                    raise RuntimeError("Cannot invert the influence matrix. Check its scale: " + joint)
                # 回転フリーズはワールド行列を保つため、変更前に全対象を計算できる。
                matrices[plug] = list(matrix.inverse())
            for pose in cmds.listConnections(skin + ".bindPose", source=True,
                                             destination=False, type="dagPose") or []:
                if (cmds.lockNode(pose, query=True, lock=True)[0]
                        or cmds.referenceQuery(pose, isNodeReferenced=True)):
                    raise RuntimeError("The bindPose is locked or referenced: " + pose)
                if joint in _poseMembers(pose):
                    poses.setdefault(pose, set()).add(joint)
    with _transaction("HTools: Freeze Selected Joint Rotations"):
        for joint, orient in rotations:
            cmds.setAttr(joint + ".jointOrient", *orient)
            cmds.setAttr(joint + ".rotate", 0, 0, 0)
        for plug, values in matrices.items():
            cmds.setAttr(plug, *values, type="matrix")
        for pose, members in poses.items():
            cmds.dagPose(sorted(members), reset=True, name=pose)
    return joints


def _preserveChildContexts():
    """Maya標準の移動・回転・スケールコンテキストを返す。"""
    return ((cmds.manipMoveContext, "Move"),
            (cmds.manipRotateContext, "Rotate"),
            (cmds.manipScaleContext, "Scale"))


def getPreserveChildren():
    """標準3ツールの子保持設定を取得する。

    Returns:
        list[bool]: 移動・回転・スケールの有効状態。
    """
    return [bool(command(name, query=True, preserveChildPosition=True))
            for command, name in _preserveChildContexts()]


def setPreserveChildren(enabled):
    """標準3ツールの子保持を指定した状態に揃える。

    Args:
        enabled (bool): 有効にする場合True、無効にする場合False。

    Returns:
        bool: 切り替え後の有効状態。
    """
    previous = getPreserveChildren()
    enabled = bool(enabled)
    try:
        for command, name in _preserveChildContexts():
            command(name, edit=True, preserveChildPosition=enabled)
    except Exception:
        for (command, name), value in zip(_preserveChildContexts(), previous):
            command(name, edit=True, preserveChildPosition=value)
        raise
    return enabled


class _JointOrientPreserver:
    """UI存続中の選択ジョイントを監視し、子のワールド行列を保持する。

    scriptJobのcompressUndoで補正を元の編集にまとめる。プラグインは不要。
    選択変更・Undo/Redo・時刻変更で基準を更新し、古い姿勢への補正を防ぐ。
    """

    def __init__(self, window):
        """UIに所有させた監視を準備する。"""
        self.window = window
        self.jobs = []
        self.cache = {}
        self.busy = False
        for event in ("SelectionChanged", "Undo", "Redo", "timeChanged",
                      "SceneOpened", "NewSceneOpened"):
            cmds.scriptJob(event=[event, self.rebuild], parent=window)
        self.rebuild()

    def rebuild(self, *_):
        """選択対象を取り直し、削除やUndoで失われた監視も再構築する。"""
        if self.busy:
            return
        for job in self.jobs:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        self.jobs = []
        self.cache = {}
        if not all(getPreserveChildren()):
            return
        for joint in cmds.ls(selection=True, type="joint", long=True) or []:
            self.cache[joint] = None
            for attr in ("jointOrient", "translate", "rotate", "scale"):
                self.jobs.append(cmds.scriptJob(
                    attributeChange=[joint + "." + attr, self.changed],
                    allChildren=True, compressUndo=True, parent=self.window))
            for child in cmds.listRelatives(joint, children=True, type="transform", fullPath=True) or []:
                for attr in ("translate", "rotate", "scale", "offsetParentMatrix"):
                    self.jobs.append(cmds.scriptJob(
                        attributeChange=[child + "." + attr, self.changed],
                        allChildren=True, compressUndo=True, parent=self.window))
        self.snapshot()

    def snapshot(self):
        """現在のjointOrientと直下の子の行列を次の編集の基準にする。"""
        for joint in list(self.cache):
            if not cmds.objExists(joint):
                del self.cache[joint]
                continue
            children = cmds.listRelatives(joint, children=True, type="transform", fullPath=True) or []
            self.cache[joint] = (
                cmds.getAttr(joint + ".jointOrient")[0],
                {child: cmds.xform(child, query=True, worldSpace=True, matrix=True)
                 for child in children})

    def changed(self, *_):
        """jointOrient変更をまとめて補正し、他の編集では基準だけ更新する。"""
        if self.busy:
            return
        if not all(getPreserveChildren()):
            self.snapshot()
            return
        changed = [joint for joint, data in self.cache.items()
                   if data and cmds.objExists(joint)
                   and tuple(cmds.getAttr(joint + ".jointOrient")[0]) != tuple(data[0])]
        if not changed:
            self.snapshot()
            return
        targets = {}
        for joint in changed:
            targets.update(self.cache[joint][1])
        # Undo/Redoや回転フリーズでは、子が既に正しい位置に戻っている。
        # 同値のxformもUndoキューを変更するため、不要な書き込みを避ける。
        targets = {child: matrix for child, matrix in targets.items()
                   if not cmds.objExists(child) or
                   max(abs(a - b) for a, b in zip(
                       cmds.xform(child, query=True, worldSpace=True, matrix=True), matrix)) > 1e-8}
        self.busy = True
        try:
            # 全対象を事前確認する。ロックや入力接続を強制解除しない。
            for child in targets:
                if not cmds.objExists(child):
                    raise RuntimeError("A child was removed or reparented: " + child)
                for attr in ("translate", "rotate", "scale", "shear"):
                    for axis in ("XY", "XZ", "YZ") if attr == "shear" else "XYZ":
                        _writable(child + "." + attr + axis)
            for child in sorted(targets, key=lambda name: name.count("|")):
                cmds.xform(child, worldSpace=True, matrix=targets[child])
        except Exception as exc:
            cmds.warning("Joint Orient child preservation failed. Undo the edit. " + str(exc))
        finally:
            self.snapshot()
            self.busy = False


def run():
    """編集開始・完了の画面を開く。再実行しても編集状態を保持する。"""
    if cmds.window(_WINDOW, exists=True):
        cmds.deleteUI(_WINDOW)
    # cmds標準UIにMayaのスケーリングを任せ、独自のDPI倍率や固定フォントを重ねない。
    # windowPrefは削除せず、ユーザーが変更したサイズをMayaに保持させる。
    cmds.window(_WINDOW, title="Edit Skin Joints", widthHeight=(620, 360),
                sizeable=True, resizeToFitChildren=False)
    frame = cmds.formLayout()
    # 小さい画面や拡大表示でも下部の操作へ必ず到達できるようにする。
    scroll = cmds.scrollLayout(childResizable=True, minChildWidth=300)
    cmds.formLayout(frame, edit=True,
                    attachForm=[(scroll, edge, 0) for edge in ("top", "bottom", "left", "right")])
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=("both", 12))
    cmds.text(label="Pause skinning for the selected joints and their descendants.\n"
                    "Edit translation, rotation, or jointOrient, then click Finish Edit.\n"
                    "All influences are reset, including skins sharing a bindPose.\n"
                    "Do not change names, connections, hierarchy, or the current frame.",
              align="left", wordWrap=True)
    status = cmds.text(label="", align="left")
    targets = cmds.scrollField(editable=False, wordWrap=True, height=75, text="")
    orient_preserver = _JointOrientPreserver(_WINDOW)

    def preserve(enabled):
        """標準マニピュレーターとChannel Box監視を同時に切り替える。"""
        setPreserveChildren(enabled)
        orient_preserver.rebuild()

    def refreshPreserve(*_):
        """ツール切替時にもMaya側の実設定を色へ反映する。"""
        states = getPreserveChildren()
        enabled = all(states)
        cmds.button(preserve_button, edit=True, label="Begin Preserve Children",
                    backgroundColor=(0.65, 0.18, 0.18) if enabled else default_color,
                    enableBackground=True)

    def refresh(*_):
        """Undo/Redoや再表示後の状態をシーンから取得する。"""
        active = cmds.objExists(_SESSION + "." + _DATA)
        if active:
            cmds.button(begin_button, edit=True, backgroundColor=(0.65, 0.18, 0.18),
                        enableBackground=True)
        else:
            cmds.button(begin_button, edit=True, backgroundColor=default_color,
                        enableBackground=True)
        cmds.text(status, edit=True, label="Editing (envelopes disabled)" if active else "Ready")
        names = [record["name"] for record in _readSession()["skins"]] if active else []
        cmds.scrollField(targets, edit=True,
                         text="Affected skinClusters ({}):\n{}".format(len(names), "\n".join(names)))
        refreshPreserve()

    def invoke(action):
        """処理結果またはエラーを通知して状態表示を更新する。"""
        try:
            action()
        except Exception as exc:
            cmds.warning(str(exc))
        refresh()

    # 標準ボタンのbackgroundColor照会はテーマの実表示色と異なる場合がある。
    # 両ボタンに同じグレーを指定し、待機状態で黒くなることを防ぐ。
    default_color = (0.36, 0.36, 0.36)
    begin_button = cmds.button(label="1. Begin Edit", command=lambda *_: invoke(beginEdit),
                               backgroundColor=default_color, enableBackground=True)
    cmds.button(label="2. Finish Edit", command=lambda *_: invoke(finishEdit),
                backgroundColor=default_color, enableBackground=True)
    cmds.text(label="Begin and Finish each use one Undo. Joint edits use normal Undo.",
              align="left", wordWrap=True)
    cmds.separator(style="in", height=12)
    cmds.text(label="Extra", align="left")
    preserve_button = cmds.button(label="Begin Preserve Children",
                                  command=lambda *_: invoke(lambda: preserve(True)),
                                  backgroundColor=default_color, enableBackground=True)
    cmds.button(label="End Preserve Children",
                command=lambda *_: invoke(lambda: preserve(False)),
                backgroundColor=default_color, enableBackground=True)
    cmds.text(label="Preserves children with Maya's Move, Rotate, and Scale tools.\n"
                    "Also preserves children when editing selected joints' jointOrient in the Channel Box.\n"
                    "Keep this window open. Child transform channels must be unlocked and unconnected.",
              align="left", wordWrap=True)
    cmds.button(label="Freeze Selected Joint Rotations",
                command=lambda *_: invoke(freezeSelectedJoints))
    cmds.text(label="Selected joints only: rotate to jointOrient. Translation and scale are kept.\n"
                    "Updates their bindPreMatrix and bindPose to the current pose (one Undo).",
              align="left", wordWrap=True)
    for event in ("Undo", "Redo", "SceneOpened", "NewSceneOpened"):
        cmds.scriptJob(event=[event, refresh], parent=_WINDOW)
    cmds.scriptJob(event=["ToolChanged", refreshPreserve], parent=_WINDOW)
    refresh()
    cmds.showWindow(_WINDOW)


if __name__ == "__main__":
    run()
