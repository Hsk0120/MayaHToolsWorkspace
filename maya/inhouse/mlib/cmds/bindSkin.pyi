# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from ..decorator import _pick_alias, undoChunk, undoTransaction
from ..util import _UNSET
from typing import Iterable
from mlib.nodes.node import Node
from mlib.nodes.skinCluster import SkinCluster
import os

_DEFAULT_FLAGS: tuple
_REJECTED_FLAGS: frozenset
_FILE_FLAGS: tuple

def bindSkin(joints: Node | str | Iterable[Node | str] | None, geometry: Node | str, maximumInfluences: int | None = ..., *, mi: int | None = ..., weights: str | os.PathLike | None = ..., nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., method: str = ..., **kwargs: object) -> SkinCluster:
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
            ファイルの値、ファイルが無ければ4。既定None。
        mi (int | None): maximumInfluencesの短縮名。同時指定はできない。
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
        TypeError: maximumInfluencesと短縮名 ``mi`` を同時に指定した場合、query・editフラグを渡した場合、
            または ``weights`` なしで対応付けの引数を渡した場合。
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
    ...

def _file_flags(settings: dict, flags: dict) -> dict:
    """ファイルの設定から、指定されていない ``cmds.skinCluster`` のフラグを作る。

    Args:
        settings (dict): 検査済みの設定(:meth:`SkinCluster._parse_weights_data` の ``settings``)。
        flags (dict): 指定済みのフラグ。長名・短名のどちらかがあれば上書きしない。

    Returns:
        dict: 追加するフラグ。
    """
    ...

def _load_weights(path: str | os.PathLike, geometry: Node | str, nameMap: dict[str, str] | None, replace: Iterable[tuple[str, str]] | None, namespaceMap: dict[str, str] | None, method: str) -> tuple[dict, list[Node]]:
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
    ...
