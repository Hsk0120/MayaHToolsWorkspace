"""複数のウェイトの組み合わせ(コンボ)と途中(インビトウィーン)のウェイトを、標準DGで求める。"""

import math
import re

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 組み合わせの求め方。``multiply`` は積、``lowest`` は最も小さい値。
METHODS = ("multiply", "lowest")

#: container が自分で使うアトリビュート名。ドライバー・出力の名前には使えない。
_RESERVED = ("comboMethod", "driverNames", "outputNames")

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _clamp(value):
    return min(max(float(value), 0.0), 1.0)


class ComboWeight(TwistDistribution):
    """補正シェイプ・補助骨を動かすための、組み合わせと途中のウェイトを持つ container 所有の標準DG。

    元のウェイト(ドライバー)は ``0`` 〜 ``1`` に切り詰めてから使う。
    組み合わせのウェイトは、含むドライバーがすべて動いたときだけ大きくなる値で、
    ``multiply`` なら積 ``w = a * b * ...`` 、 ``lowest`` なら最小 ``w = min(a, b, ...)`` 。
    左右を同時に動かしたときだけ足す補正シェイプ(左右それぞれのシェイプを足すと崩れる分を直す)などに使う。
    途中のウェイトは、1つのドライバー ``x`` が位置 ``p`` (0と1の間)で 1 、0と1で 0 になる山形の値で、
    ``w = min(x / p, (1 - x) / (1 - p))`` 。ブレンドシェイプのインビトウィーンと同じ時点で
    別の補正や補助骨を動かすときに使う。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def evaluate(cls, values, combos=None, inbetweens=None, method="multiply"):
        """組み合わせと途中のウェイトを計算する(DGと同じ式のPython版)。

        Args:
            values (dict[str, float]): ドライバー名と値。
            combos (dict[str, list[str]] | None): 組み合わせの名前と、含むドライバー名の並び。
            inbetweens (dict[str, tuple[str, float]] | None): 途中のウェイトの名前と(ドライバー名, 位置)。
            method (str): ``"multiply"`` または ``"lowest"`` 。

        Returns:
            dict[str, float]: 組み合わせと途中のウェイトの名前と値。
        """
        result = {}
        for combo, names in (combos or {}).items():
            weights = [_clamp(values[item]) for item in names]
            if method == "lowest":
                result[combo] = min(weights)
            else:
                product = 1.0
                for weight in weights:
                    product *= weight
                result[combo] = product
        for item, (driver, position) in (inbetweens or {}).items():
            weight = _clamp(values[driver])
            result[item] = min(weight / position, (1.0 - weight) / (1.0 - position))
        return result

    @classmethod
    @undoTransaction("mlrig.ComboWeight.create")
    def create(cls, drivers, combos=None, inbetweens=None, method="multiply", name="comboWeight"):
        """組み合わせと途中のウェイトの計算containerを作る。

        Args:
            drivers (list[str] | dict[str, str | Plug | None]): ドライバー名の並び、または
                ドライバー名と入力のアトリビュート(``"node.attr"`` やPlug)の対応。入力がNoneの名前と、
                並びで渡した名前は、container の keyable なアトリビュート(既定0)を直接動かす。
            combos (dict[str, list[str]] | None): 組み合わせの名前と、含むドライバー名(2個以上、重複なし)。
            inbetweens (dict[str, tuple[str, float]] | None): 途中のウェイトの名前と(ドライバー名, 位置)。
                位置は 0 より大きく 1 より小さい。
            method (str): 組み合わせの求め方。 ``"multiply"`` (積)または ``"lowest"`` (最小)。
            name (str): 一意なcontainer名。

        Returns:
            ComboWeight: container にドライバー名のアトリビュート(入力)と、組み合わせ・途中のウェイトの
                名前のアトリビュート(出力、keyableでない)を持つ。出力をブレンドシェイプのウェイトや
                補助骨の値へ接続して使う。

        Raises:
            ValueError: 名前が不正・重複している場合、組み合わせや途中のウェイトが未知のドライバーを
                含む場合、位置や method が不正な場合、入力のアトリビュートが無い場合、
                またはnameが既に存在する場合。
        """
        if not isinstance(drivers, dict):
            drivers = dict((item, None) for item in drivers)
        combos = dict(combos or {})
        inbetweens = dict(inbetweens or {})
        if method not in METHODS:
            raise ValueError("method must be one of: " + ", ".join(METHODS))
        if not drivers:
            raise ValueError("drivers must not be empty")
        if not combos and not inbetweens:
            raise ValueError("combos or inbetweens must be given")
        names = list(drivers) + list(combos) + list(inbetweens)
        for item in names:
            if not isinstance(item, str) or not _NAME.match(item) or item in _RESERVED:
                raise ValueError("invalid attribute name: " + repr(item))
        if len(set(names)) != len(names):
            raise ValueError("driver, combo and inbetween names must be unique")
        for combo, members in combos.items():
            members = list(members)
            if len(members) < 2 or len(set(members)) != len(members):
                raise ValueError("combo needs two or more different drivers: " + combo)
            for member in members:
                if member not in drivers:
                    raise ValueError("unknown driver in combo {}: {}".format(combo, member))
            combos[combo] = members
        for item, pair in inbetweens.items():
            driver, position = pair
            if driver not in drivers:
                raise ValueError("unknown driver in inbetween {}: {}".format(item, driver))
            if not math.isfinite(float(position)) or not 0.0 < float(position) < 1.0:
                raise ValueError("inbetween position must be between 0 and 1: " + item)
            inbetweens[item] = (driver, float(position))
        sources = {}
        for driver, source in drivers.items():
            if source is not None:
                text = str(source)
                if not mlib.ls(text):
                    raise ValueError("driver source does not exist: " + text)
                sources[driver] = text
        if mlib.ls(name):
            raise ValueError("ComboWeight container already exists: " + name)
        graph = cls(mlib.nodes.Container.create(name=name))
        graph._build(list(drivers), sources, combos, inbetweens, method)
        return graph

    def _build(self, drivers, sources, combos, inbetweens, method):
        """createの本体。

        Args:
            drivers (list[str]): ドライバー名。
            sources (dict[str, str]): ドライバー名と入力のアトリビュート。
            combos (dict[str, list[str]]): 組み合わせ。
            inbetweens (dict[str, tuple[str, float]]): 途中のウェイト。
            method (str): 組み合わせの求め方。
        """
        owner = self.container
        owner.addAttr(longName="comboMethod", attributeType="enum", enumName=":".join(METHODS))
        owner.getPlug("comboMethod").set(METHODS.index(method))
        for attribute, items in (("driverNames", drivers), ("outputNames", list(combos) + list(inbetweens))):
            owner.addAttr(longName=attribute, dataType="string")
            owner.getPlug(attribute).set(" ".join(items))
        clamped = {}
        for driver in drivers:
            owner.addAttr(longName=driver, attributeType="double", defaultValue=0.0, keyable=True)
            if driver in sources:
                mlib.getPlug(sources[driver]).connectTo(owner.getPlug(driver))
            # 0〜1 に切り詰める(clamp は単精度)。
            limit = self._node("clamp", driver + "Clamp")
            limit.getPlug("maxR").set(1.0)
            owner.getPlug(driver).connectTo(limit.getPlug("inputR"))
            clamped[driver] = limit.getPlug("outputR")
        outputs = list(combos) + list(inbetweens)
        for item in outputs:
            owner.addAttr(longName=item, attributeType="double")

        for combo, members in combos.items():
            value = clamped[members[0]]
            for index, member in enumerate(members[1:]):
                suffix = "{}Step{}".format(combo, index)
                if method == "multiply":
                    # value * member(倍精度の animBlendNodeAdditive の inputA * weightA)。
                    step = self._node("animBlendNodeAdditive", suffix)
                    value.connectTo(step.getPlug("inputA"))
                    clamped[member].connectTo(step.getPlug("weightA"))
                    step.getPlug("weightB").set(0.0)
                    value = step.getPlug("output")
                else:
                    value = self._lower(value, clamped[member], suffix)
            value.connectTo(owner.getPlug(combo))

        for item, (driver, position) in inbetweens.items():
            # 上り x / p と下り (1 - x) / (1 - p) の小さい方。
            rise = self._node("animBlendNodeAdditive", item + "Rise")
            clamped[driver].connectTo(rise.getPlug("inputA"))
            rise.getPlug("weightA").set(1.0 / position)
            rise.getPlug("weightB").set(0.0)
            fall = self._node("animBlendNodeAdditive", item + "Fall")
            clamped[driver].connectTo(fall.getPlug("inputA"))
            fall.getPlug("weightA").set(-1.0 / (1.0 - position))
            fall.getPlug("inputB").set(1.0)
            fall.getPlug("weightB").set(1.0 / (1.0 - position))
            self._lower(rise.getPlug("output"), fall.getPlug("output"), item + "Lower").connectTo(
                owner.getPlug(item))
        owner.setAttrFlags(["comboMethod"] + outputs, keyable=False)

    def _lower(self, first, second, suffix):
        """2つの値の小さい方を condition で求める。

        Args:
            first (Plug): 1つ目の値。
            second (Plug): 2つ目の値。
            suffix (str): ノード名の接尾辞。

        Returns:
            Plug: 小さい方の値(condition の outColorR、単精度)。
        """
        lower = self._node("condition", suffix)
        lower.getPlug("operation").set(4)
        first.connectTo(lower.getPlug("firstTerm"))
        second.connectTo(lower.getPlug("secondTerm"))
        first.connectTo(lower.getPlug("colorIfTrueR"))
        second.connectTo(lower.getPlug("colorIfFalseR"))
        return lower.getPlug("outColorR")

    def getDrivers(self):
        """ドライバー名を作成時の順で返す。

        Returns:
            list[str]: container の入力のアトリビュート名。
        """
        return str(self.container.getPlug("driverNames").get() or "").split()

    def getOutputs(self):
        """組み合わせと途中のウェイトの名前を作成時の順で返す。

        Returns:
            list[str]: container の出力のアトリビュート名(組み合わせが先、途中のウェイトが後)。
        """
        return str(self.container.getPlug("outputNames").get() or "").split()
