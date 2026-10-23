"""ジョイントのSwingを、曲げる側ごとに限界角が違う楕円コーンへ柔らかく制限する。"""

import math

from mlib.decorator import undoTransaction

from mlrig.setups.swingLimit import SwingLimit


class AsymmetricSwingLimit(SwingLimit):
    """直交2軸の+側・-側で別の限界角を持つ、象限ごとの楕円コーンの標準DG。

    例えば肩で「前へは大きく、後ろへは小さく」曲げられる可動域を表す。
    柔らかい制限・Twistの保持・出力はSwingLimitと同じ。
    """

    #: 限界角のアトリビュート名。(limit1の+側, limit1の-側, limit2の+側, limit2の-側)。
    LIMIT_ATTRIBUTES = ("limit1Positive", "limit1Negative", "limit2Positive", "limit2Negative")

    @classmethod
    def quadrantLimits(cls, limit1Positive, limit1Negative, limit2Positive, limit2Negative,
                       direction1, direction2):
        """曲げる向きの符号から、その象限で使う楕円の半径(限界角)を選ぶ。

        Args:
            limit1Positive (float): limit1軸の+側へ曲げたときの限界角(度)。
            limit1Negative (float): limit1軸の-側へ曲げたときの限界角(度)。
            limit2Positive (float): limit2軸の+側へ曲げたときの限界角(度)。
            limit2Negative (float): limit2軸の-側へ曲げたときの限界角(度)。
            direction1 (float): 先端方向のlimit1軸成分。
            direction2 (float): 先端方向のlimit2軸成分。

        Returns:
            tuple: (limit1側の半径, limit2側の半径)。成分が0以下なら-側を使う。
        """
        return (limit1Positive if direction1 > 0 else limit1Negative,
                limit2Positive if direction2 > 0 else limit2Negative)

    @classmethod
    def asymmetricLimitAngle(cls, limit1Positive, limit1Negative, limit2Positive, limit2Negative,
                             direction1, direction2):
        """曲げる向きに対する非対称な楕円コーンの限界角を計算する。

        Args:
            limit1Positive (float): limit1軸の+側の限界角(度)。
            limit1Negative (float): limit1軸の-側の限界角(度)。
            limit2Positive (float): limit2軸の+側の限界角(度)。
            limit2Negative (float): limit2軸の-側の限界角(度)。
            direction1 (float): 先端方向のlimit1軸成分。
            direction2 (float): 先端方向のlimit2軸成分。

        Returns:
            float: 限界角(度)。向きが定まらない場合は4つの限界角の最小値。
        """
        if math.hypot(direction1, direction2) <= 1e-9:
            return min(limit1Positive, limit1Negative, limit2Positive, limit2Negative)
        first, second = cls.quadrantLimits(limit1Positive, limit1Negative, limit2Positive, limit2Negative,
                                           direction1, direction2)
        return cls.limitAngle(first, second, direction1, direction2)

    @classmethod
    @undoTransaction("mlrig.AsymmetricSwingLimit.create")
    def create(cls, joint, name="asymmetricSwingLimit", axis="x", limit1Positive=80.0, limit1Negative=30.0,
               limit2Positive=60.0, limit2Negative=20.0, softness=0.2):
        """親空間での可動域制限済みの行列を生成する。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 一意なcontainer名。
            axis (str): 基準姿勢での骨の長手(Twist)軸x/y/z。
            limit1Positive (float): ``perpendicularAxes(axis)[0]`` の+側へ曲げる限界角。度、0より大きく179以下。
            limit1Negative (float): 同じ軸の-側へ曲げる限界角。度、0より大きく179以下。
            limit2Positive (float): ``perpendicularAxes(axis)[1]`` の+側へ曲げる限界角。度、0より大きく179以下。
            limit2Negative (float): 同じ軸の-側へ曲げる限界角。度、0より大きく179以下。
            softness (float): 限界角に対する柔らかい区間の割合。0で硬い制限、1で0度から緩める。

        Returns:
            AsymmetricSwingLimit: matrix・restMatrix・swingAngle・limitAngle・limitedAngle・excessAngle・ratioの所有者。

        Raises:
            ValueError: 軸・角度・softnessが範囲外の場合。

        Note:
            先端方向の直交2軸成分c・sの符号で半径を選ぶ。a = c>0 ? l1+ : l1-、b = s>0 ? l2+ : l2-。
            限界角 L = a*b*r / sqrt((b*c)^2 + (a*s)^2)、r=sqrt(c^2+s^2)。各象限は1/4の楕円で、
            軸上(c=0またはs=0)では隣の象限と同じ値になるため、向きを回してもLは連続する
            (象限の境で傾きは変わる)。柔らかい制限・excessAngle・ratioはSwingLimitと同じ式。
            向きが定まらないほど小さい曲げでは4つの限界角の最小値を使う。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        values = (limit1Positive, limit1Negative, limit2Positive, limit2Negative)
        for value in values:
            if not math.isfinite(value) or not 0 < value <= 179:
                raise ValueError("limit angles must be greater than 0 and at most 179 degrees")
        cls._checkSoftness(softness)
        return cls._build(joint, name, axis, tuple(zip(cls.LIMIT_ATTRIBUTES, values)), softness)

    @classmethod
    def _limitGraph(cls, scalar, owner, c, s):
        """成分の符号で象限の半径を選び、楕円の限界角を求めるDGを作る。

        Args:
            scalar (ScalarGraph): ノードを作るヘルパー。
            owner (Node): 4つの限界角のアトリビュートを持つcontainer。
            c (Plug): 先端方向のlimit1軸成分。
            s (Plug): 先端方向のlimit2軸成分。

        Returns:
            Plug: 限界角(度)。
        """
        p1, n1, p2, n2 = (owner.getPlug(attr) for attr in cls.LIMIT_ATTRIBUTES)
        # condition(operation=2)は「左 > 右」。成分が0のときは-側だが、軸上では半径が式から消えるため連続する。
        l1 = scalar.condition("limit1Side", c, 0, p1, n1)
        l2 = scalar.condition("limit2Side", s, 0, p2, n2)
        smaller1 = scalar.condition("smallerLimit1", p1, n1, n1, p1)
        smaller2 = scalar.condition("smallerLimit2", p2, n2, n2, p2)
        smallest = scalar.condition("smallestLimit", smaller1, smaller2, smaller2, smaller1)
        return cls._ellipseGraph(scalar, l1, l2, c, s, smallest)
