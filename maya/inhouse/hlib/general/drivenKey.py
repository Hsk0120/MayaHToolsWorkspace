"""ドライバーPlugと駆動先Plugの組を扱う。"""

import math
import maya.api.OpenMaya as om2
import maya.cmds as cmds

from hlib._core.attributeType import attribute_type
from hlib._core.coerce import to_plug
from hlib.decorators.undo import undo_chunk
from hlib.nodes.node import Node
from hlib.plugs.plug import Plug

#: ドライバー・駆動先に使える数値スカラーの属性型名。
_NUMERIC_SCALAR_TYPES = frozenset(
    (
        "double",
        "float",
        "doubleAngle",
        "doubleLinear",
        "time",
        "bool",
        "byte",
        "char",
        "short",
        "long",
        "enum",
    )
)


def _plug(value):
    """Plug・MPlug・属性名を、数値スカラーのPlugとして検証する。

    文字列は ``to_plug`` で解決するため、``str(plug)`` が返す形式(``grp1|dup.tx``、
    ``bs.weight[0]``、エイリアス名、``cubeShape.pnts[1].pntx`` など)をそのまま渡せる。
    属性が見つからない、または名前が一意でない場合は RuntimeError、属性を指さない
    文字列や対応しない型は TypeError。属性型は属性定義から判定するため
    (:func:`hlib._core.attributeType.attribute_type`)、検証でシーンは変更しない。
    """
    if isinstance(value, (Plug, om2.MPlug)) or (isinstance(value, str) and "." in value):
        result = to_plug(value)
    else:
        raise TypeError("Expected a Plug, MPlug or node.attribute string")
    if not result.is_valid() or not cmds.objExists(result.full_name()):
        raise RuntimeError("Cannot access an invalid plug")
    if result.mplug().isArray or result.mplug().isCompound:
        raise ValueError("Expected a scalar plug, not an array or compound")
    if attribute_type(result.mplug()) not in _NUMERIC_SCALAR_TYPES:
        raise ValueError("Expected a numeric scalar plug")
    return result


def _contains_plug(plugs, mplug):
    """同じプラグ(所有ノード・属性・配列インデックスが一致)が含まれるか判定する。

    インスタンス化されたシェイプの属性は、どのインスタンスのパスから取得しても同じ
    プラグになる。名前(インスタンスのパスを含む ``full_name()``)では比較しない。

    Args:
        plugs (Iterable[om2.MPlug]): 比較対象のプラグ。
        mplug (om2.MPlug): 探すプラグ。

    Returns:
        bool: 同じプラグが含まれる場合は True。
    """
    return any(candidate == mplug for candidate in plugs)


def _sources(plug):
    """単位変換ノードを透過して入力元のPlug名を返す。"""
    return (
        cmds.listConnections(
            plug, source=True, destination=False, plugs=True, skipConversionNodes=True
        )
        or []
    )


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
            if (
                kind in {"animCurveUA", "animCurveUL", "animCurveUT", "animCurveUU"}
                and attribute == "output"
            ):
                found.append(Node(name))
            elif kind == "blendWeighted" and attribute == "output":
                visit(name + ".input")
            elif strict:
                raise RuntimeError(f"Unsupported driven-key connection: {source}")

    visit(driven.full_name())
    return found


class DrivenKey:
    """1つのドライバーと駆動先の関係。生成だけではシーンを変更しない。

    直接接続・単位変換・blendWeighted経由を対象とする。
    pairBlend、アニメーションレイヤー、任意の計算ノード経由は対象外。
    """

    def __init__(self, driver, driven):
        """既存の数値Plugを保持する。関係が未作成でも取得できる。

        Args:
            driver (Plug | om2.MPlug | str): ドライバー属性。文字列は ``"node.attribute"`` 形式。
            driven (Plug | om2.MPlug | str): 駆動される属性。
        Raises:
            ValueError: 非スカラー、非数値、または同一属性の場合。
            TypeError: Plug・MPlug・属性名のいずれでもない場合。
            RuntimeError: 属性が存在しない場合。
        """
        self._driver, self._driven = _plug(driver), _plug(driven)
        if self._driver.mplug() == self._driven.mplug():
            raise ValueError("Driver and driven must be different plugs")

    def __repr__(self):
        """str: ドライバーと駆動先の属性名を含む表示。"""
        return f"DrivenKey({self.driver_plug().full_name()!r}, {self.driven_plug().full_name()!r})"

    def driver_plug(self):
        """Plug: ドライバー。削除済みの場合は例外。"""
        return _plug(self._driver)

    def driven_plug(self):
        """Plug: 駆動先。削除済みの場合は例外。"""
        return _plug(self._driven)

    def curves(self):
        """list[AnimCurve]: この組に対応するカーブ。未作成・対象外の構成なら空。

        接続を毎回照会し、他ドライバーのカーブやblendWeightedのweight入力は含めない。
        ドライバーは名前ではなくプラグ自体で照合するため、インスタンス化されたシェイプの
        属性をどのインスタンスのパスから指定しても同じ関係として扱う。
        """
        driver = self.driver_plug().mplug()
        return [
            curve
            for curve in _curves(self.driven_plug())
            if _contains_plug(
                (to_plug(source).mplug() for source in _sources(curve.full_name() + ".input")),
                driver,
            )
        ]

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
        driver, driven = self.driver_plug(), self.driven_plug()
        _curves(driven, strict=True)
        if len(self.curves()) > 1:
            raise RuntimeError("Multiple curves match this driver/driven pair")
        count = cmds.setDrivenKeyframe(
            driven.full_name(),
            currentDriver=driver.full_name(),
            driverValue=x,
            value=y,
            inTangentType=in_tangent,
            outTangentType=out_tangent,
            insertBlend=False,
        )
        if not count:
            raise RuntimeError("Maya did not set a driven key")
        # 現在値と異なる位置のキー更新後も、駆動先が古い評価値を保持しないようにする。
        cmds.dgdirty([curve.full_name() for curve in self.curves()])
        return self
