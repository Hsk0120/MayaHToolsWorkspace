# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""単一の対象を複製し、複製結果の先頭ノードを型に応じたラッパーで返す。

``maya.cmds.duplicate`` に委ね、MayaのUndoに対応する(1回のUndoで戻せる)。fast引数は持たない。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    copied = mlib.duplicate(node, name="exampleCopy")

    # 複製したjointチェーンの全ノードへ接尾辞を付ける(L_hip_FK|L_knee_FK|...)。
    fk = mlib.duplicate("L_hip", suffix="_FK")
"""

import re
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import _merge_flags, undoChunk
from ..util import _UNSET
from typing import Any
from mlib.nodes.node import Node

_SUFFIX: Any

def duplicate(node: object, *, fullPath: bool = ..., f: bool = ..., inputConnections: bool = ..., ic: bool = ..., instanceLeaf: bool = ..., ilf: bool = ..., name: str = ..., n: str = ..., parentOnly: bool = ..., po: bool = ..., renameChildren: bool = ..., rc: bool = ..., returnRootsOnly: bool = ..., rr: bool = ..., smartTransform: bool = ..., st: bool = ..., transformsOnly: bool = ..., to: bool = ..., upstreamNodes: bool = ..., un: bool = ..., query: bool = ..., q: bool = ..., edit: bool = ..., e: bool = ..., suffix: str | None = ..., **kwargs: object) -> Node:
    """指定したノードを複製し、対応する mlib wrapper として返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    Args:
        node (object): 複製元のNode・Plug・Component・API参照または名前。Mayaへ渡す一意な名前へ変換する。
        fullPath (bool): Mayaの複製結果を完全DAGパスで受け取る指定。mlibの戻り型は変わらない。
        f (bool): fullPathの短縮名。同時指定はできない。
        inputConnections (bool): 入力接続も複製する指定。
        ic (bool): inputConnectionsの短縮名。同時指定はできない。
        instanceLeaf (bool): 末端ノードを複製せずインスタンス化する指定。
        ilf (bool): instanceLeafの短縮名。同時指定はできない。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parentOnly (bool): 指定した対象だけを複製し、子階層を含めない指定。
        po (bool): parentOnlyの短縮名。同時指定はできない。
        renameChildren (bool): 複製した子の名前をMayaの規則で補正する指定。
        rc (bool): renameChildrenの短縮名。同時指定はできない。
        returnRootsOnly (bool): Maya側の戻り値を複製ルートだけにする指定。mlibは先頭をラップする。
        rr (bool): returnRootsOnlyの短縮名。同時指定はできない。
        smartTransform (bool): 前回の複製からの変換差を使うMayaの複製指定。
        st (bool): smartTransformの短縮名。同時指定はできない。
        transformsOnly (bool): Transformのみを複製するMayaフラグ。
        to (bool): transformsOnlyの短縮名。同時指定はできない。
        upstreamNodes (bool): 上流の依存ノードも複製する指定。
        un (bool): upstreamNodesの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        suffix (str | None): mlib独自の指定。複製した起点ノードと、複製された全DAG子孫(shape・
            intermediateを含む)の名前を「複製元の名前(名前空間を除く) + suffix」にする
            (例: ``L_hip|L_knee`` を ``"_FK"`` で複製すると ``L_hip_FK|L_knee_FK``)。名前空間は
            Mayaが複製を置いた名前空間のまま。name を同時に指定した場合、起点ノードは name のまま
            にし、子孫だけに接尾辞を付ける。renameChildren=True とは同時に指定できない。
            インスタンスとして共有された子孫(instanceLeaf)・upstreamNodes 等で複製されたDGノードは
            改名しない。改名先が兄弟と重なる場合はMayaが番号を付ける。Noneは改名しない。
        **kwargs (object): 今後追加される未知のMayaフラグ。そのままMayaへ渡す。

    Returns:
        Node: 複製された起点ノードに対応するラッパー。

    Raises:
        TypeError: 長名・短名を同時指定した場合、nodeが対応しない型の場合、または suffix が文字列・
            None以外の場合。
        ValueError: node が空文字列・存在しない名前・複数に一致する名前、または削除済みの対象の場合。
            suffix が空文字列・英数字と ``_`` 以外を含む場合、または renameChildren=True と同時に
            指定した場合。
        RuntimeError: Maya が複製を拒否した場合。
    """
    ...

def _apply_suffix(source: om2.MObject, copied: om2.MObject, suffix: str, rename_root: bool) -> None:
    """複製元と複製を同じ子の並びで対応させ、複製側を「複製元の名前 + suffix」へ改名する。

    子の数が違う場合(transformsOnly 等で shape が複製されない場合)は shape を除いて対応させ、
    それでも合わない階層より下は改名しない。複製元と同じノード(共有インスタンス)は改名しない。

    Args:
        source (om2.MObject): 複製元の起点ノード。
        copied (om2.MObject): 複製の起点ノード。
        suffix (str): 付ける接尾辞。
        rename_root (bool): Falseなら起点ノードは改名しない(name 指定時)。

    Returns:
        None: 値を返さない。
    """
    ...

def _collect_child_pairs(source: om2.MObject, copied: om2.MObject, pairs: list[tuple[om2.MObject, om2.MObject]]) -> None:
    """複製元と複製の子を、同じ並び順で深さ優先に対応させて pairs へ追加する。

    Args:
        source (om2.MObject): 複製元のDAGノード。
        copied (om2.MObject): 対応する複製のDAGノード。
        pairs (list[tuple[om2.MObject, om2.MObject]]): 対応を追加するリスト。

    Returns:
        None: 値を返さない。
    """
    ...
