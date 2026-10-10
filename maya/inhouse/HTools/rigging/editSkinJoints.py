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
import maya.api.OpenMaya as om


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
        found = cmds.ls(record["uuid"], long=True) or []
        if not found:
            continue
        if len(found) != 1 or cmds.nodeType(found[0]) != "skinCluster":
            raise RuntimeError("Cannot resolve the recorded skinCluster: " + record["name"])
        _writable(found[0] + ".envelope")
        result.append((found[0], record))
    return result


def pauseEdit(*, undoable=True):
    """編集を確定せず、envelopeだけ復元して再開可能な状態を残す。

    Args:
        undoable (bool): 通常操作はTrue。MayaがUndoを停止するファイル処理ではFalse。
    """
    if not cmds.objExists(_SESSION + "." + _DATA):
        return
    data = _readSession()
    if data.get("paused", False):
        return
    targets = _sessionSkins(data)
    with _transaction("HTools: Pause Skin Joint Edit") if undoable else nullcontext():
        for skin, record in targets:
            cmds.setAttr(skin + ".envelope", record["envelope"])
        data["paused"] = True
        cmds.setAttr(_SESSION + "." + _DATA, json.dumps(data), type="string")


def discardEdit():
    """骨の編集とbind情報は触らず、envelopeを復元して記録を終了する。"""
    data = _readSession()
    targets = _sessionSkins(data)
    with _transaction("HTools: Discard Skin Edit Session"):
        for skin, record in targets:
            cmds.setAttr(skin + ".envelope", record["envelope"])
        cmds.delete(_SESSION)


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
        data = _readSession()
        if not data.get("paused", False):
            raise RuntimeError("An edit session already exists. Finish it before starting another.")
        if cmds.currentTime(query=True) != data["time"]:
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
                cmds.setAttr(skin + ".envelope", 0)
            data["paused"] = False
            cmds.setAttr(_SESSION + "." + _DATA, json.dumps(data), type="string")
        return [skin for skin, _ in targets]
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
        self.callbacks = []
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
            for callback in self.callbacks:
                om.MMessage.removeCallback(callback)
            self.callbacks = []
            if _owner() is self:
                delattr(maya, _OWNER)

    def install(self):
        """UI削除と保存/シーン切替/終了に対する後始末を登録する。"""
        cmds.scriptJob(uiDeleted=[_WINDOW, self.close], runOnce=True)
        self.callbacks.append(om.MSceneMessage.addCheckCallback(
            om.MSceneMessage.kBeforeSaveCheck, self.suspend))
        for message in (om.MSceneMessage.kBeforeNew,
                        om.MSceneMessage.kBeforeOpen, om.MSceneMessage.kAfterOpen):
            self.callbacks.append(om.MSceneMessage.addCallback(message, self.suspend))
        self.callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kMayaExiting, self.close))


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
        self.stopped = False
        self.events = []
        for event in ("SelectionChanged", "Undo", "Redo", "timeChanged",
                      "SceneOpened", "NewSceneOpened"):
            self.events.append(cmds.scriptJob(event=[event, self.rebuild], parent=window))
        self.rebuild()

    def stop(self):
        """自分が作成した監視だけを解放し、遅れて届く通知も無効にする。"""
        self.stopped = True
        for job in self.jobs + self.events:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        self.jobs = []
        self.events = []
        self.cache = {}

    def rebuild(self, *_):
        """選択対象を取り直し、削除やUndoで失われた監視も再構築する。"""
        if self.busy or self.stopped:
            return
        for job in self.jobs:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        self.jobs = []
        self.cache = {}
        if not _owner() or not _owner().enabled:
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
        if self.busy or self.stopped:
            return
        if not _owner() or not _owner().enabled:
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
        exists = cmds.objExists(_SESSION + "." + _DATA)
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
    owner.refresh = refresh
    refresh()
    cmds.showWindow(_WINDOW)


if __name__ == "__main__":
    run()
