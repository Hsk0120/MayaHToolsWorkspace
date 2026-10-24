"""ドライバーPlugと駆動先Plugの組を扱う。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import attributeType
from ..decorator import undoChunk
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
    (:func:`mlib.core.attributeType.attributeType`)、検証でシーンは変更しない。

    Args:
        value (Plug | om2.MPlug | str): 数値スカラーのPlugまたはアトリビュート名。

    Returns:
        Plug: 有効な数値スカラーのアトリビュート参照。
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
    """単位変換ノードを透過し、配列要素も含めた入力元Plugを返す。

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
                raise RuntimeError(f"Unsupported driven-key connection: {source.getFullName()}")

    visit(driven)
    return found


class DrivenKey:
    """数値スカラーのドライバーPlugと駆動先Plugを保持し、ドリブンキーの関係を扱う。

    生成時は二つの参照を検証するだけで、カーブや接続を作らない。
    接続は問い合わせの都度調べ、単位変換ノードとblendWeightedのinput経由を辿る。
    pairBlend、アニメーションレイヤー、任意の計算ノードを辿る汎用探索ではない。

    setKeyの数値は各アトリビュートの内部単位で受け取り、Mayaコマンド境界で
    UI単位へ変換する。AnimCurveのU型カーブに渡す無次元入力と混同しない。
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

    @undoChunk("mlibDrivenKeySetKey")
    def setKey(self, driver_value, value, inTangentType="linear", outTangentType="linear"):
        """指定したドライバー値と駆動先値でドリブンキーを追加・更新する。

        両値をfloat()で有限性検査し、それぞれのPlug定義に従って内部単位から
        UI単位へ変換してsetDrivenKeyframeを呼ぶ。ドライバーの現在値やシーン時刻は
        変更しない。作成後は対応カーブをdgdirtyで汚し、駆動先の再評価を促す。

        fast引数やOpenMaya更新は提供しない。Undo有効時は一回のチャンクにまとめる。
        呼出元のfast指定には影響されず、Undo設定は変更しない。

        Args:
            driver_value (float): ドライバーの内部単位の値。角度rad、距離cm、時間秒、その他は無次元。
            value (float): 駆動先の内部単位の値。単位はdriver_valueと独立に解釈する。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。

        Returns:
            DrivenKey: 自身。

        Raises:
            ValueError: 数値が非有限、またはfloat()で変換できない場合。
            TypeError: 数値の型がfloat()へ変換できない場合。
            RuntimeError: 対象外の入力接続、同じ組に複数のカーブがある、
                またはMayaがキー作成を拒否した場合。

        複数ドライバーの合成にはMaya標準のblendWeightedを使い、pairBlendの
        自動挿入は行わない。最終出力は他カーブや合成ウェイトにも依存する。
        後続の失敗に対する自動ロールバックは行わない。
        """
        from ..core.attributeType import _convert_units
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
