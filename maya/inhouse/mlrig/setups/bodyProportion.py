"""体格を決める少数のパラメーターから、体格調整用の骨の移動・スケールを標準DGで作る。"""

import math
import re

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: パラメーター名に使える形(アトリビュート名として安全な英数字)。
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

#: 骨ごとの量の種類。``Negative`` は値が負のときに使う量。
_ROLES = ("translate", "translateNegative", "scale", "scaleNegative")


class BodyProportion(TwistDistribution):
    """「腕の長さ」「肩幅」「上腕の太さ」のような体格のパラメーターで、標準の体格の骨を変形する一般的な仕組み。

    衣装やモデルを全員共通の標準の体格で作り、体格調整用の骨の移動・スケールだけをパラメーターで変えて
    個別の体格を作る。パラメーターごとに下限・上限(clamp)と、値が1(負の側は-1)のときの骨ごとの
    移動量・スケールの変化量を持ち、骨ごとの値は

    ``translate = 生成時の移動 + Σ (正の値 * translate量 + 負の値の大きさ * translateNegative量)``

    ``scale = 生成時のスケール + Σ (正の値 * scale量 + 負の値の大きさ * scaleNegative量)``

    とする(正の値 = clamp(値, 0, 上限)、負の値の大きさ = -clamp(値, 下限, 0))。正負で別の量を持てるので、
    太くする向きと細くする向きで形を変えられる。全てのパラメーターが0なら骨は生成時のまま。
    回転は扱わない(足し算で混ぜると軸の順番に依存するため)。
    """

    @staticmethod
    def evaluate(rest, values, amounts):
        """1つの骨の移動またはスケールを計算する(DGと同じ式のPython版)。

        Args:
            rest (Sequence[float]): 生成時の値(XYZ)。
            values (Sequence[tuple[float, float, float]]): パラメーターごとの (値, 下限, 上限)。
            amounts (Sequence[tuple[Sequence[float], Sequence[float]]]): パラメーターごとの
                (値が1のときの変化量, 値が-1のときの変化量)。

        Returns:
            tuple[float, float, float]: 計算した値。
        """
        result = list(rest)
        for (value, minimum, maximum), (positive, negative) in zip(values, amounts):
            clamped = min(max(value, minimum), maximum)
            for axis in range(3):
                if clamped >= 0.0:
                    result[axis] += clamped * positive[axis]
                else:
                    result[axis] += -clamped * negative[axis]
        return tuple(result)

    @classmethod
    def _parse(cls, parameters):
        """パラメーターの定義を検証し、骨の順と量の表に直す。"""
        parameters = list(parameters)
        if not parameters:
            raise ValueError("Expected at least one parameter")
        names = []
        joints = []
        keys = {}
        table = []
        for parameter in parameters:
            if not isinstance(parameter, dict):
                raise ValueError("Each parameter must be a dict")
            unknown = set(parameter) - {"name", "minimum", "maximum", "targets"}
            if unknown:
                raise ValueError("Unknown parameter keys: " + ", ".join(sorted(unknown)))
            name = parameter.get("name")
            if not isinstance(name, str) or not _NAME.match(name):
                raise ValueError("Parameter names must be alphanumeric and start with a letter: " + repr(name))
            if name in names:
                raise ValueError("Duplicate parameter name: " + name)
            if name.startswith(("translate", "scale", "rest", "joint", "parameterNames")):
                raise ValueError("Parameter names must not start with translate/scale/rest/joint: " + name)
            names.append(name)
            minimum = float(parameter.get("minimum", -1.0))
            maximum = float(parameter.get("maximum", 1.0))
            if not (math.isfinite(minimum) and math.isfinite(maximum)) or minimum > 0.0 or maximum < 0.0:
                raise ValueError("minimum must be <= 0 and maximum >= 0: " + name)
            targets = parameter.get("targets")
            if not isinstance(targets, dict) or not targets:
                raise ValueError("targets must be a non-empty dict of joint: amounts: " + name)
            amounts = {}
            for joint, values in targets.items():
                node = mlib.nodes.Node(str(joint))
                if not isinstance(node, mlib.nodes.Transform):
                    raise ValueError("Expected a transform or joint: " + str(joint))
                key = node.getUuid()
                if key not in keys:
                    keys[key] = len(joints)
                    joints.append(node)
                if not isinstance(values, dict) or set(values) - set(_ROLES):
                    raise ValueError("Amounts must be a dict with translate/scale(/Negative) keys: " + str(joint))
                parsed = {}
                for role in _ROLES:
                    default = values.get(role[:-len("Negative")]) if role.endswith("Negative") else None
                    vector = values.get(role)
                    if vector is None:
                        # 負の側を省略したら、正の側と同じ傾きで反対へ動かす(値に比例する一次式)。
                        vector = (0.0, 0.0, 0.0) if default is None else tuple(-float(v) for v in default)
                    vector = tuple(float(v) for v in vector)
                    if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
                        raise ValueError(role + " must have three finite values: " + str(joint))
                    parsed[role] = vector
                if keys[key] in amounts:
                    raise ValueError("The same joint is listed twice in " + name)
                amounts[keys[key]] = parsed
            table.append((name, minimum, maximum, amounts))
        return joints, table

    @classmethod
    @undoTransaction("mlrig.BodyProportion.create")
    def create(cls, parameters, name="bodyProportion", connect=True):
        """体格のパラメーターと、それが動かす骨の移動・スケールの計算グラフを作る。

        Args:
            parameters (Sequence[dict]): パラメーターの定義。各要素は
                ``{"name": "armLength", "minimum": -1.0, "maximum": 1.0, "targets": {骨: 量}}`` 。
                ``量`` は ``{"translate": (x, y, z), "scale": (x, y, z), "translateNegative": ..., "scaleNegative": ...}``
                の辞書で、値が1のとき(Negativeは-1のとき)の生成時からの変化量(移動は骨の親の空間、内部の単位cm)。
                省略した量は0、Negativeを省略すると正の量の符号を反転したもの(一次式)。
                minimum・maximum は値をclampする範囲(既定 -1・1、minimum<=0<=maximum)。
            name (str): 一意なcontainer名。
            connect (bool): Trueなら出力を骨の ``translate`` ・ ``scale`` へ接続する(生成時の値を保つので跳ねない)。

        Returns:
            BodyProportion: 出力の所有者。container にパラメーターごとの値(keyable)・``<名前>Minimum`` ・
                ``<名前>Maximum`` 、パラメーターと骨ごとの ``<名前><種類><骨の番号>`` (例 ``armLengthTranslate0``)、
                骨ごとの出力 ``translate<i>`` ・ ``scale<i>`` と生成時の ``restTranslate<i>`` ・ ``restScale<i>`` 、
                骨への ``joint<i>`` (message)を持つ。骨の番号 ``i`` は定義に最初に現れた順。

        Raises:
            ValueError: 定義が不正な場合、connect=True で骨の translate・scale が既に接続されている場合、
                またはnameが既に存在する場合。
        """
        joints, table = cls._parse(parameters)
        if mlib.ls(name):
            raise ValueError("BodyProportion container already exists: " + name)
        if connect:
            for joint in joints:
                for channel in ("translate", "scale"):
                    plugs = [joint.getPlug(channel)] + [joint.getPlug(channel + axis) for axis in "XYZ"]
                    if any(plug.getSource() is not None for plug in plugs):
                        raise ValueError("The {} of the joint is already connected: {}".format(
                            channel, joint.getFullName()))

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="parameterNames", dataType="string")
        owner.getPlug("parameterNames").set(" ".join(entry[0] for entry in table))
        for parameter, minimum, maximum, amounts in table:
            for attribute in [parameter, parameter + "Minimum", parameter + "Maximum"] + [
                    parameter + role[0].upper() + role[1:] + str(index) for index in amounts for role in _ROLES]:
                if owner.hasAttr(attribute):
                    raise ValueError("The parameter name collides with an attribute: " + attribute)
            owner.addAttr(longName=parameter, attributeType="double", defaultValue=0.0, keyable=True)
            owner.addAttr(longName=parameter + "Minimum", attributeType="double", defaultValue=minimum,
                          maxValue=0.0)
            owner.addAttr(longName=parameter + "Maximum", attributeType="double", defaultValue=maximum,
                          minValue=0.0)
            owner.setAttrFlags([parameter + "Minimum", parameter + "Maximum"], channelBox=True)
        for index, joint in enumerate(joints):
            owner.addAttr(longName="joint" + str(index), attributeType="message")
            joint.getPlug("message").connectTo(owner.getPlug("joint" + str(index)))
            for role in ("translate", "scale"):
                for prefix in ("rest" + role[0].upper() + role[1:], role):
                    owner.addAttr(longName=prefix + str(index), attributeType="double3")
                owner.getPlug("rest" + role[0].upper() + role[1:] + str(index)).set(
                    tuple(joint.getPlug(role).get()))

        # 値を正の部分 clamp(値, 0, 上限) と、負の部分の大きさ clamp(-値, 0, -下限) に分ける。
        parts = []
        for parameter, minimum, maximum, amounts in table:
            split = graph._node("clamp", parameter + "Split")
            owner.getPlug(parameter).connectTo(split.getPlug("inputR"))
            owner.getPlug(parameter + "Maximum").connectTo(split.getPlug("maxR"))
            # 符号の反転は単位を持たない multiplyDivide で行う(multDoubleLinear はMaya 2027で長さの型になり、
            # UIの単位がcm以外だと自動の単位変換が挟まるため)。
            flip = graph._node("multiplyDivide", parameter + "Flip")
            flip.getPlug("input2").set((-1.0, -1.0, 1.0))
            for source, axis, destination in ((parameter, "X", "inputG"), (parameter + "Minimum", "Y", "maxG")):
                owner.getPlug(source).connectTo(flip.getPlug("input1" + axis))
                flip.getPlug("output" + axis).connectTo(split.getPlug(destination))
            parts.append((parameter, split, amounts))

        for index, joint in enumerate(joints):
            suffix = str(index)
            for role in ("translate", "scale"):
                upper = role[0].upper() + role[1:]
                weighted = []
                for parameter, split, amounts in parts:
                    if index not in amounts:
                        continue
                    for side, channel in ((role, "outputR"), (role + "Negative", "outputG")):
                        attribute = parameter + side[0].upper() + side[1:] + suffix
                        owner.addAttr(longName=attribute, attributeType="double3")
                        owner.setAttrFlags([attribute + axis for axis in "XYZ"], keyable=True)
                        owner.getPlug(attribute).set(amounts[index][side])
                        weighted.append((attribute, split.getPlug(channel)))
                for axis in "XYZ":
                    # blendWeighted: 生成時の値(倍率1)に、量 * 正負の部分 を足す。値は倍精度のまま渡す。
                    total = graph._node("blendWeighted", "joint{}{}{}".format(index, upper, axis))
                    owner.getPlug("rest" + upper + suffix + axis).connectTo(total.getPlug("input")[0])
                    total.getPlug("weight")[0].set(1.0)
                    for slot, (attribute, weight) in enumerate(weighted, 1):
                        owner.getPlug(attribute + axis).connectTo(total.getPlug("input")[slot])
                        weight.connectTo(total.getPlug("weight")[slot])
                    total.getPlug("output").connectTo(owner.getPlug(role + suffix + axis))
                if connect:
                    if role == "translate":
                        # 内部の単位(cm)の値を長さへそのまま渡す。自動の単位変換はUIの単位で倍率が変わるため使わない。
                        back = graph._node("unitConversion", "joint{}{}Distance".format(index, upper))
                        owner.getPlug(role + suffix).connectTo(back.getPlug("input"))
                        back.getPlug("conversionFactor").set(1.0)
                        back.getPlug("output").connectTo(joint.getPlug("translate"))
                    else:
                        owner.getPlug(role + suffix).connectTo(joint.getPlug("scale"))
        return graph

    def getParameters(self):
        """パラメーターの名前を作成時の順に返す。

        Returns:
            list[str]: パラメーター名。
        """
        return str(self.container.getPlug("parameterNames").get() or "").split()

    def getJoints(self):
        """計算の対象の骨を、出力の番号の順に返す。

        Returns:
            list[Node]: 骨。``translate<i>`` ・ ``scale<i>`` の ``i`` の順(定義に最初に現れた順)。
        """
        joints = []
        index = 0
        while self.container.hasAttr("joint" + str(index)):
            joints.append(self.container.getPlug("joint" + str(index)).getSource().getNode())
            index += 1
        return joints

    def getValues(self):
        """全パラメーターの現在の値を返す(体格の設定として保存する用途)。

        Returns:
            dict[str, float]: パラメーター名と値。
        """
        return {name: float(self.container.getPlug(name).get()) for name in self.getParameters()}

    @undoTransaction("mlrig.BodyProportion.setValues")
    def setValues(self, values):
        """パラメーターの値をまとめて設定する(保存した体格の設定を読み込む用途)。

        Args:
            values (dict[str, float]): パラメーター名と値。含まれないパラメーターは変えない。

        Raises:
            ValueError: 未知のパラメーター名がある場合。
        """
        known = set(self.getParameters())
        unknown = set(values) - known
        if unknown:
            raise ValueError("Unknown parameters: " + ", ".join(sorted(unknown)))
        for name, value in values.items():
            self.container.getPlug(name).set(float(value))
