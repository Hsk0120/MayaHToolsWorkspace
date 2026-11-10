"""形状をinfluenceへバインドし、作成したskinClusterを返す(``cmds.skinCluster`` 相当)。

Mayaの Bind Skin と同じく ``cmds.skinCluster`` でバインドする。既定は選択したjointだけをinfluenceにし
(``toSelectedBones=True``)、正規化はInteractive(``normalizeWeights=1``)にする。
``weights`` に :meth:`SkinCluster.exportWeights <mlib.nodes.skinCluster.SkinCluster.exportWeights>` の
ファイルを渡すと、ファイルのinfluenceでバインドし、ウェイトと設定をファイルから読み込む。

.. code-block:: python

    import mlib

    skin = mlib.bindSkin([hip, knee, ankle], "leg_geo", maximumInfluences=3)
    skin = mlib.bindSkin(None, "leg_geo", weights="leg_weights.json", namespaceMap={"chrA": "chrB"})
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk, undoTransaction

#: bindSkin が既定値を決めるフラグ(長名, 短名, 既定値)。
_DEFAULT_FLAGS = (
    ("toSelectedBones", "tsb", True),
    ("normalizeWeights", "nw", 1),
)

#: 作成専用のため受け付けないフラグ。
_REJECTED_FLAGS = frozenset(("query", "q", "edit", "e"))

#: ウェイトのファイルの設定から既定値を決めるフラグ(長名, 短名, 設定名)。
_FILE_FLAGS = (
    ("normalizeWeights", "nw", "normalizeWeights"),
    ("obeyMaxInfluences", "omi", "maintainMaxInfluences"),
    ("skinMethod", "sm", "skinningMethod"),
)


def bindSkin(joints, geometry, maximumInfluences=None, *, weights=None, nameMap=None, replace=None,
             namespaceMap=None, method="index", **kwargs):
    """形状を指定したinfluenceへバインドする。

    選択状態は参照しない。形状が既に skinCluster で変形されている場合は何もせず拒否する。
    fast引数は持たない(OpenMayaにバインドの同等機能が無い)。Undo有効時は1回で戻せる。

    ``weights`` を指定すると、バインドの後に :meth:`SkinCluster.setWeightsData
    <mlib.nodes.skinCluster.SkinCluster.setWeightsData>` と同じ規則でファイルのウェイト・DQブレンドウェイト・
    設定・ロック・ngSkinTools2のレイヤーを書き込む。``joints`` がNoneならファイルのinfluenceのうちシーンに
    あるもの(``nameMap``・``replace``・``namespaceMap`` で対応付け)でバインドする。``joints`` を指定した場合も、
    ファイルのinfluenceでシーンにあるものはウェイト0で追加してから書く。設定(最大インフルエンス数・その維持・
    正規化・スキニングの方法)は、引数で指定しなければファイルの値でバインドし、書込みの後はファイルの値になる。
    ファイルの検査(形式・頂点数・influence)はバインドの前に行い、書込みの途中の失敗はバインドごと巻き戻す。

    Args:
        joints (Node | str | Iterable[Node | str] | None): influenceにするjoint等のtransform。
            Noneは ``weights`` のファイルのinfluence(``weights`` が必要)。
        geometry (Node | str): Mayaがバインドできる形状またはそのtransform。``weights`` ではMesh。
        maximumInfluences (int | None): 1頂点に割り当てる最大数。正の整数。Noneは ``weights`` の
            ファイルの値、ファイルが無ければ4。
        weights (str | os.PathLike | None): ``mlib.skinWeights`` 形式のファイル。Noneは読み込まない。
        nameMap (dict[str, str] | None): ファイルのinfluenceの、名前空間を除いた名前の対応表。
        replace (Iterable[tuple[str, str]] | None): ファイルのinfluenceの名前に順に当てる文字列置換。
        namespaceMap (dict[str, str] | None): ファイルのinfluenceの名前空間の対応。
        method (str): ファイルの頂点の対応。``"index"`` (既定)は頂点番号、``"position"`` は最も近い位置。
        **kwargs (object): ``cmds.skinCluster`` のその他のフラグ(``bindMethod``・``dropoffRate``・
            ``name`` 等。長名・短名とも可)。``toSelectedBones``・``normalizeWeights`` を指定すると既定値を上書きする。

    Returns:
        SkinCluster: 作成したskinCluster。

    Raises:
        TypeError: query・editフラグ、または ``maximumInfluences`` の短名 ``mi`` を渡した場合、
            ``weights`` なしで対応付けの引数を渡した場合。
        ValueError: influenceが空、maximumInfluencesが正の整数でない、形状が既にスキニングされている、
            ``joints`` と ``weights`` が両方None、またはファイルの形式・頂点数・influenceが合わない場合。
        OSError: ファイルを読み込めない場合。
        RuntimeError: 名前を解決できない、またはMayaがバインドを拒否した場合。

    Examples:
        .. code-block:: python

            skin.exportWeights("body_weights.json")
            cmds.delete(skin)
            skin = mlib.bindSkin(None, "body_geo", weights="body_weights.json")
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node, Nodes
    from ..nodes.skinCluster import SkinCluster

    if "mi" in kwargs:
        raise TypeError("Use maximumInfluences instead of mi")
    rejected = sorted(_REJECTED_FLAGS.intersection(kwargs))
    if rejected:
        raise TypeError(f"bindSkin does not accept: {', '.join(rejected)}")
    if maximumInfluences is not None and (
            isinstance(maximumInfluences, bool) or not isinstance(maximumInfluences, int) or maximumInfluences < 1):
        raise ValueError("maximumInfluences must be a positive int")
    saved = None
    if weights is None:
        if nameMap is not None or replace is not None or namespaceMap is not None or method != "index":
            raise TypeError("nameMap, replace, namespaceMap and method require weights")
        if joints is None:
            raise ValueError("joints is required when weights is not given")
        influences = [Node(name) for name in Nodes._resolve_inputs(joints)]
    else:
        saved, influences = _load_weights(weights, geometry, nameMap, replace, namespaceMap, method)
        if joints is not None:
            influences = [Node(name) for name in Nodes._resolve_inputs(joints)]
    if not influences:
        raise ValueError("At least one influence is required")
    target = Node(Object._input_name(geometry))
    if SkinCluster._geometry_skin_uuids(target):
        raise ValueError("Geometry already has a skinCluster")
    flags = dict(kwargs)
    if maximumInfluences is None:
        stored = saved["settings"]["maxInfluences"] if saved else None
        maximumInfluences = 4 if stored is None else stored
    flags["maximumInfluences"] = maximumInfluences
    if saved:
        flags.update(_file_flags(saved["settings"], flags))
    for long, short, default in _DEFAULT_FLAGS:
        if long not in flags and short not in flags:
            flags[long] = default
    names = [node.getFullName() for node in influences]
    if saved is None:
        with undoChunk("mlibBindSkin"):
            result = cmds.skinCluster(names, target.getFullName(), **flags)
            return Node(result[0])
    # 循環参照の回避: mlib.json はnodesを読み込むため、使う時点で読み込む。
    from ..json.nameMapping import NameMapping
    with undoTransaction("mlibBindSkin"):
        skin = Node(cmds.skinCluster(names, target.getFullName(), **flags)[0])
        data, nodes, report = skin._prepare_weights_data(
            saved["data"], NameMapping(nameMap, replace, namespaceMap), method)
        skin._apply_weights_data(data, nodes, method, report, False)
    report.warn(f"SkinCluster {skin.getName()}")
    return skin


def _file_flags(settings, flags):
    """ファイルの設定から、指定されていない ``cmds.skinCluster`` のフラグを作る。

    Args:
        settings (dict): 検査済みの設定(:meth:`SkinCluster._parse_weights_data` の ``settings``)。
        flags (dict): 指定済みのフラグ。長名・短名のどちらかがあれば上書きしない。

    Returns:
        dict: 追加するフラグ。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.skinCluster import SkinCluster

    result = {}
    for long, short, key in _FILE_FLAGS:
        value = settings[key]
        if value is None or long in flags or short in flags:
            continue
        if key == "skinningMethod":
            value = SkinCluster._SKINNING_METHODS.index(value)
        elif key == "normalizeWeights":
            value = SkinCluster._NORMALIZE_MODES.index(value)
        result[long] = value
    return result


def _load_weights(path, geometry, nameMap, replace, namespaceMap, method):
    """ウェイトのファイルを読み込み、バインドの前にできる検査を行う。シーンは変更しない。

    Args:
        path (str | os.PathLike): ``mlib.skinWeights`` 形式のファイル。
        geometry (Node | str): バインドする形状またはそのtransform。
        nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
        replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
        namespaceMap (dict[str, str] | None): 名前空間の対応。
        method (str): ``"index"`` または ``"position"``。

    Returns:
        tuple[dict, list[Node]]: ``{"data": 元のデータ, "settings": 検査済みの設定}`` と、シーンにある
            ファイルのinfluence(重複を除いた保存順)。

    Raises:
        ValueError: ファイルの形式・データ・頂点数が不正、形状がMeshでない、または保存したinfluenceが
            1つもシーンに無い場合。
        OSError: 読み込みに失敗した場合。
    """
    # 循環参照の回避: mlib.json・nodesはcmdsより後に読み込まれる。
    from ..json import file
    from ..json.nameMapping import NameMapping
    from ..nodes.node import Node
    from ..nodes.skinCluster import SkinCluster

    SkinCluster._require_choice(method, "method", ("index", "position"))
    mapping = NameMapping(nameMap, replace, namespaceMap)
    _, data = file.load(path, SkinCluster._WEIGHTS_FORMAT, SkinCluster._WEIGHTS_VERSION)
    saved = SkinCluster._parse_weights_data(data)
    shape = Node(Object._input_name(geometry)).mpath()
    if shape.node().hasFn(om2.MFn.kTransform):
        shape.extendToShape()
    if not shape.node().hasFn(om2.MFn.kMesh):
        raise ValueError(f"weights requires a mesh: {shape.fullPathName()}")
    count = om2.MFnMesh(shape).numVertices
    if method == "index" and saved["vertexCount"] != count:
        raise ValueError(f"Cannot apply skin weights: Stored vertex count ({saved['vertexCount']}) does not match "
                         f"the vertex count of {shape.fullPathName()} ({count}); use method='position'")
    if method == "position" and not saved["positions"]:
        raise ValueError("Cannot apply skin weights: The data has no vertex positions")
    influences, seen = [], set()
    for ref in saved["influences"]:
        node = ref.resolve(mapping)
        if node is not None and node.getUuid() not in seen:
            seen.add(node.getUuid())
            influences.append(node)
    if not influences:
        raise ValueError("None of the stored influences exist in the scene")
    return {"data": data, "settings": saved["settings"]}, influences
