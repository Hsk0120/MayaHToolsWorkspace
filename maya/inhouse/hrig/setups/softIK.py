"""Maya標準演算ノードによるSoft IK。containerで生成物を所有する。"""

import math

import hlib

from hlib import getPlug as to_plug
from hlib.decorator import nativeUnits, undoTransaction
from hlib.common.scalarGraph import ScalarGraph


class SoftIK:
    """距離・softnessからIK目標の位置倍率を作る標準DGビルダー。"""

    @classmethod
    @undoTransaction("hrig.SoftIK.create")
    def create(cls, name, length):
        """標準ノードをcontainerへまとめ、入出力アトリビュートを備えた参照を返す。

        Args:
            name (str): container名。
            length (float): 正のチェーン長。

        Returns:
            str: distance、softness、ratioアトリビュートを持つcontainerの名前。
        """
        if not math.isfinite(length) or length <= 0:
            raise ValueError("length must be positive and finite")
        owner = hlib.nodes.Container.create(name).getFullName()
        builder = ScalarGraph(owner)
        try:
            for attr, value in (("distance", 0.0), ("softness", 0.0), ("ratio", 1.0)):
                hlib.nodes.Node(owner).addAttr(
                    longName=attr, attributeType="double", defaultValue=value
                )
            distance = cls._condition(builder, "distance", owner + ".distance", 0, owner + ".distance", 0)
            soft = cls._condition(builder, "softMin", owner + ".softness", 0, owner + ".softness", 0)
            soft = cls._condition(builder, "softMax", soft, length, length, soft)
            # softness=0でも未選択側の除算が有限になるよう、分母だけを置換する。
            safe_soft = cls._condition(builder, "safeSoft", soft, 0, soft, 1)
            safe_distance = cls._condition(builder, "safeDistance", distance, 0, distance, 1)
            # multiplyDivideは非ゼロでも約1e-5以下の分母で100000を返す。
            # Maya 2025以降のdouble演算を使い、指数側の1-powerもfloatへ丸めない。
            threshold = cls._arithmetic(owner, "subtract", "threshold", length, soft)
            excess = cls._arithmetic(owner, "subtract", "excess", distance, threshold)
            excess = cls._condition(builder, "positiveExcess", excess, 0, excess, 0)
            exponent = cls._arithmetic(owner, "divide", "exponent", excess, safe_soft)
            negative = cls._arithmetic(owner, "multiply", "negative", exponent, -1)
            power = cls._arithmetic(owner, "power", "power", math.e, negative)
            falloff = cls._arithmetic(owner, "subtract", "falloff", 1, power)
            softened = cls._arithmetic(
                owner, "sum", "softened", threshold,
                cls._arithmetic(owner, "multiply", "range", soft, falloff),
            )
            limited = cls._condition(builder, "limited", distance, softened, softened, distance)
            hard = cls._condition(builder, "hard", distance, length, length, distance)
            result = cls._condition(builder, "result", soft, 0, limited, hard)
            ratio = cls._arithmetic(owner, "divide", "ratio", result, safe_distance)
            cls._feed(owner, ratio, owner + ".ratio")
            return owner
        except Exception:
            hlib.delete(owner)
            raise

    @staticmethod
    def _condition(builder, role, left, right, yes, no):
        """既存の比較規則を使い、型変換を内部単位・container所有へ揃える。

        Args:
            builder (ScalarGraph): 同じ所有先の標準比較ビルダー。
            role (str): 演算の識別子。
            left (float | str | Plug): 比較の左辺。
            right (float | str | Plug): 比較の右辺。
            yes (float | str | Plug): 左辺が右辺より大きい場合の値。
            no (float | str | Plug): それ以外の値。

        Returns:
            Plug: 既存と同じcondition出力。
        """
        with nativeUnits():
            output = builder.condition(role, left, right, yes, no)
        node = output.getNode()
        for attr in ("firstTerm", "secondTerm", "colorIfTrueR", "colorIfFalseR"):
            source = node.getPlug(attr).getSourceWithConversion()
            if source is not None and source.getNode().getType() == "unitConversion":
                builder.container.addMembers(source.getNode())
        return output

    @staticmethod
    def _feed(owner, value, destination):
        """数値を内部単位で渡し、自動生成された変換ノードも所有下へ入れる。

        Args:
            owner (str): 所有するcontainer。
            value (float | str | Plug): 定数または入力プラグ。
            destination (str | Plug): 接続・設定先。

        Note:
            Maya 2025の標準算術はdoubleLinear、2027はdoubleという型の差がある。
            nativeUnitsで接続時のUI単位変換を1に統一し、計算値の単位を変えない。
        """
        destination = to_plug(destination)
        with nativeUnits():
            if isinstance(value, (str, hlib.plugs.Plug)):
                source = to_plug(value)
                source.connectTo(destination)
                immediate = destination.getSourceWithConversion()
                if immediate is not None and immediate.getNode() != source.getNode():
                    conversion = immediate.getNode()
                    if conversion.getType() == "unitConversion":
                        hlib.nodes.Container(owner).addMembers(conversion)
            else:
                destination.set(value)

    @classmethod
    def _arithmetic(cls, owner, kind, role, left, right):
        """Soft IKだけに必要な標準double演算をcontainerへ追加する。

        Args:
            owner (str): 所有するcontainer。
            kind (str): divide/subtract/sum/multiply/power。
            role (str): 演算の識別子。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。

        Returns:
            Plug: double精度の出力。公開するdistance/softness/ratioの型は変えない。
        """
        container = hlib.nodes.Container(owner)
        node = container.createNode(kind, name=container.getName() + "_" + role)
        if kind in ("sum", "multiply"):
            destinations = (node.getPlug("input")[0], node.getPlug("input")[1])
        elif kind == "power":
            destinations = (node.getPlug("input"), node.getPlug("exponent"))
        else:
            destinations = (node.getPlug("input1"), node.getPlug("input2"))
        cls._feed(owner, left, destinations[0])
        cls._feed(owner, right, destinations[1])
        return node.getPlug("output")

    @staticmethod
    def distance(distance, length, softness):
        """到達距離を連続に減衰する参照実装。

        Args:
            distance (float): 根元から目標までの距離。
            length (float): 2本の骨長の和。
            softness (float): 0以上、全長以下の減衰範囲。

        Returns:
            float: 部位空間の減衰後の距離。入力と同じ距離単位。

        Raises:
            ValueError: 非有限値、負の距離、不正な骨長や減衰範囲の場合。
        """
        if not all(math.isfinite(v) for v in (distance, length, softness)):
            raise ValueError("Expected finite parameters")
        if distance < 0 or length <= 0 or not 0 <= softness <= length:
            raise ValueError("Invalid Soft IK parameters")
        threshold = length - softness
        if softness == 0 or distance <= threshold:
            return min(distance, length)
        return threshold + softness * (1 - math.exp(-(distance - threshold) / softness))
