"""ドライバーPlugと駆動先Plugの組を扱う。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.attributeType import attributeType
from ..decorators.undo import undoChunk
from ..nodes.node import Node
from ..plugs.plug import Plug

#: ドライバー・駆動先に使える数値スカラーのアトリビュート型名。
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
    """Plug・MPlug・アトリビュート名を、数値スカラーのPlugとして検証する。

    文字列は Plug の入力解決を使うため、``str(plug)`` が返す形式(``grp1|dup.tx``、
    ``bs.weight[0]``、エイリアス名、``cubeShape.pnts[1].pntx`` など)をそのまま渡せる。
    アトリビュートが見つからない、または名前が一意でない場合は RuntimeError、アトリビュートを指さない
    文字列や対応しない型は TypeError。アトリビュート型はアトリビュート定義から判定するため
    (:func:`hlib._core.attributeType.attributeType`)、検証でシーンは変更しない。

    Args:
        value: 変換・設定する入力値。
    """
    from ..plugs.plug import Plug as _InputPlug
    if isinstance(value, (Plug, om2.MPlug)) or (isinstance(value, str) and "." in value):
        result = _InputPlug._resolve_input(value)
    else:
        raise TypeError("Expected a Plug, MPlug or node.attribute string")
    if not result.isValid() or not cmds.objExists(result.getFullName()):
        raise RuntimeError("Cannot access an invalid plug")
    if result.mplug().isArray or result.mplug().isCompound:
        raise ValueError("Expected a scalar plug, not an array or compound")
    if attributeType(result.mplug()) not in _NUMERIC_SCALAR_TYPES:
        raise ValueError("Expected a numeric scalar plug")
    return result


def _contains_plug(plugs, mplug):
    """同じプラグ(所有ノード・アトリビュート・配列インデックスが一致)が含まれるか判定する。

    インスタンス化されたシェイプのアトリビュートは、どのインスタンスのパスから取得しても同じ
    プラグになる。名前(インスタンスのパスを含む ``getFullName()``)では比較しない。

    Args:
        plugs (Iterable[om2.MPlug]): 比較対象のプラグ。
        mplug (om2.MPlug): 探すプラグ。

    Returns:
        bool: 同じプラグが含まれる場合は True。
    """
    return any(candidate == mplug for candidate in plugs)


def _sources(plug):
    """単位変換ノードを透過して入力元のPlug名を返す。

    Args:
        plug: 照会または更新するアトリビュート参照。
    """
    return (
        cmds.listConnections(
            plug, source=True, destination=False, plugs=True, skipConversionNodes=True
        )
        or []
    )


def _curves(driven, strict=False):
    """駆動先からblendWeightedの入力を遡り、単位なし入力カーブを集める。

    Args:
        driven: ドリブンキーの出力先。
        strict: 未対応の構造を例外として扱うか。
    """
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

    visit(driven.getFullName())
    return found


class DrivenKey:
    """1つのドライバーと駆動先の関係。生成だけではシーンを変更しない。

    直接接続・単位変換・blendWeighted経由を対象とする。
    pairBlend、アニメーションレイヤー、任意の計算ノード経由は対象外。
    """

    def __init__(self, driver, driven):
        """既存の数値Plugを保持する。関係が未作成でも取得できる。

        Args:
            driver (Plug | om2.MPlug | str): ドライバーアトリビュート。文字列は ``"node.attribute"`` 形式。
            driven (Plug | om2.MPlug | str): 駆動されるアトリビュート。
        Raises:
            ValueError: 非スカラー、非数値、または同一アトリビュートの場合。
            TypeError: Plug・MPlug・アトリビュート名のいずれでもない場合。
            RuntimeError: アトリビュートが存在しない場合。
        """
        self._driver, self._driven = _plug(driver), _plug(driven)
        if self._driver.mplug() == self._driven.mplug():
            raise ValueError("Driver and driven must be different plugs")

    def __repr__(self):
        """ドライバーと駆動先のアトリビュート名を含む表示。

        Returns:
            str: ドライバーと駆動先のアトリビュート名を含む表示。
        """
        return f"DrivenKey({self.getDriverPlug().getFullName()!r}, {self.getDrivenPlug().getFullName()!r})"

    @classmethod
    def find(cls, driven):
        """駆動先に接続された関係を取得する。シーンは変更しない。

        Args:
            driven (Plug | om2.MPlug | str): 検索する駆動先アトリビュート。文字列は ``"node.attribute"`` 形式。
        Returns:
            list[DrivenKey]: 対応するドライバーごとの関係。対象外の構成は含めない
                (数値スカラーでないドライバー。``choice.output`` のような値によって型が
                変わる generic アトリビュートなど)。同じドライバー(プラグ自体で照合する)は1件にまとめる。
        Raises:
            ValueError: driven が非スカラー・非数値の場合。
            TypeError: driven が Plug・MPlug・アトリビュート名のいずれでもない場合。
            RuntimeError: driven のアトリビュートが存在しない場合。
        """
        target = _plug(driven)
        items, seen = [], []
        for curve in _curves(target):
            for source in _sources(curve.getFullName() + ".input"):
                try:
                    driver = _plug(source)
                except ValueError:
                    continue  # 数値スカラーでないドライバーは DrivenKey の対象外。
                if not _contains_plug(seen, driver.mplug()):
                    seen.append(driver.mplug())
                    items.append(cls(driver, target))
        return items

    def getDriverPlug(self):
        """ドライバー。削除済みの場合は例外。

        Returns:
            Plug: ドライバー。削除済みの場合は例外。
        """
        return _plug(self._driver)

    def getDrivenPlug(self):
        """駆動先。削除済みの場合は例外。

        Returns:
            Plug: 駆動先。削除済みの場合は例外。
        """
        return _plug(self._driven)

    def getCurves(self):
        """list[AnimCurve]: この組に対応するカーブ。未作成・対象外の構成なら空。

        接続を毎回照会し、他ドライバーのカーブやblendWeightedのweight入力は含めない。
        ドライバーは名前ではなくプラグ自体で照合するため、インスタンス化されたシェイプの
        アトリビュートをどのインスタンスのパスから指定しても同じ関係として扱う。
        """
        from ..plugs.plug import Plug as _InputPlug
        driver = self.getDriverPlug().mplug()
        return [
            curve
            for curve in _curves(self.getDrivenPlug())
            if _contains_plug(
                (_InputPlug._resolve_input(source).mplug() for source in _sources(curve.getFullName() + ".input")),
                driver,
            )
        ]

    def exists(self):
        """対応するカーブ接続が存在するか。キーが空でもTrue。

        Returns:
            bool: 対応するカーブ接続が存在するか。キーが空でもTrue。
        """
        return bool(self.getCurves())

    @undoChunk("hlibDrivenKeySetKey")
    def setKey(self, driver_value, value, inTangentType="linear", outTangentType="linear"):
        """指定値でキーを追加・更新する。ドライバーの現在値は変更しない。

        Args:
            driver_value (float): 内部単位(cm/rad/秒)での入力値。
            value (float): 内部単位(cm/rad/秒)での出力値。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。
        Returns:
            DrivenKey: 自身。
        Raises:
            ValueError: 非有限値の場合。
            RuntimeError: 対象外の接続構成、複数の対応カーブ、またはMayaが設定を拒否した場合。

        複数ドライバーはMaya標準のblendWeightedで合成する。
        pairBlendの自動挿入は行わない。最終出力は他カーブやウェイトにも依存する。
        """
        from .._core.unitValue import convert
        x, y = float(driver_value), float(value)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Expected finite key values")
        driver, driven = self.getDriverPlug(), self.getDrivenPlug()
        _curves(driven, strict=True)
        if len(self.getCurves()) > 1:
            raise RuntimeError("Multiple curves match this driver/driven pair")
        count = cmds.setDrivenKeyframe(
            driven.getFullName(),
            currentDriver=driver.getFullName(),
            driverValue=convert(driver.mplug(), x),
            value=convert(driven.mplug(), y),
            inTangentType=inTangentType,
            outTangentType=outTangentType,
            insertBlend=False,
        )
        if not count:
            raise RuntimeError("Maya did not set a driven key")
        # 現在値と異なる位置のキー更新後も、駆動先が古い評価値を保持しないようにする。
        cmds.dgdirty([curve.getFullName() for curve in self.getCurves()])
        return self
