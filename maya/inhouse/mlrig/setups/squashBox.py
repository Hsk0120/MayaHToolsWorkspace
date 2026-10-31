"""箱形の対象を上下左右の4辺から押し引きして、体積を保つように潰し伸ばす標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class SquashBox(TwistDistribution):
    """上・下・外・内の4辺の押し引きから、反対の辺を支点にした潰しと伸ばしの行列を作る標準DG。

    各辺の値(cm)を正にするとその辺が外へ動いて伸び、負にすると内へ動いて潰れる。
    伸ばした向きの拡大率は (d + 値) / d、直交する2軸は体積を保つ近似として 1 - volume * 値 / d にする
    (dは向かい合う辺の間の長さ)。
    """

    @classmethod
    def factors(cls, amount, length, volume):
        """1つの辺の値から、伸ばす向きと直交する向きの拡大率を計算する。

        Args:
            amount (float): 辺を外へ動かす量(cm)。
            length (float): 向かい合う辺の間の長さ(cm)。
            volume (float): 体積を保つ割合(0〜1)。

        Returns:
            tuple[float, float]: (伸ばす向きの拡大率 1 + amount/length, 直交する向きの拡大率 1 - volume*amount/length)。
        """
        ratio = amount / length
        return 1.0 + ratio, 1.0 - volume * ratio

    @classmethod
    @undoTransaction("mlrig.SquashBox.create")
    def create(cls, root, name="squashBox", height=2.0, width=2.0, verticalAxis="y", sideAxis="x", volume=1.0):
        """rootの空間に置いた箱の4辺の押し引きから、潰し伸ばした行列を生成する。

        Args:
            root (str | Node): 箱の基準のtransform。箱はこの原点を中心に置く。
            name (str): 一意なcontainer名。
            height (float): 上下の辺の間の長さ(cm、verticalAxis方向)。
            width (float): 外と内の辺の間の長さ(cm、sideAxis方向)。
            verticalAxis (str): rootのローカルで上下を表す軸 x/y/z。上は正の向き。
            sideAxis (str): rootのローカルで外内を表す軸 x/y/z。外は正の向き。verticalAxisと別の軸。
            volume (float): 体積を保つ割合の初期値(0〜1)。0なら直交する向きは変えない。

        Returns:
            SquashBox: matrix・localMatrixの所有者。containerに top・bottom・outer・inner・volume を持つ。

        Raises:
            ValueError: 軸・長さ・割合が不正な場合、rootがtransformでない場合、またはnameが既に存在する場合。

        Note:
            1つの辺の行列 P = T(-p) · S · T(p)。pは反対の辺の生成時の位置、Sは伸ばす向きに (1+a/d)、
            直交する2軸に (1-volume*a/d) の拡大(aは辺の値、dはheightまたはwidth)。
            localMatrix = P_inner · P_outer · P_bottom · P_top(Mayaの行ベクトルの規約で左から先に適用)、
            matrix = localMatrix · rootのworldMatrix。順序は上→下→外→内の階層で、各支点は生成時の位置。
            全ての値が0なら単位行列なので、作成時に跳ねない。辺が反対の辺を越えるほど潰す(a <= -d)と裏返る。
        """
        axes = ("x", "y", "z")
        if verticalAxis not in axes or sideAxis not in axes:
            raise ValueError("verticalAxis and sideAxis must be x, y or z")
        if verticalAxis == sideAxis:
            raise ValueError("verticalAxis and sideAxis must be different")
        height, width, volume = (float(value) for value in (height, width, volume))
        if not all(math.isfinite(value) for value in (height, width, volume)):
            raise ValueError("height, width and volume must be finite")
        if height <= 0.0 or width <= 0.0:
            raise ValueError("height and width must be positive")
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        if mlib.objExists(name):
            raise ValueError("SquashBox container already exists: " + name)
        root = mlib.nodes.Node(root)
        if not isinstance(root, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the root")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for attr in ("top", "bottom", "outer", "inner"):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="volume", attributeType="double", defaultValue=volume, keyable=True,
                      minValue=0, maxValue=1)
        for attr in ("localMatrix", "matrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        def point(axis, value):
            return [value if item == axis else 0.0 for item in axes]

        # (辺の値, 伸ばす軸, 長さ, 支点 = 反対の辺の生成時の位置)
        sides = (
            ("top", verticalAxis, height, point(verticalAxis, -height / 2.0)),
            ("bottom", verticalAxis, height, point(verticalAxis, height / 2.0)),
            ("outer", sideAxis, width, point(sideAxis, -width / 2.0)),
            ("inner", sideAxis, width, point(sideAxis, width / 2.0)),
        )
        local = graph._node("multMatrix", "local")
        # 階層の末端(内)から先に掛けるので、multMatrixへは内→外→下→上の順に並べる。
        slot = 0
        for attr, axis, length, pivot in reversed(sides):
            # ratio = a/d、perp = 1 - volume*ratio、main = 1 + ratio
            ratio = graph._node("multiplyDivide", attr + "Ratio")
            owner.getPlug(attr).connectTo(ratio.getPlug("input1X"))
            ratio.getPlug("input2X").set(1.0 / length)
            owner.getPlug(attr).connectTo(ratio.getPlug("input1Y"))
            ratio.getPlug("input2Y").set(1.0 / length)
            weighted = graph._node("multiplyDivide", attr + "Volume")
            ratio.getPlug("outputY").connectTo(weighted.getPlug("input1X"))
            owner.getPlug("volume").connectTo(weighted.getPlug("input2X"))
            main = graph._node("plusMinusAverage", attr + "Main")
            main.getPlug("input1D")[0].set(1)
            ratio.getPlug("outputX").connectTo(main.getPlug("input1D")[1])
            perp = graph._node("plusMinusAverage", attr + "Perpendicular")
            perp.getPlug("operation").set(2)
            perp.getPlug("input1D")[0].set(1)
            weighted.getPlug("outputX").connectTo(perp.getPlug("input1D")[1])
            scale = graph._node("composeMatrix", attr + "Scale")
            for item in axes:
                source = main if item == axis else perp
                source.getPlug("output1D").connectTo(scale.getPlug("inputScale" + item.upper()))
            # T(-p) · S · T(p)
            local.getPlug("matrixIn")[slot].set(list(Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                                                             -pivot[0], -pivot[1], -pivot[2], 1])))
            scale.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[slot + 1])
            local.getPlug("matrixIn")[slot + 2].set(list(Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                                                                 pivot[0], pivot[1], pivot[2], 1])))
            slot += 3
        local.getPlug("matrixSum").connectTo(owner.getPlug("localMatrix"))
        world = graph._node("multMatrix", "world")
        local.getPlug("matrixSum").connectTo(world.getPlug("matrixIn")[0])
        root.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        return graph
