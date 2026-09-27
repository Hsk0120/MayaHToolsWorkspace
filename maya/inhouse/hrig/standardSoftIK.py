"""Maya標準演算ノードによるSoft IK。containerで生成物を所有する。"""

import math

from maya import cmds

import hlib


class StandardSoftIK:
    """距離・softnessからIK目標の位置倍率を作る標準DGビルダー。"""

    @classmethod
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
        owner = cmds.container(name=name)
        builder = cls()
        builder.owner = owner
        try:
            for attr, value in (("distance", 0.0), ("softness", 0.0), ("ratio", 1.0)):
                hlib.node(owner).add_attr(long_name=attr, attribute_type="double", default_value=value)
            distance = builder._condition("distance", owner + ".distance", 0, owner + ".distance", 0)
            soft = builder._condition("softMin", owner + ".softness", 0, owner + ".softness", 0)
            soft = builder._condition("softMax", soft, length, length, soft)
            # softness=0でも未選択側の除算が有限になるよう、分母だけを置換する。
            safe_soft = builder._condition("safeSoft", soft, 0, soft, 1)
            safe_distance = builder._condition("safeDistance", distance, 0, distance, 1)
            threshold = builder._sum("threshold", length, soft, subtract=True)
            excess = builder._sum("excess", distance, threshold, subtract=True)
            excess = builder._condition("positiveExcess", excess, 0, excess, 0)
            exponent = builder._multiply("exponent", excess, safe_soft, operation=2)
            negative = builder._multiply("negative", exponent, -1)
            power = builder._multiply("power", math.e, negative, operation=3)
            falloff = builder._sum("falloff", 1, power, subtract=True)
            softened = builder._sum("softened", threshold, builder._multiply("range", soft, falloff))
            limited = builder._condition("limited", distance, softened, softened, distance)
            hard = builder._condition("hard", distance, length, length, distance)
            result = builder._condition("result", soft, 0, limited, hard)
            ratio = builder._multiply("ratio", result, safe_distance, operation=2)
            hlib.plug(ratio).connect(owner + ".ratio")
            return owner
        except Exception:
            hlib.delete(owner)
            raise

    def _node(self, kind, role):
        """演算ノードを作成し、削除・保存用のcontainerへ登録する。

        Args:
            kind (str): 標準ノード型。
            role (str): 演算の識別名。

        Returns:
            str: 作成したノード名。
        """
        node = hlib.createNode(kind, name=self.owner + "_" + role, skipSelect=True).full_name()
        cmds.container(self.owner, edit=True, addNode=node)
        return node

    @staticmethod
    def _feed(value, destination):
        """入力へ定数を設定するかプラグを接続する。

        Args:
            value (float | str): 定数または入力プラグ名。
            destination (str): 接続先プラグ名。
        """
        if isinstance(value, str):
            hlib.plug(value).connect(destination)
        else:
            hlib.plug(destination).set(value)

    def _sum(self, role, left, right, subtract=False):
        """加減算を構築する。

        Args:
            role (str): 演算名。
            left (float | str): 左辺。
            right (float | str): 右辺。
            subtract (bool): Trueなら減算。

        Returns:
            str: 出力プラグ名。
        """
        node = self._node("plusMinusAverage", role)
        hlib.plug(node + ".operation").set(2 if subtract else 1)
        self._feed(left, node + ".input1D[0]")
        self._feed(right, node + ".input1D[1]")
        return node + ".output1D"

    def _multiply(self, role, left, right, operation=1):
        """乗除算・累乗を構築する。

        Args:
            role (str): 演算名。
            left (float | str): 左辺。
            right (float | str): 右辺。
            operation (int): 1は乗算、2は除算、3は累乗。

        Returns:
            str: 出力プラグ名。
        """
        node = self._node("multiplyDivide", role)
        hlib.plug(node + ".operation").set(operation)
        self._feed(left, node + ".input1X")
        self._feed(right, node + ".input2X")
        return node + ".outputX"

    def _condition(self, role, left, right, yes, no):
        """大小比較によって値を選択する。

        Args:
            role (str): 演算名。
            left (float | str): 比較の左辺。
            right (float | str): 比較の右辺。
            yes (float | str): 左辺が右辺より大きい場合の値。
            no (float | str): それ以外の値。

        Returns:
            str: 出力プラグ名。
        """
        node = self._node("condition", role)
        hlib.plug(node + ".operation").set(2)
        for value, attr in ((left, "firstTerm"), (right, "secondTerm"),
                            (yes, "colorIfTrueR"), (no, "colorIfFalseR")):
            self._feed(value, node + "." + attr)
        return node + ".outColorR"
