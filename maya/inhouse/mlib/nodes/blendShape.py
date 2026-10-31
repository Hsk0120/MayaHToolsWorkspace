"""Maya の blendShape デフォーマを扱う。"""

import re

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import maya.mel as mel

from ..decorator import undoChunk
from .node import Node

#: エイリアスの対象 ``weight[<番号>]`` から論理番号を取り出す。
_WEIGHT_ALIAS = re.compile(r"^(?:weight|w)\[(\d+)\]$")


class BlendShape(Node):
    """blendShapeデフォーマの参照と、ターゲットの名前による照会・追加・除去を提供する。

    ターゲット名はウェイト(``weight[i]``)のエイリアスで、Shape Editorやチャンネルボックスに
    表示される名前と同じ。``"smile_L" in blendShape`` はターゲット名の有無を返す。
    作成・追加・除去はMaya標準コマンドを使い、fast引数は持たない(OpenMayaに同等の編集APIが無い)。

    Note:
        ターゲットの除去は :meth:`removeTarget` を使う。``getPlug("weight").removeElement(i)`` は
        ウェイトの要素だけを消し、エイリアスと ``inputTarget[].inputTargetGroup[i]`` を残す。
    """

    def __contains__(self, name):
        """ターゲット名(ウェイトのエイリアス)が存在するかを返す。

        Args:
            name (str): ターゲット名。

        Returns:
            bool: ターゲットが存在すればTrue。

        Raises:
            TypeError: nameが文字列以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        return self._target_lookup(name) is not None

    def getTargetNames(self):
        """ターゲット名を論理番号の順に取得する。

        Returns:
            list[str]: ウェイトのエイリアス。エイリアスの無いウェイト要素は含めない。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        return [name for _index, name in sorted(self._target_items())]

    def getTargetIndex(self, name):
        """ターゲット名に対応するウェイトの論理番号を取得する。

        Args:
            name (str): ターゲット名。

        Returns:
            int: ``weight`` の論理番号(``inputTargetGroup`` の番号と同じ)。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効な場合。
        """
        index = self._target_lookup(name)
        if index is None:
            raise ValueError(f"No blendShape target named {name!r} on {self.getName()}")
        return index

    def getWeightPlug(self, name):
        """ターゲット名に対応するウェイトのPlug(``weight[i]``)を取得する。

        Args:
            name (str): ターゲット名。

        Returns:
            Plug: ``weight`` の要素のPlug。接続・値の設定に使う。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効な場合。
        """
        return self.getPlug("weight")[self.getTargetIndex(name)]

    def getBaseGeometry(self):
        """変形する形状(出力ジオメトリ)を取得する。

        Returns:
            list[Node]: 変形対象の形状。geometryFilterの出力順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the geometry of")
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()]

    def addTarget(self, mesh, name=None):
        """ターゲットを空いている次の論理番号へ追加する(``cmds.blendShape(edit=True, target=...)`` 相当)。

        最初の変形対象(:meth:`getBaseGeometry` の先頭)に対するターゲットとして追加し、ウェイトは0。
        ターゲット形状との接続はMayaの既定どおり残す。Undo有効時は1回で戻せる。

        Args:
            mesh (str | Node): ターゲットの形状またはtransform。
            name (str | None): ターゲット名。Noneはメッシュの名前(Mayaの既定)。

        Returns:
            Plug: 追加したターゲットのウェイト(``weight[i]``)。

        Raises:
            TypeError: nameが文字列・None以外、またはmeshが対応しない型の場合。
            ValueError: nameが空文字列、同名のターゲットが既にある、またはmeshが無効な場合。
            RuntimeError: ノードが無効、変形対象が無い、またはMayaが追加を拒否した場合。
        """
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string or None")
        if name == "":
            raise ValueError("name must be a non-empty string or None")
        self._require_valid("add a target to")
        mesh_name = Node._input_name(mesh)
        if name is not None and name in self:
            raise ValueError(f"blendShape target {name!r} already exists on {self.getName()}")
        bases = self.getBaseGeometry()
        if not bases:
            raise RuntimeError(f"blendShape {self.getName()} has no geometry to add a target to")
        weight = self.getPlug("weight")
        indices = set(weight.getIndices()) | set(index for index, _name in self._target_items())
        index = max(indices) + 1 if indices else 0
        with undoChunk("mlibBlendShapeAddTarget"):
            cmds.blendShape(self.getFullName(), edit=True, target=(bases[0].getFullName(), index, mesh_name, 1.0))
            if name is not None and self._alias_of(index) != name:
                cmds.aliasAttr(name, f"{self.getFullName()}.weight[{index}]")
            return weight[index]

    def removeTarget(self, name):
        """ターゲットを完全に取り除く。ターゲット形状が削除済みでもよい。

        ``cmds.blendShape(edit=True, remove=True, target=...)`` と同じく、ウェイトの要素・エイリアス・
        全変形対象の ``inputTarget[].inputTargetGroup[i]``・Shape Editorの所属情報を取り除く
        (Maya標準の ``blendShapeDeleteTargetGroup`` を使う)。ウェイトへの入力接続は切断し、
        ウェイトを駆動するcombinationShapeノードはMayaの規則どおり削除する。ターゲット形状のノードは
        削除しない。Undo有効時は1回で戻せる。

        Args:
            name (str): ターゲット名。

        Returns:
            BlendShape: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: ターゲットが存在しない場合。
            RuntimeError: ノードが無効、ウェイトがロックされている、またはMayaが除去を拒否した場合。
        """
        index = self.getTargetIndex(name)
        if self.getPlug("weight")[index].isLocked():
            raise RuntimeError(f"Cannot remove the locked blendShape target {name!r} on {self.getName()}")
        with undoChunk("mlibBlendShapeRemoveTarget"):
            command = f'blendShapeDeleteTargetGroup("{self.getFullName()}", {index})'
            if not mel.eval(command):
                raise RuntimeError(f"Maya failed to remove blendShape target {name!r} on {self.getName()}")
            return self

    def _target_items(self):
        """エイリアスのあるウェイト要素を ``(論理番号, 名前)`` の並びで返す。

        Returns:
            list[tuple[int, str]]: OpenMayaのエイリアス一覧から得た対応。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the targets of")
        items = []
        for alias, attribute in om2.MFnDependencyNode(self.mnode()).getAliasList():
            match = _WEIGHT_ALIAS.match(attribute)
            if match is not None:
                items.append((int(match.group(1)), alias))
        return items

    def _target_lookup(self, name):
        """ターゲット名の論理番号を返す。無ければNone。

        Args:
            name (str): ターゲット名。

        Returns:
            int | None: 論理番号。

        Raises:
            TypeError: nameが文字列以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        if not isinstance(name, str):
            raise TypeError("blendShape target name must be a string")
        for index, alias in self._target_items():
            if alias == name:
                return index
        return None

    def _alias_of(self, index):
        """論理番号のウェイトのエイリアスを返す。無ければNone。

        Args:
            index (int): ウェイトの論理番号。

        Returns:
            str | None: エイリアス。
        """
        for item_index, alias in self._target_items():
            if item_index == index:
                return alias
        return None
