"""スキン全体の操作(バインド・バインドポーズ・ミラー・別のメッシュへのコピー・書き出し/読込み・ジョイントの移動)。"""

import mlib
from mlib.common import Selection
from mlib.decorator import preservedSkinShape, undoChunk

from . import influences as influences_module
from . import target as target_module

#: バインドの方法の名前と、skinCluster の bindMethod の値。
BIND_METHODS = (("closest", 0), ("hierarchy", 1), ("heatMap", 2))

#: ミラーの軸と、skinCluster のミラー面の名前。
MIRROR_AXES = {"x": "YZ", "y": "XZ", "z": "XY"}


def selectedJoints(selection=None):
    """選んでいるジョイントを、選んだ順に返す。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        list[mlib.Joint]: ジョイント。
    """
    selection = Selection.capture() if selection is None else selection
    return [node for node in selection.getNodes() if isinstance(node, mlib.Joint)]


def selectedMeshes(selection=None):
    """選んでいるメッシュ(transform ならその中間でないシェイプ)を、選んだ順に返す。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        list[mlib.Mesh]: メッシュ。
    """
    selection = Selection.capture() if selection is None else selection
    meshes = []
    for node in selection.getNodes():
        for mesh in target_module._meshes_of(node):
            if mesh not in meshes:
                meshes.append(mesh)
    return meshes


def skinnedMeshes():
    """シーンにある、バインドされたメッシュ(中間オブジェクトでないもの)を返す。

    Returns:
        list[mlib.Mesh]: メッシュ。
    """
    return [mesh for mesh in mlib.ls(type="mesh", noIntermediate=True) if mesh.getSkinClusters()]


@undoChunk("skinWeightKitBind")
def bind(joints, meshes, maxInfluences=4, method="closest"):
    """メッシュをジョイントへバインドする(既にバインドされたメッシュは飛ばす)。

    Args:
        joints (list[mlib.Joint]): インフルエンスにするジョイント。
        meshes (list[mlib.Mesh]): バインドするメッシュ。
        maxInfluences (int): 1頂点の最大数。
        method (str): :data:`BIND_METHODS` の名前。

    Returns:
        list[mlib.SkinCluster]: 作った skinCluster。

    Raises:
        ValueError: ジョイント・メッシュが無い、または method が不正な場合。
    """
    if not joints or not meshes:
        raise ValueError("Select joints and the meshes to bind")
    methods = dict(BIND_METHODS)
    if method not in methods:
        raise ValueError("method must be one of " + ", ".join(methods))
    skins = []
    for mesh in meshes:
        if mesh.getSkinClusters():
            continue
        skins.append(mlib.bindSkin(joints, mesh, maximumInfluences=maxInfluences, bindMethod=methods[method]))
    return skins


def goToBindPose(target):
    """バインドしたときのポーズへ戻す。

    Args:
        target (Target): 対象。

    Returns:
        None: 値を返さない。
    """
    target.requireSkin().restoreBindPose()


def mirror(target, axis="x", positiveToNegative=True):
    """ウェイトを左右へミラーする(スキン全体。インフルエンスは名前の左右で対応させる)。

    Args:
        target (Target): 対象。
        axis (str): ミラーの軸 ``"x"``・``"y"``・``"z"``。
        positiveToNegative (bool): Trueは+側から-側へ写す。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: axis が不正な場合。
    """
    if axis not in MIRROR_AXES:
        raise ValueError("axis must be one of x, y, z")
    target.requireSkin().mirrorWeights(plane=MIRROR_AXES[axis], positiveToNegative=positiveToNegative)


@undoChunk("skinWeightKitCopySkin")
def copySkin(source, meshes):
    """ウェイトを別のメッシュへ最近点でコピーする(バインドされていなければ同じインフルエンスでバインドする)。

    Args:
        source (Target): コピー元。
        meshes (Iterable[mlib.Mesh]): コピー先(コピー元と同じものは飛ばす)。

    Returns:
        int: コピーしたメッシュの数。

    Raises:
        ValueError: コピー先が無い場合。
    """
    skin = source.requireSkin()
    targets = [mesh for mesh in meshes if mesh != source.mesh]
    if not targets:
        raise ValueError("Select the skinned source mesh first, then the meshes to copy to")
    for mesh in targets:
        skin.copyWeightsTo(mesh)
    return len(targets)


def exportWeights(target, path):
    """ウェイトを mlib の ``mlib.skinWeights`` 形式の JSON へ書き出す。

    Args:
        target (Target): 対象。
        path (str): 書き出し先。

    Returns:
        None: 値を返さない。
    """
    target.requireSkin().exportWeights(path)


@undoChunk("skinWeightKitImport")
def importWeights(target, path):
    """``mlib.skinWeights`` 形式の JSON のウェイトを読み込む(頂点数が一致すること)。

    シーンにあるがスキンに無いインフルエンスは足し、シーンに無いインフルエンスは飛ばして警告する。

    Args:
        target (Target): 対象。
        path (str): 読み込むファイル。

    Returns:
        None: 値を返さない。
    """
    target.requireSkin().importWeights(path)


@undoChunk("skinWeightKitRemoveUnused")
def removeUnusedInfluences(target):
    """どの頂点にも影響していないインフルエンスを外す。

    Args:
        target (Target): 対象。

    Returns:
        int: 外した数。
    """
    return len(target.requireSkin().removeInfluences(unused=True))


#: スキニング方法の名前(skinningMethod の値の順)。
SKINNING_METHODS = ("classicLinear", "dualQuaternion", "weightBlended")

#: 正規化の方法の名前(normalizeWeights の値の順)。
NORMALIZE_MODES = ("none", "interactive", "post")


def getSettings(target):
    """skinCluster の設定を返す。

    Args:
        target (Target): 対象。

    Returns:
        dict: ``skinningMethod``(str)・``normalizeWeights``(str)・``maxInfluences``(int)・
        ``maintainMaxInfluences``(bool)。
    """
    skin = target.requireSkin()
    return {
        "skinningMethod": skin.getMode("skinning"),
        "normalizeWeights": skin.getMode("normalize"),
        "maxInfluences": int(skin.getMaxInfluences()),
        "maintainMaxInfluences": skin.getMaxInfluences(maintain=True),
    }


@undoChunk("skinWeightKitSkinSettings")
def setSettings(target, skinningMethod=None, normalizeWeights=None, maxInfluences=None, maintainMaxInfluences=None):
    """skinCluster の設定を変える(None の項目は変えない)。

    Args:
        target (Target): 対象。
        skinningMethod (str | None): :data:`SKINNING_METHODS` の名前。
        normalizeWeights (str | None): :data:`NORMALIZE_MODES` の名前。
        maxInfluences (int | None): 1頂点の最大数(1以上)。
        maintainMaxInfluences (bool | None): 塗るときに最大数を保つか。

    Returns:
        dict: 変えた後の設定(:func:`getSettings` と同じ形)。

    Raises:
        ValueError: 名前が不正、または maxInfluences が1未満の場合。
    """
    skin = target.requireSkin()
    if skinningMethod is not None:
        if skinningMethod not in SKINNING_METHODS:
            raise ValueError("skinningMethod must be one of " + ", ".join(SKINNING_METHODS))
        skin.setMode(skinningMethod, "skinning")
    if normalizeWeights is not None:
        if normalizeWeights not in NORMALIZE_MODES:
            raise ValueError("normalizeWeights must be one of " + ", ".join(NORMALIZE_MODES))
        skin.setMode(normalizeWeights, "normalize")
    if maxInfluences is not None:
        if maxInfluences < 1:
            raise ValueError("maxInfluences must be 1 or more")
        skin.setMaxInfluences(int(maxInfluences), maintain=skin.getMaxInfluences(maintain=True))
    if maintainMaxInfluences is not None:
        skin.setMaxInfluences(int(skin.getMaxInfluences()), maintain=bool(maintainMaxInfluences))

    return getSettings(target)


class MoveJointsSession(object):
    """スキンの形を保ったまま、ジョイントを動かせる状態にする(始めてから終えるまで)。

    Args:
        joints (list[mlib.Joint]): 動かすジョイント。
    """

    def __init__(self, joints):
        if not joints:
            raise ValueError("Select the joints to move")
        self.joints = list(joints)
        self._context = None

    def start(self):
        """ジョイントを動かせる状態にする。

        Returns:
            MoveJointsSession: 自身。
        """
        if self._context is None:
            # 開始と終了が別々のボタン操作になるため、コンテキストマネージャーを手で開閉する。
            self._context = preservedSkinShape(self.joints)
            self._context.__enter__()
        return self

    def finish(self):
        """動かした位置をバインドの位置として確定し、通常の状態へ戻す。

        Returns:
            None: 値を返さない。
        """
        if self._context is not None:
            context, self._context = self._context, None
            context.__exit__(None, None, None)

    def isActive(self):
        """動かせる状態かを返す。

        Returns:
            bool: 始めて終えていなければTrue。
        """
        return self._context is not None

def captureBindSettings(target):
    """現在の方式、影響名・ロックとデフォーマー履歴の順序を比較用に読む。"""
    cluster = target.requireSkin()
    nodes = cluster.getInfluences()
    locks = influences_module.lockedFlags(cluster, nodes)
    return {
        "mesh": target.mesh.getUuid(),
        "skin": cluster.getUuid(),
        "settings": getSettings(target),
        "influences": {node.getUuid(): (node.getName(full=True), lock) for node, lock in zip(nodes, locks)},
        "history": [(node.getUuid(), node.getName(short=True)) for node in target.mesh.getHistory(type="geometryFilter")],
    }


@undoChunk("skinWeightKitRestoreBindSettings")
def restoreBindSettings(target, recorded):
    """同じ構成のスキンで、記録した設定とロックを一度のUndoで復元する。"""
    now = captureBindSettings(target)
    if any(now[key] != recorded[key] for key in ("mesh", "skin")):
        raise ValueError("Select the recorded mesh and skinCluster")
    if now["influences"].keys() != recorded["influences"].keys():
        raise ValueError("Restore the original influence membership first")
    if [uid for uid, _ in now["history"]] != [uid for uid, _ in recorded["history"]]:
        raise ValueError("Restore the original deformer order first")
    cluster = target.requireSkin()
    settings = {key: value for key, value in recorded["settings"].items() if now["settings"][key] != value}
    attributes = set(settings)
    if attributes.intersection(("maxInfluences", "maintainMaxInfluences")):
        attributes.update(("maxInfluences", "maintainMaxInfluences"))
    plugs = [cluster.getPlug(name) for name in attributes]
    locks = []
    for node in cluster.getInfluences():
        uid = node.getUuid()
        state = recorded["influences"][uid][1]
        if now["influences"][uid][1] != state:
            plugs.append(node.getPlug("lockInfluenceWeights"))
            locks.append((node, state))
    for plug in plugs:
        if not plug.isSettable():
            raise ValueError("Cannot restore " + str(plug))
    if settings:
        setSettings(target, **settings)
    for node, state in locks:
        influences_module.setLocked(cluster, [node], state)


def compareBindSettings(target, recorded):
    """同一スキンの基準との差を返す。改名後もUUIDでインフルエンスを対応させる。"""
    now = captureBindSettings(target)
    if (now["mesh"], now["skin"]) != (recorded["mesh"], recorded["skin"]):
        raise ValueError("Select the mesh and skinCluster used for the recording")
    changes = []
    for name, old in recorded["settings"].items():
        if old != now["settings"][name]:
            changes.append("{}: {} → {}".format(name, old, now["settings"][name]))
    for uid in sorted(recorded["influences"].keys() | now["influences"].keys()):
        old = recorded["influences"].get(uid)
        new = now["influences"].get(uid)
        if old is None:
            changes.append("Added influence: " + new[0])
        elif new is None:
            changes.append("Removed influence: " + old[0])
        else:
            if old[0] != new[0]:
                changes.append("Influence path: {} → {}".format(old[0], new[0]))
            if old[1] != new[1]:
                changes.append("{} locked: {} → {}".format(new[0], old[1], new[1]))
    if [uid for uid, _ in recorded["history"]] != [uid for uid, _ in now["history"]]:
        changes.append("History: {} → {}".format(" / ".join(name for _, name in recorded["history"]),
                                                " / ".join(name for _, name in now["history"])))
    return changes
