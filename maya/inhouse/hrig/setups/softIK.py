"""Maya標準演算ノードによるSoft IK。containerで生成物を所有する。"""

import math

import hlib

from hlib import getPlug as to_plug
from hlib.decorators.undo import undo_transaction
from hlib.utils.scalarGraph import ScalarGraph


class SoftIK:
    """距離・softnessからIK目標の位置倍率を作る標準DGビルダー。"""

    @classmethod
    @undo_transaction("hrig.SoftIK.create")
    def create(cls, name, length):
        """標準ノードをcontainerへまとめ、入出力属性を返す。

        Args:
            name (str): container名。
            length (float): 正のチェーン長。

        Returns:
            str: distance、softness、ratio属性を持つcontainerの名前。
        """
        if not math.isfinite(length) or length <= 0:
            raise ValueError("length must be positive and finite")
        owner = hlib.nodes.Container.create(name).full_name()
        builder = ScalarGraph(owner)
        try:
            for attr, value in (("distance", 0.0), ("softness", 0.0), ("ratio", 1.0)):
                hlib.nodes.Node(owner).add_attribute(
                    long_name=attr, attribute_type="double", default_value=value
                )
            distance = builder.condition("distance", owner + ".distance", 0, owner + ".distance", 0)
            soft = builder.condition("softMin", owner + ".softness", 0, owner + ".softness", 0)
            soft = builder.condition("softMax", soft, length, length, soft)
            # softness=0でも未選択側の除算が有限になるよう、分母だけを置換する。
            safe_soft = builder.condition("safeSoft", soft, 0, soft, 1)
            safe_distance = builder.condition("safeDistance", distance, 0, distance, 1)
            threshold = builder.sum("threshold", length, soft, subtract=True)
            excess = builder.sum("excess", distance, threshold, subtract=True)
            excess = builder.condition("positiveExcess", excess, 0, excess, 0)
            exponent = builder.multiply("exponent", excess, safe_soft, operation=2)
            negative = builder.multiply("negative", exponent, -1)
            power = builder.multiply("power", math.e, negative, operation=3)
            falloff = builder.sum("falloff", 1, power, subtract=True)
            softened = builder.sum("softened", threshold, builder.multiply("range", soft, falloff))
            limited = builder.condition("limited", distance, softened, softened, distance)
            hard = builder.condition("hard", distance, length, length, distance)
            result = builder.condition("result", soft, 0, limited, hard)
            ratio = builder.multiply("ratio", result, safe_distance, operation=2)
            to_plug(ratio).connect(owner + ".ratio")
            return owner
        except Exception:
            hlib.delete(owner)
            raise

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
