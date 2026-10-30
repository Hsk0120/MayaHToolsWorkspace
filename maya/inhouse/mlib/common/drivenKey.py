"""ドライバーPlugと駆動先Plugの組を扱う。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import _convert_angles, _convert_times, _convert_units, attributeType
from ..core.fastWrite import require_writable
from ..decorator import _edit_context
from ..nodes.animCurve import AnimCurve
from ..nodes.node import Node
from ..plugs.plug import Plug
from ..util import _angle_unit, _time_unit

#: fastで新しく作るカーブの型。駆動先のアトリビュート型から選ぶ(setDrivenKeyframeと同じ。他はanimCurveUU)。
_CURVE_TYPES = {"doubleLinear": "animCurveUL", "doubleAngle": "animCurveUA", "time": "animCurveUT"}

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
    (:func:`mlib.core.attributeType.attributeType`)、検証でシーンは変更しない。

    Args:
        value (Plug | om2.MPlug | str): 数値スカラーのPlugまたはアトリビュート名。

    Returns:
        Plug: 有効な数値スカラーのアトリビュート参照。
    """
    if isinstance(value, (Plug, om2.MPlug)) or (isinstance(value, str) and "." in value):
        result = Plug._resolve_input(value)
    else:
        raise TypeError("Expected a Plug, MPlug or node.attribute string")
    # Plug.isValidは所有ノードとアトリビュート(deleteAttrで消えた動的アトリビュートを含む)の存在を確かめる。
    if not result.isValid():
        raise RuntimeError("Cannot access an invalid plug")
    if result.mplug().isArray or result.mplug().isCompound:
        raise ValueError("Expected a scalar plug, not a multi attribute or compound attribute")
    if attributeType(result.mplug()) not in _NUMERIC_SCALAR_TYPES:
        raise ValueError("Expected a numeric scalar plug")
    return result


def _contains_plug(plugs, mplug):
    """同じプラグ(所有ノード・アトリビュート・論理番号が一致)が含まれるか判定する。

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
    """単位変換ノードを透過し、マルチアトリビュートの要素も含めた入力元Plugを返す。

    Args:
        plug (Plug | str): 接続元を調べるアトリビュート。

    Returns:
        list[Plug]: 単位変換ノードを透過した接続元。未接続なら空。
    """
    return Plug._resolve_input(plug).getConnections(
        source=True, destination=False, skipConversionNodes=True)


def _curves(driven, strict=False):
    """駆動先からblendWeightedの入力を遡り、単位なし入力カーブを集める。

    Args:
        driven (Plug): ドリブンキーで駆動するアトリビュート。
        strict (bool): 未対応の接続構造を例外として扱うか。

    Returns:
        list[AnimCurve]: 駆動先の入力へつながる単位なし入力のカーブ。重複を含めない。
    """
    found, visited = [], []

    def visit(destination):
        """接続を再帰走査する。未知の構成はstrict時に例外とする。

        Args:
            destination (Plug): 接続元を調べるアトリビュート。

        Returns:
            None: 値を返さない。
        """
        for source in _sources(destination):
            if _contains_plug(visited, source.mplug()):
                continue
            visited.append(source.mplug())
            node = source.getNode()
            attribute, kind = source.getLongName(), node.getType()
            if (
                kind in {"animCurveUA", "animCurveUL", "animCurveUT", "animCurveUU"}
                and attribute == "output"
            ):
                found.append(node)
            elif kind == "blendWeighted" and attribute == "output":
                visit(node.getPlug("input"))
            elif strict:
                raise RuntimeError(
                    f"Cannot set a driven key on {driven.getFullName()}: {destination.getFullName()} already has "
                    f"an input from {source.getFullName()} ({kind}), which is not a driven-key curve; "
                    "disconnect it first (e.g. plug.disconnectInput()), or combine both inputs through a "
                    "blendWeighted node")

    visit(driven)
    return found


class DrivenKey:
    """数値スカラーのドライバーPlugと駆動先Plugを保持し、ドリブンキーの関係を扱う。

    生成時は二つの参照を検証するだけで、カーブや接続を作らない。
    接続は問い合わせの都度調べ、単位変換ノードとblendWeightedのinput経由を辿る。
    pairBlend、アニメーションレイヤー、任意の計算ノードを辿る汎用探索ではない。

    setKeyの数値は、角度アトリビュートでは既定で度(``unit="rad"`` でラジアン)、距離はcm、
    時間アトリビュートでは既定で現在のUI時間単位のフレーム(``timeUnit="sec"`` で秒)で受け取り、
    Mayaコマンド境界でUI単位へ変換する。
    AnimCurveのU型カーブに渡す無次元入力と混同しない。
    """

    def __init__(self, driver, driven):
        """既存の数値Plugを保持する。関係が未作成でも取得できる。

        Args:
            driver (Plug | om2.MPlug | str): ドライバーアトリビュート。文字列は ``"node.attribute"`` 形式。
            driven (Plug | om2.MPlug | str): 駆動されるアトリビュート。

        Raises:
            TypeError: Plug・MPlug・アトリビュート名のいずれでもない場合。
            ValueError: 非スカラー、非数値、または同一アトリビュートの場合。
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
            TypeError: driven が Plug・MPlug・アトリビュート名のいずれでもない場合。
            ValueError: driven が非スカラー・非数値の場合。
            RuntimeError: driven のアトリビュートが存在しない場合。
        """
        target = _plug(driven)
        items, seen = [], []
        for curve in _curves(target):
            for source in _sources(curve.getPlug("input")):
                try:
                    driver = _plug(source)
                except ValueError:
                    continue  # 数値スカラーでないドライバーは DrivenKey の対象外。
                if not _contains_plug(seen, driver.mplug()):
                    seen.append(driver.mplug())
                    items.append(cls(driver, target))
        return items

    def getDriverPlug(self):
        """保持したドライバーアトリビュートを再検証してPlug参照を取得する。

        Returns:
            Plug: 同じアトリビュートへの参照。現在値の取得やコピーは行わない。

        Raises:
            RuntimeError: 削除などでアトリビュートを参照できない場合。
        """
        return _plug(self._driver)

    def getDrivenPlug(self):
        """保持した駆動先アトリビュートを再検証してPlug参照を取得する。

        Returns:
            Plug: 同じアトリビュートへの参照。現在値の取得やコピーは行わない。

        Raises:
            RuntimeError: 削除などでアトリビュートを参照できない場合。
        """
        return _plug(self._driven)

    def getCurves(self):
        """このドライバーと駆動先の組に対応するカーブを照会する。

        接続を毎回照会し、他ドライバーのカーブやblendWeightedのweight入力は含めない。
        ドライバーは名前ではなくプラグ自体で照合するため、インスタンス化されたシェイプの
        アトリビュートをどのインスタンスのパスから指定しても同じ関係として扱う。

        Returns:
            list[AnimCurve]: この組に対応するカーブ。未作成・対象外の構成なら空。
        """
        driver = self.getDriverPlug().mplug()
        return [
            curve
            for curve in _curves(self.getDrivenPlug())
            if _contains_plug(
                (source.mplug() for source in _sources(curve.getPlug("input"))),
                driver,
            )
        ]

    def exists(self):
        """対応するカーブ接続が存在するか。キーが空でもTrue。

        Returns:
            bool: 対応するカーブ接続が存在するか。キーが空でもTrue。
        """
        return bool(self.getCurves())

    def setKey(self, driverValue, value, inTangentType="linear", outTangentType="linear", *, unit="deg",
               timeUnit="frame", fast=False):
        """指定したドライバー値と駆動先値でドリブンキーを追加・更新する。

        両値をfloat()で有限性検査し、それぞれのPlug定義に従ってUI単位へ変換して
        setDrivenKeyframeを呼ぶ。ドライバーの現在値やシーン時刻は
        変更しない。作成後は対応カーブをdgdirtyで汚し、駆動先の再評価を促す。
        Undo有効時は一回のチャンクにまとめる。

        ``fast=True`` はUndoに記録せず、OpenMayaで更新する。この組のカーブがあれば
        :meth:`AnimCurve.setKey <mlib.nodes.animCurve.AnimCurve.setKey>` のfastでキーを追加・更新する。
        無ければsetDrivenKeyframeと同じ型(駆動先が距離ならanimCurveUL、角度ならanimCurveUA、
        時間ならanimCurveUT、他はanimCurveUU)・名前(名前空間を除いた ``<駆動先ノード>_<アトリビュート>``。
        エイリアスがあればエイリアス)のカーブを作り、
        ドライバー→カーブ→駆動先へ接続する(単位の違う接続にはMayaがunitConversionを挟む)。

        Args:
            driverValue (float): ドライバーの値。角度はunitの単位(既定は度)、距離cm、
                時間はtimeUnitの単位(既定はフレーム)、その他は無次元。
            value (float): 駆動先の値。単位はdriverValueと独立に、駆動先のアトリビュート定義で解釈する。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。
            unit (str): 角度アトリビュートの値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` / ``"radians"`` 等の別名も可)。角度以外のアトリビュートでは使わない。
            timeUnit (str): 時間アトリビュートの値の単位。既定 ``"frame"`` は現在のUI時間単位のフレーム、
                ``"sec"`` は秒(``"seconds"`` 等の別名も可)。時間以外のアトリビュートでは使わない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DrivenKey: 自身。

        Raises:
            TypeError: 数値の型がfloat()へ変換できない、unit・timeUnitが文字列以外、またはfastがbool以外の場合。
            ValueError: 数値が非有限、float()で変換できない、unit・timeUnitが未対応の単位名、
                またはfastでfixed・global等の直接設定できない接線型を指定した場合。
            RuntimeError: 対象外の入力接続、同じ組に複数のカーブがある、駆動先がロックされている、
                またはMayaがキー作成を拒否した場合。
            NotImplementedError: fastで、この組のカーブが無く駆動先に別のドライバーのカーブが既に
                つながっている場合(MayaはblendWeightedを挟む)、または入力接線にstepnextを指定した場合。
                いずれも変更前に拒否する。

        Note:
            複数ドライバーの合成にはMaya標準のblendWeightedを使い、pairBlendの
            自動挿入は行わない。最終出力は他カーブや合成ウェイトにも依存する。
            後続の失敗に対する自動ロールバックは行わない。
        """
        with _edit_context("mlibDrivenKeySetKey", fast):
            angle_unit = _angle_unit(unit)
            time_unit = _time_unit(timeUnit)
            x, y = float(driverValue), float(value)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Expected finite key values")
            driver, driven = self.getDriverPlug(), self.getDrivenPlug()
            # 角度・時間の値を内部単位(rad・秒)へ揃えてから、Mayaコマンドが受け取るUI単位へ換算する。
            x = _convert_times(driver.mplug(), _convert_angles(driver.mplug(), x, angle_unit), time_unit)
            _curves(driven, strict=True)
            curves = self.getCurves()
            if len(curves) > 1:
                raise RuntimeError("Multiple curves match this driver/driven pair")
            if fast:
                # カーブの横軸はドライバーのUI単位(unitConversion経由の値)。縦軸はAnimCurve.setKeyが換算する。
                self._set_key_fast(curves, _convert_units(driver.mplug(), x), y, inTangentType, outTangentType,
                                   unit, timeUnit)
                return self
            y = _convert_times(driven.mplug(), _convert_angles(driven.mplug(), y, angle_unit), time_unit)
            count = cmds.setDrivenKeyframe(
                driven.getFullName(),
                currentDriver=driver.getFullName(),
                driverValue=_convert_units(driver.mplug(), x),
                value=_convert_units(driven.mplug(), y),
                inTangentType=inTangentType,
                outTangentType=outTangentType,
                insertBlend=False,
            )
            if not count:
                raise RuntimeError("Maya did not set a driven key")
            # 現在値と異なる位置のキー更新後も、駆動先が古い評価値を保持しないようにする。
            cmds.dgdirty([curve.getFullName() for curve in self.getCurves()])
            return self

    def _set_key_fast(self, curves, input, value, inTangentType, outTangentType, unit, timeUnit):
        """:meth:`setKey` のfast経路。必要ならカーブを作って接続し、OpenMayaでキーを書く。

        Args:
            curves (list[AnimCurve]): この組のカーブ(0個か1個)。
            input (float): カーブの横軸の値(ドライバーのUI単位)。
            value (float): 駆動先の値。:meth:`setKey` のvalueと同じ単位。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。
            unit (str): 角度の値の単位。
            timeUnit (str): 時間の値の単位。

        Returns:
            None: 値を返さない。
        """
        # カーブを作る前に接線型を検証し、未対応の指定でノードを残さない。
        AnimCurve._tangent_type(inTangentType, incoming=True, key=True)
        AnimCurve._tangent_type(outTangentType, key=True)
        if curves:
            curve = curves[0]
        else:
            driver, driven = self.getDriverPlug(), self.getDrivenPlug()
            if _sources(driven):
                raise NotImplementedError("fast setKey does not support a second driver on "
                                          f"{driven.getFullName()} (Maya inserts a blendWeighted node)")
            require_writable(driven.mplug())
            kind = _CURVE_TYPES.get(attributeType(driven.mplug()), "animCurveUU")
            # setDrivenKeyframeと同じく、名前空間を除いたノード名とエイリアス(無ければロング名)を使う。
            attribute = driven.mplug().partialName(useAlias=True, useLongNames=True)
            name = driven.getNode().getName().rpartition("|")[2].rpartition(":")[2] + "_" + attribute
            for character in "[].":
                name = name.replace(character, "_")
            curve = Node._create_node(kind, {"name": name.rstrip("_"), "skipSelect": True}, fast=True)
            curve.getPlug("input").connect(driver, fast=True)
            driven.connect(curve.getPlug("output"), fast=True)
        curve.setKey(input, value, inTangentType, outTangentType, unit=unit, timeUnit=timeUnit, fast=True)
