"""スキニング前の形状を維持してジョイントを編集するMaya標準UI。

開始・完了はそれぞれ1回のUndoで戻る。ユーザーの骨操作は通常のUndoを使う。
編集中の状態はnetworkノードに保存し、終了・保存時は一時停止して再開できる。
階層・接続・名前・時間の変更は編集対象外。ウェイトは変更しない。
"""

import json
import math
import os
import time
from pathlib import Path
from contextlib import contextmanager, nullcontext

import maya
import maya.cmds as cmds

import mlib
from mlib.common import Callbacks, ScriptJob, Time

from HTools import toolHelp


_WINDOW = "HToolsEditSkinJoints"
_SESSION = "HToolsSkinJointEditSession"
_DATA = "skinJointEditData"
_OWNER = "_htoolsSkinJointEditOwner"


def _owner():
    """import/reload/runpyをまたいで共有する現在のUI所有者を取得する。"""
    return getattr(maya, _OWNER, None)


def _sessionSkins(data):
    """記録したUUIDで復旧対象を解決し、同名の別ノードを変更しない。"""
    result = []
    for record in data["skins"]:
        found = mlib.ls(record["uuid"], long=True)
        if not found:
            continue
        if len(found) != 1 or found[0].getType() != "skinCluster":
            raise RuntimeError("Cannot resolve the recorded skinCluster: " + record["name"])
        _writable(found[0].getPlug("envelope"))
        result.append((found[0].getFullName(), record))
    return result


def pauseEdit(*, undoable=True):
    """編集を確定せず、envelopeだけ復元して再開可能な状態を残す。

    Args:
        undoable (bool): 通常操作はTrue。MayaがUndoを停止するファイル処理ではFalse。
    """
    if not mlib.objExists(_SESSION + "." + _DATA):
        return
    data = _readSession()
    if data.get("paused", False):
        return
    targets = _sessionSkins(data)
    with _transaction("HTools: Pause Skin Joint Edit") if undoable else nullcontext():
        for skin, record in targets:
            mlib.getPlug(skin + ".envelope").set(record["envelope"])
        data["paused"] = True
        mlib.getPlug(_SESSION + "." + _DATA).set(json.dumps(data))


def discardEdit():
    """骨の編集とbind情報は触らず、envelopeを復元して記録を終了する。"""
    data = _readSession()
    targets = _sessionSkins(data)
    with _transaction("HTools: Discard Skin Edit Session"):
        for skin, record in targets:
            mlib.getPlug(skin + ".envelope").set(record["envelope"])
        mlib.delete(_SESSION)


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
    plug = mlib.getPlug(plug)
    if plug.isLocked() or plug.getConnections(input=True) is not None or not plug.isSettable():
        raise RuntimeError("Attribute is locked, connected, or not writable: " + str(plug))


def _signature(skin):
    """インフルエンスの実インデックスと入力接続を記録する。"""
    matrix = mlib.getNode(skin).getPlug("matrix")
    return [[i, str(matrix[i].getConnections(input=True) or "")] for i in matrix.getIndices()]


def _poseMembers(pose):
    """共有姿勢の構成と階層を検証するため長名で取得する。"""
    return sorted(mlib.getNode(pose).getMembers().getFullNames())


def _readSession():
    """シーンに保存した編集状態を読み込む。"""
    if not mlib.objExists(_SESSION + "." + _DATA):
        raise RuntimeError("Click Begin Edit first.")
    return json.loads(mlib.getPlug(_SESSION + "." + _DATA).get())


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
        for pose in mlib.getNode(skin).getPlug("bindPose").getConnections(
                source=True, destination=False, type="dagPose", asNode=True).getNames():
            if pose in poses:
                continue
            poses.add(pose)
            for plug in mlib.getNode(pose).getPlug("message").getConnections(
                    source=False, destination=True, type="skinCluster"):
                if plug.getAttributeName() != "bindPose":
                    continue
                shared_skin = plug.getNode().getName()
                if shared_skin not in skins:
                    skins.add(shared_skin)
                    pending.append(shared_skin)
    return skins, poses


def beginEdit():
    """選択ジョイントと子孫に接続したskinClusterの変形を無効にする。

    Returns:
        list[str]: 編集対象のskinCluster名。
    """
    if mlib.objExists(_SESSION):
        data = _readSession()
        if not data.get("paused", False):
            raise RuntimeError("An edit session already exists. Finish it before starting another.")
        if Time.getCurrent() != data["time"]:
            raise RuntimeError("Return to the frame where editing started.")
        targets = _sessionSkins(data)
        if len(targets) != len(data["skins"]):
            raise RuntimeError("Some recorded skinClusters are missing. Resolve the recovery session first.")
        for skin, record in targets:
            if _signature(skin) != record["signature"]:
                raise RuntimeError("Influence connections changed: " + skin)
            record["name"] = skin
        with _transaction("HTools: Resume Skin Joint Edit"):
            for skin, _ in targets:
                mlib.getPlug(skin + ".envelope").set(0)
            data["paused"] = False
            mlib.getPlug(_SESSION + "." + _DATA).set(json.dumps(data))
        return [skin for skin, _ in targets]
    joints = set(mlib.ls(selection=True, long=True, type="joint"))
    if not joints:
        raise RuntimeError("Select one or more joints.")
    for joint in list(joints):
        joints.update(joint.getChildren(allDescendents=True, type="joint"))
    skins = set()
    for joint in joints:
        skins.update(joint.getPlug("worldMatrix").getConnections(
            source=False, destination=True, type="skinCluster", asNode=True).getNames())
    if not skins:
        raise RuntimeError("No skinClusters were found in the selected joint hierarchies.")
    skins, poses = _expandSharedSkins(skins)
    records = []
    for skin in sorted(skins):
        node = mlib.getNode(skin)
        if node.isFromReferencedFile():
            raise RuntimeError("Referenced skinClusters are not supported: " + skin)
        _writable(node.getPlug("envelope"))
        signature = _signature(skin)
        for index, source in signature:
            if not source:
                raise RuntimeError("Disconnected influences are not supported: " + skin)
            _writable(node.getPlug("bindPreMatrix")[index])
        records.append(dict(name=skin, uuid=node.getUuid(),
                            envelope=node.getPlug("envelope").get(),
                            signature=signature))
    for pose in poses:
        node = mlib.getNode(pose)
        if node.isLocked():
            raise RuntimeError("The bindPose is locked: " + pose)
        if node.isFromReferencedFile():
            raise RuntimeError("Referenced bindPoses are not supported: " + pose)
    data = dict(skins=records, poses={pose: _poseMembers(pose) for pose in sorted(poses)},
                time=Time.getCurrent())
    with _transaction("HTools: Begin Skin Joint Edit"):
        node = mlib.createNode("network", name=_SESSION, skipSelect=True)
        node.addAttr(_DATA, type="string")
        node.getPlug(_DATA).set(json.dumps(data))
        for record in records:
            mlib.getPlug(record["name"] + ".envelope").set(0)
    return sorted(skins)


def finishEdit():
    """現在の骨の姿勢を基準に再設定し、元のenvelopeへ戻す。

    Returns:
        list[str]: 更新したskinCluster名。
    """
    data = _readSession()
    if Time.getCurrent() != data["time"]:
        raise RuntimeError("Return to the frame where editing started.")
    matrices = []
    for record in data["skins"]:
        skin = record["name"]
        if (not mlib.objExists(skin)
                or mlib.getNode(skin).getUuid() != record["uuid"]
                or _signature(skin) != record["signature"]):
            raise RuntimeError("An editing target was renamed, replaced, or reconnected: " + skin)
        node = mlib.getNode(skin)
        _writable(node.getPlug("envelope"))
        for index, source in record["signature"]:
            plug = node.getPlug("bindPreMatrix")[index]
            _writable(plug)
            # envelope=0ではskinCluster側の評価が省略されるため接続元を評価する。
            matrix = mlib.getPlug(source).get()
            if (matrix.isSingular() or abs(matrix.det4x4()) < 1e-10
                    or not all(math.isfinite(value) for value in matrix)):
                raise RuntimeError("Cannot invert the influence matrix. Check its scale: " + skin)
            matrices.append((plug, matrix.inverse()))
    for pose in data["poses"]:
        if not mlib.objExists(pose):
            raise RuntimeError("The bindPose was deleted: " + pose)
        if _poseMembers(pose) != data["poses"][pose]:
            raise RuntimeError("The bindPose membership or hierarchy has changed: " + pose)
        shared = set(mlib.getNode(pose).getPlug("message").getConnections(
            source=False, destination=True, type="skinCluster", asNode=True).getNames())
        if shared - {record["name"] for record in data["skins"]}:
            raise RuntimeError("The bindPose sharing connections have changed: " + pose)
    # 全対象の検証・計算後に変更する。数学型は計算のみ、書き込みはUndo対応の通常の経路。
    with _transaction("HTools: Finish Skin Joint Edit"):
        for plug, matrix in matrices:
            plug.set(matrix)
        for pose in data["poses"]:
            # メンバーが無ければ何も変えない(元の処理と同じ)。
            mlib.getNode(pose).reset()
        for record in data["skins"]:
            mlib.getPlug(record["name"] + ".envelope").set(record["envelope"])
        mlib.delete(_SESSION)
    return [record["name"] for record in data["skins"]]


def freezeSelectedJoints():
    """選択ジョイントの回転だけをフリーズし、対応するバインド情報を更新する。

    rotateをjointOrientへ合成し、子のチャンネル・位置・スケールは変更しない。
    選択インフルエンスの現在姿勢を新しい基準とする。編集中のenvelopeは保持する。

    Returns:
        list[str]: フリーズしたジョイントの長名。
    """
    nodes = sorted(set(mlib.ls(selection=True, long=True, type="joint")), key=lambda node: node.getFullName())
    joints = [node.getFullName() for node in nodes]
    if not joints:
        raise RuntimeError("Select one or more joints to freeze.")
    matrices = {}
    poses = {}
    for node, joint in zip(nodes, joints):
        if node.isFromReferencedFile():
            raise RuntimeError("Referenced joints are not supported: " + joint)
        for attr in ("rotate", "jointOrient"):
            for child in node.getPlug(attr).getChildren():
                _writable(child)
        for skin in node.getPlug("worldMatrix").getConnections(
                source=False, destination=True, type="skinCluster", asNode=True):
            if skin.isFromReferencedFile():
                raise RuntimeError("Referenced skinClusters are not supported: " + skin.getName())
            for index, source in _signature(skin):
                if not source or mlib.getPlug(source).getNode() != node:
                    continue
                plug = skin.getPlug("bindPreMatrix")[index]
                _writable(plug)
                matrix = mlib.getPlug(source).get()
                if (matrix.isSingular() or abs(matrix.det4x4()) < 1e-10
                        or not all(math.isfinite(value) for value in matrix)):
                    raise RuntimeError("Cannot invert the influence matrix. Check its scale: " + joint)
                # 回転フリーズはワールド行列を保つため、変更前に全対象を計算できる。
                matrices[str(plug)] = (plug, matrix.inverse())
            for pose in skin.getPlug("bindPose").getConnections(
                    source=True, destination=False, type="dagPose", asNode=True):
                if pose.isLocked() or pose.isFromReferencedFile():
                    raise RuntimeError("The bindPose is locked or referenced: " + pose.getName())
                if joint in _poseMembers(pose):
                    poses.setdefault(pose.getName(), set()).add(joint)
    with _transaction("HTools: Freeze Selected Joint Rotations"):
        for node in nodes:
            # rotateをjointOrientへ合成して0にする(ワールドの姿勢は変わらない)。
            node.freezeRotate()
        for plug, matrix in matrices.values():
            plug.set(matrix)
        for pose, members in poses.items():
            mlib.getNode(pose).reset(sorted(members))
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
    owner = _owner()
    if owner is None or owner.closed:
        raise RuntimeError("Open Edit Skin Joints before enabling Preserve Children.")
    owner.preserve(bool(enabled))
    return bool(enabled)


def _restoreContexts(values):
    """保存した3標準ツールの設定を復元する。"""
    for (command, name), value in zip(_preserveChildContexts(), values):
        command(name, edit=True, preserveChildPosition=value)


def _processAlive(pid):
    """別のMayaプロセスが所有する復旧情報を回収しないため生存確認する。"""
    if type(pid) is not int or pid <= 0:
        raise ValueError("Invalid process ID in recovery data")
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _recoveryFolder():
    """このツール専用の設定復旧ファイル保存先を返す。"""
    return Path(cmds.internalVar(userPrefDir=True)) / "HToolsEditSkinJointsRecovery"


def _recoverContexts():
    """終了済みプロセスの設定を回収する。起動中の別Mayaには触れない。"""
    folder = _recoveryFolder()
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["pid"] != os.getpid() and _processAlive(data["pid"]):
                continue
            values = data["contexts"]
            if len(values) != 3 or any(type(value) is not bool for value in values):
                raise ValueError("Invalid context recovery data")
            _restoreContexts(values)
            path.unlink()
        except Exception as exc:
            cmds.warning("Could not restore previous Edit Skin Joints settings: " + str(exc))


class _WindowOwner:
    """単一UI・一時設定・コールバック・復旧情報の所有者。"""

    def __init__(self):
        """外部設定を変更する前に、寿命管理の状態を初期化する。"""
        self.closed = False
        self.enabled = False
        self.original = None
        self.preserver = None
        self.callbacks = Callbacks()
        self.refresh = None
        self.journal = _recoveryFolder() / (str(os.getpid()) + ".json")

    def preserve(self, enabled):
        """開始前の設定をディスクへ記録し、終了時には元の値を復元する。"""
        if self.closed:
            return
        if enabled and not self.enabled:
            if self.journal.exists():
                raise RuntimeError("Unresolved recovery settings exist. Reopen this tool to recover them first.")
            self.original = getPreserveChildren()
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.journal.with_suffix(".tmp")
            temporary.write_text(json.dumps(dict(pid=os.getpid(), contexts=self.original,
                                                  created=time.time())), encoding="utf-8")
            temporary.replace(self.journal)
            try:
                _restoreContexts([True, True, True])
            except Exception:
                _restoreContexts(self.original)
                raise
            self.enabled = True
        elif not enabled:
            self.enabled = False
            if self.original is not None:
                _restoreContexts(self.original)
                self.original = None
                if self.journal.exists():
                    self.journal.unlink()
        if self.preserver:
            self.preserver.rebuild()

    def suspend(self, *_):
        """保存・シーン切替前に一時設定とenvelopeを復元する。"""
        if self.closed:
            return True
        try:
            self.preserve(False)
            # Mayaは保存/読込の通知中にUndoを無効にする。設定を強制的に有効化しない。
            pauseEdit(undoable=bool(cmds.undoInfo(query=True, state=True)))
        except Exception as exc:
            cmds.warning("Could not pause skin editing. Recovery data was kept: " + str(exc))
            return False
        if self.refresh and cmds.window(_WINDOW, exists=True):
            self.refresh()
        return True

    def close(self, *_):
        """閉じる・deleteUI・終了処理の重複呼出でも一度だけ解放する。"""
        if self.closed:
            return
        try:
            self.suspend()
        finally:
            self.closed = True
            if self.preserver:
                self.preserver.stop()
            self.callbacks.remove()
            if _owner() is self:
                delattr(maya, _OWNER)

    def install(self):
        """UI削除と保存/シーン切替/終了に対する後始末を登録する。"""
        ScriptJob(uiDeleted=_WINDOW, callback=self.close, runOnce=True)
        # suspend が False を返したら保存を止める。
        self.callbacks.addSceneCheckCallback("beforeSaveCheck", self.suspend)
        for event in ("beforeNew", "beforeOpen", "afterOpen"):
            self.callbacks.addSceneCallback(event, self.suspend)
        self.callbacks.addSceneCallback("mayaExiting", self.close)


class _JointOrientPreserver:
    """UI存続中の選択ジョイントを監視し、子のワールド行列を保持する。

    scriptJobのcompressUndoで補正を元の編集にまとめる。プラグインは不要。
    選択変更・Undo/Redo・時刻変更で基準を更新し、古い姿勢への補正を防ぐ。
    """

    _attrs = ("jointOrient", "translate", "rotate", "scale", "shear",
              "rotateAxis", "rotatePivot", "rotatePivotTranslate",
              "scalePivot", "scalePivotTranslate", "rotateOrder", "offsetParentMatrix")

    def __init__(self, window):
        """UIに所有させた監視を準備する。"""
        self.window = window
        self.jobs = []
        self.cache = {}
        self.busy = False
        self.stopped = False
        self.events = []
        self.history_pending = False
        self.callbacks = Callbacks()
        # APIイベントで先に履歴・時刻変更を識別する。scriptJob同士の実行順に
        # 依存すると、履歴復元やアニメーション評価を直接編集と誤認する。
        try:
            for event in ("Undo", "Redo", "timeChanged"):
                self.callbacks.addEventCallback(event, self.historyChanged)
            for event in ("SelectionChanged", "Undo", "Redo", "timeChanged",
                          "SceneOpened", "NewSceneOpened"):
                self.events.append(ScriptJob(event=event, callback=self.rebuild, parent=window))
            self.rebuild()
        except Exception:
            self.stop()
            raise

    def historyChanged(self, *_):
        """履歴・時刻変更に伴う遅延通知を、基準の再構築まで補正対象から除外する。"""
        self.history_pending = True

    def stop(self):
        """自分が作成した監視だけを解放し、遅れて届く通知も無効にする。"""
        self.stopped = True
        self.callbacks.remove()
        for job in self.jobs + self.events:
            job.stop()
        self.jobs = []
        self.events = []
        self.cache = {}

    def rebuild(self, *_):
        """選択対象を取り直し、削除やUndoで失われた監視も再構築する。"""
        if self.busy or self.stopped:
            return
        for job in self.jobs:
            job.stop()
        self.jobs = []
        self.cache = {}
        self.history_pending = False
        if not _owner() or not _owner().enabled:
            return
        for node in mlib.ls(selection=True, type="joint", long=True):
            joint = node.getFullName()
            self.cache[joint] = None
            for attr in self._attrs:
                self.jobs.append(ScriptJob(
                    attribute=node.getPlug(attr), callback=self.changed,
                    allChildren=True, compressUndo=True, parent=self.window))
            for child in node.getChildren(type="transform"):
                for attr in ("translate", "rotate", "scale", "offsetParentMatrix"):
                    self.jobs.append(ScriptJob(
                        attribute=child.getPlug(attr), callback=self.changed,
                        allChildren=True, compressUndo=True, parent=self.window))
        self.snapshot()

    def snapshot(self):
        """ローカルの編集値と直下の子の行列を次の編集の基準にする。"""
        for joint in list(self.cache):
            if not mlib.objExists(joint):
                del self.cache[joint]
                continue
            children = mlib.getNode(joint).getChildren(type="transform")
            self.cache[joint] = (
                self.signature(joint),
                {child.getFullName(): child.getPlug("worldMatrix")[0].get()
                 for child in children})

    def signature(self, joint):
        """親からの伝播を直接編集と誤認しないようローカル値を取得する。"""
        node = mlib.getNode(joint)
        return tuple(node.getPlug(attr).get() for attr in self._attrs)

    def restore(self, child, matrix):
        """SSC・回転補助成分を除いて分解し、Undo可能なローカル値で復元する。

        非均一スケールと回転を併用したjointにxformのワールド行列を
        直接設定するとSSCの補正が一致しないため、成分を明示的に解く。
        行列・角度は内部単位(cm・rad)のまま書く。
        """
        node = mlib.getNode(child)
        local = mlib.Matrix(matrix) * node.getPlug("parentInverseMatrix")[0].get()
        if local.isSingular():
            raise RuntimeError("Cannot preserve a child with a singular matrix: " + child)
        joint = isinstance(node, mlib.Joint)
        corrected = local
        if joint and node.getSegmentScaleCompensate():
            inverse_scale = node.getInverseScale()
            if any(abs(value) < 1e-12 for value in inverse_scale):
                raise RuntimeError("Cannot preserve a child with zero inverseScale: " + child)
            corrected = local * mlib.Matrix.compose(scale=inverse_scale)
        parts = mlib.Transformation(corrected)

        orientation = node.getJointOrient().asMatrix() if joint else mlib.Matrix()
        rotate_axis = mlib.EulerRotate(*node.getPlug("rotateAxis").get(unit="rad"))
        rotation = mlib.Transformation(
            rotate_axis.asMatrix().inverse()
            * parts.rotate.asMatrix() * orientation.inverse()).rotate
        current = node.getPlug("rotate").get()
        rotation.reorderIt(current.order)
        rotation = rotation.closestSolution(current)
        node.getPlug("scale").set(parts.scale)
        node.getPlug("shear").set(parts.shear)
        node.getPlug("rotate").set(tuple(rotation), unit="rad")
        # ピボット補償を含む実際のローカル行列との差でtranslateを求める。
        actual = node.getPlug("matrix").get()
        translation = node.getPlug("translate").get()
        node.getPlug("translate").set([translation[i] + local[12 + i] - actual[12 + i] for i in range(3)])

    def changed(self, *_):
        """Matchや直接編集をまとめて補正し、選択された子は編集対象として優先する。"""
        if self.busy or self.stopped or self.history_pending:
            return
        if not _owner() or not _owner().enabled:
            self.snapshot()
            return
        changed = [joint for joint, data in self.cache.items()
                   if data and mlib.objExists(joint)
                   and self.signature(joint) != data[0]]
        if not changed:
            self.snapshot()
            return
        targets = {}
        for joint in self.cache:
            if joint in changed or any(joint.startswith(parent + "|") for parent in changed):
                targets.update(self.cache[joint][1])
        # 選択された子は編集対象として優先する。Match後のローカル値が
        # 偶然同じでも、親の編集に伴うワールド変化を打ち消さない。
        # 選択された子の未選択の子孫は、その子の保存行列で保持する。
        for joint in self.cache:
            targets.pop(joint, None)
        # 未選択の中間ジョイントを保持すると、その下の選択ジョイントも
        # 動く。選択ジョイントのMatch結果を復元点として途中へ挟む。
        for joint in self.cache:
            if any(joint.startswith(parent + "|") for parent in targets):
                targets[joint] = mlib.getNode(joint).getPlug("worldMatrix")[0].get()
        self.busy = True
        try:
            affected = []
            for child in sorted(targets, key=lambda name: name.count("|")):
                if (not mlib.objExists(child)
                        or any(child.startswith(parent + "|") for parent in affected)
                        or max(abs(a - b) for a, b in zip(
                            mlib.getNode(child).getPlug("worldMatrix")[0].get(), targets[child])) > 1e-8):
                    affected.append(child)
            # 全対象を事前確認する。ロックや入力接続を強制解除しない。
            for child in affected:
                if not mlib.objExists(child):
                    raise RuntimeError("A child was removed or reparented: " + child)
                node = mlib.getNode(child)
                for attr in ("translate", "rotate", "scale", "shear"):
                    for plug in node.getPlug(attr).getChildren():
                        _writable(plug)
            for child in affected:
                # 親の補正後に判定する。同値書込はRedo履歴を壊し得る。
                if max(abs(a - b) for a, b in zip(
                        mlib.getNode(child).getPlug("worldMatrix")[0].get(), targets[child])) > 1e-8:
                    self.restore(child, targets[child])
        except Exception as exc:
            cmds.warning("Child preservation failed. Undo the edit. " + str(exc))
        finally:
            self.snapshot()
            self.busy = False


def run():
    """単一の画面を開き、中断された設定を回収する。"""
    previous = _owner()
    if previous and not previous.closed and cmds.window(_WINDOW, exists=True):
        cmds.showWindow(_WINDOW)
        return
    if previous:
        previous.close()
    if cmds.window(_WINDOW, exists=True):
        cmds.deleteUI(_WINDOW)
    _recoverContexts()
    # クラッシュ/旧版で無効化されたまま保存されたシーンも、自動確定せず復旧する。
    pauseEdit()
    owner = _WindowOwner()
    setattr(maya, _OWNER, owner)
    try:
        _buildWindow(owner)
    except Exception:
        owner.close()
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        raise


def _buildWindow(owner):
    """所有者の監視下でUIを構築し、初期化失敗時に解放できるようにする。"""
    # cmds標準UIにMayaのスケーリングを任せ、独自のDPI倍率や固定フォントを重ねない。
    # windowPrefは削除せず、ユーザーが変更したサイズをMayaに保持させる。
    cmds.window(_WINDOW, title="Edit Skin Joints", widthHeight=(620, 360),
                sizeable=True, resizeToFitChildren=False, closeCommand=owner.close)
    owner.install()
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
    owner.preserver = orient_preserver

    def preserve(enabled):
        """標準マニピュレーターとChannel Box監視を同時に切り替える。"""
        setPreserveChildren(enabled)

    def refreshPreserve(*_):
        """ツール切替時にもMaya側の実設定を色へ反映する。"""
        if owner.closed:
            return
        enabled = owner.enabled
        cmds.button(preserve_button, edit=True, label="Begin Preserve Children",
                    backgroundColor=(0.65, 0.18, 0.18) if enabled else default_color,
                    enableBackground=True)

    def refresh(*_):
        """Undo/Redoや再表示後の状態をシーンから取得する。"""
        if owner.closed:
            return
        exists = mlib.objExists(_SESSION + "." + _DATA)
        data = _readSession() if exists else None
        paused = bool(data and data.get("paused", False))
        active = exists and not paused
        if active:
            cmds.button(begin_button, edit=True, backgroundColor=(0.65, 0.18, 0.18),
                        enableBackground=True)
        else:
            cmds.button(begin_button, edit=True, backgroundColor=default_color,
                        enableBackground=True)
        cmds.text(status, edit=True, label=("Editing (envelopes disabled)" if active else
                                           "Paused / recovered: Begin Edit to resume, or Finish Edit to commit." if paused else "Ready"))
        names = [record["name"] for record in data["skins"]] if data else []
        cmds.scrollField(targets, edit=True,
                         text="Affected skinClusters ({}):\n{}".format(len(names), "\n".join(names)))
        refreshPreserve()

    def invoke(action):
        """処理結果またはエラーを通知して状態表示を更新する。"""
        if owner.closed:
            return
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
    cmds.text(label="Closing or saving pauses editing without committing the bind pose.\n"
                    "Joint edits remain; Begin Edit resumes the recorded session.", align="left", wordWrap=True)
    cmds.separator(style="in", height=12)
    cmds.text(label="Extra", align="left")
    preserve_button = cmds.button(label="Begin Preserve Children",
                                  command=lambda *_: invoke(lambda: preserve(True)),
                                  backgroundColor=default_color, enableBackground=True)
    cmds.button(label="End Preserve Children",
                command=lambda *_: invoke(lambda: preserve(False)),
                backgroundColor=default_color, enableBackground=True)
    cmds.text(label="Preserves children with Maya's Move, Rotate, and Scale tools.\n"
                    "Also supports Match Transformations and direct transform / jointOrient edits.\n"
                    "Selected joints remain editable; unselected children keep their world transforms.\n"
                    "Keep this window open. Child transform channels must be unlocked and unconnected.",
              align="left", wordWrap=True)
    cmds.button(label="Freeze Selected Joint Rotations",
                command=lambda *_: invoke(freezeSelectedJoints))
    cmds.text(label="Selected joints only: rotate to jointOrient. Translation and scale are kept.\n"
                    "Updates their bindPreMatrix and bindPose to the current pose (one Undo).",
              align="left", wordWrap=True)
    cmds.separator(style="in", height=12)
    # 説明ページ(Sphinx)を開く。runpyで__main__として動くため名前を明示する。
    cmds.button(label="Help", command=lambda *_: toolHelp.openHelp("rigging", "editSkinJoints"))
    for event in ("Undo", "Redo", "SceneOpened", "NewSceneOpened"):
        ScriptJob(event=event, callback=refresh, parent=_WINDOW)
    ScriptJob(event="ToolChanged", callback=refreshPreserve, parent=_WINDOW)
    owner.refresh = refresh
    refresh()
    cmds.showWindow(_WINDOW)


if __name__ == "__main__":
    run()
