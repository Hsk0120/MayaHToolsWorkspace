"""ドライバーPlugと駆動先Plugの組を扱う。"""

import math
import maya.cmds as cmds

from .._core.collection import BulkCollection, bulk_api
from ..decorators.undo import undo_chunk
from ..nodes.node import Node
from ..plugs.plug import Plug


def _plug(value):
    """Plugまたは属性名を、数値スカラーのPlugとして検証する。"""
    if isinstance(value, Plug):
        result = value
    elif isinstance(value, str) and "." in value:
        name, attribute = value.split(".", 1)
        result = Node(name).plug(attribute)
    else:
        raise TypeError("Expected a Plug or node.attribute string")
    if not result.node.is_valid() or not cmds.objExists(result.full_name):
        raise RuntimeError("Cannot access an invalid plug")
    if result.mplug().isArray or result.mplug().isCompound:
        raise ValueError("Expected a scalar plug, not an array or compound")
    if cmds.getAttr(result.full_name, type=True) not in {
        "double", "float", "doubleAngle", "doubleLinear", "time",
        "bool", "byte", "char", "short", "long", "enum",
    }:
        raise ValueError("Expected a numeric scalar plug")
    return result


def _sources(plug):
    """単位変換ノードを透過して入力元のPlug名を返す。"""
    return cmds.listConnections(plug, source=True, destination=False,
                                plugs=True, skipConversionNodes=True) or []


def _curves(driven, strict=False):
    """駆動先からblendWeightedの入力を遡り、単位なし入力カーブを集める。"""
    found, visited = [], set()

    def visit(destination):
        """接続を再帰走査する。未知の構成はstrict時に例外とする。"""
        for source in _sources(destination):
            if source in visited:
                continue
            visited.add(source)
            name, attribute = source.split(".", 1)
            kind = cmds.nodeType(name)
            if kind in {"animCurveUA", "animCurveUL", "animCurveUT", "animCurveUU"} and attribute == "output":
                found.append(Node(name))
            elif kind == "blendWeighted" and attribute == "output":
                visit(name + ".input")
            elif strict:
                raise RuntimeError(f"Unsupported driven-key connection: {source}")

    visit(driven.full_name)
    return found


class DrivenKey:
    """1つのドライバーと駆動先の関係。生成だけではシーンを変更しない。

    直接接続・単位変換・blendWeighted経由を対象とする。
    pairBlend、アニメーションレイヤー、任意の計算ノード経由は対象外。
    """

    def __init__(self, driver, driven):
        """既存の数値Plugを保持する。関係が未作成でも取得できる。

        Args:
            driver (Plug | str): ドライバー属性。
            driven (Plug | str): 駆動される属性。
        Raises:
            ValueError: 非スカラー、非数値、または同一属性の場合。
            TypeError: Plugでも属性名でもない場合。
            RuntimeError: 属性が存在しない場合。
        """
        self._driver, self._driven = _plug(driver), _plug(driven)
        if self._driver.full_name == self._driven.full_name:
            raise ValueError("Driver and driven must be different plugs")

    def __repr__(self):
        """str: ドライバーと駆動先の属性名を含む表示。"""
        return f"DrivenKey({self.driver().full_name!r}, {self.driven().full_name!r})"

    def driver(self):
        """Plug: ドライバー。削除済みの場合は例外。"""
        return _plug(self._driver)

    def driven(self):
        """Plug: 駆動先。削除済みの場合は例外。"""
        return _plug(self._driven)

    def curves(self):
        """list[AnimCurve]: この組に対応するカーブ。未作成・対象外の構成なら空。

        接続を毎回照会し、他ドライバーのカーブやblendWeightedのweight入力は含めない。
        """
        driver = self.driver().full_name
        return [curve for curve in _curves(self.driven())
                if any(_plug(source).full_name == driver
                       for source in _sources(curve.full_name + ".input"))]

    def exists(self):
        """bool: 対応するカーブ接続が存在するか。キーが空でもTrue。"""
        return bool(self.curves())

    @undo_chunk("hlibDrivenKeySetKey")
    def set_key(self, driver_value, value, in_tangent="linear", out_tangent="linear"):
        """指定値でキーを追加・更新する。ドライバーの現在値は変更しない。

        Args:
            driver_value (float): 現在のMaya UI単位での入力値。
            value (float): 現在のMaya UI単位での出力値。
            in_tangent (str): Mayaの入力接線型。
            out_tangent (str): Mayaの出力接線型。
        Returns:
            DrivenKey: 自身。
        Raises:
            ValueError: 非有限値の場合。
            RuntimeError: 対象外の接続構成、複数の対応カーブ、またはMayaが設定を拒否した場合。

        複数ドライバーはMaya標準のblendWeightedで合成する。
        pairBlendの自動挿入は行わない。最終出力は他カーブやウェイトにも依存する。
        """
        x, y = float(driver_value), float(value)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Expected finite key values")
        driver, driven = self.driver(), self.driven()
        _curves(driven, strict=True)
        if len(self.curves()) > 1:
            raise RuntimeError("Multiple curves match this driver/driven pair")
        count = cmds.setDrivenKeyframe(driven.full_name, currentDriver=driver.full_name,
                                      driverValue=x, value=y, inTangentType=in_tangent,
                                      outTangentType=out_tangent, insertBlend=False)
        if not count:
            raise RuntimeError("Maya did not set a driven key")
        # 現在値と異なる位置のキー更新後も、駆動先が古い評価値を保持しないようにする。
        cmds.dgdirty([curve.full_name for curve in self.curves()])
        return self


@bulk_api(DrivenKey)
class DrivenKeys(BulkCollection):
    """DrivenKeyの保持順コレクション。同名メソッドを一括実行できる。"""

    def __init__(self, items=()):
        """Iterable[DrivenKey]を保持する。不正要素はTypeError。"""
        self._items = list(items)
        if any(not isinstance(item, DrivenKey) for item in self._items):
            raise TypeError("Expected DrivenKey objects")

    def __iter__(self):
        """Iterator[DrivenKey]: 保持順の要素。"""
        return iter(self._items)

    @classmethod
    def find(cls, driven):
        """駆動先に接続された関係を取得する。シーンは変更しない。

        Args:
            driven (Plug | str): 検索する駆動先属性。
        Returns:
            DrivenKeys: 対応するドライバーごとの関係。対象外の構成は含めない。
        """
        target = _plug(driven)
        items, seen = [], set()
        for curve in _curves(target):
            for source in _sources(curve.full_name + ".input"):
                driver = _plug(source)
                if driver.full_name not in seen:
                    seen.add(driver.full_name)
                    items.append(DrivenKey(driver, target))
        return cls(items)
