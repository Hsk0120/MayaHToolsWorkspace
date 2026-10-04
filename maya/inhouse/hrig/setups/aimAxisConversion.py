"""既存Aimの出力を1〜2軸へ変換し、元の接続を復元する。"""

import math

import maya.cmds as cmds

import hlib
from hlib.decorators.undo import undoTransaction
from hlib.json import JsonText
from hlib.nodes import Container, Node, Transform
from hlib.plugs import Plug
from hlib.utils.scalarGraph import ScalarGraph


_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
_TAG = "hrigAimAxisConversion"


class AimAxisConversion:
    """標準DGだけで動く変換。containerが生成ノードと復元情報を所有する。

    sourceの全Euler出力から同じ回転行列を再構成するため、部分Eulerの別解切替を
    そのまま採用しない。元の循環接続やWorld Upの特異点を修復するものではない。
    """

    def __init__(self, container):
        """保存済みcontainerを参照する。

        Args:
            container (str | Container): 本ツールで作成した所有ノード。
        """
        self.container = Container(container)
        if not self.container.hasAttribute(_TAG):
            raise ValueError("Aim軸変換のcontainerではありません。")
        self._graph = ScalarGraph(self.container)
        self._serial = 0

    @classmethod
    def find(cls, constraint):
        """Aimのmessage接続から変換を検索する。改名・保存読込に対応する。

        Args:
            constraint (str | Node): 既存aimConstraint。

        Returns:
            AimAxisConversion | None: 既存の変換。
        """
        source = Node(constraint)
        for plug in source.plug("message").destinations():
            if plug.node.type() == "container" and plug.node.hasAttribute(_TAG):
                return cls(plug.node)
        return None

    @classmethod
    @undoTransaction("hrig.AimAxisConversion.convert")
    def create(cls, constraint, axes="x", mode="euler", direction="x",
               reference=(0.0, 0.0, 0.0), half_range=math.radians(85),
               preserve_pose=True):
        """Aimと回転の間に変換を挿入する。既存変換は復元して切り替える。

        Args:
            constraint (str | Node): 回転へ直接接続されたaimConstraint。
            axes (str): x/y/z/xy/xz/yzのいずれか。
            mode (str): euler（等価解）、direction（方向再解）、twist（軸別Twist）。
            direction (str): direction方式で追うローカル軸。x/y/z/-x/-y/-z。
                回転軸と異なる軸。2軸では残る軸を指定する。
            reference (Sequence[float]): euler方式のXYZ基準角。ラジアン。
            half_range (float): 基準角からの許容半幅。ラジアン、0より大きくpi未満。
            preserve_pose (bool): direction/twistの出力に定数を加え作成時の角度を維持。

        Returns:
            AimAxisConversion: 復元可能な変換。outputX/Y/Zは角度Plug、validは診断値。

        Raises:
            ValueError: 不正な設定、間接接続、複数出力先、参照・ロック等の非対応構成。
            RuntimeError: 接続変更に失敗した場合。Undoトランザクションで巻き戻す。

        Note:
            未選択軸の元Aim接続は外して現在値に固定する。他の入力は維持する。
            directionはAimの補正済み回転行列で指定方向を変換してから1/2軸で再解する。
            方向の再解は未選択軸0の基準姿勢で行う。未選択軸の固定角や姿勢維持の
            加算がある場合、最終姿勢の方向と元Aimの方向の完全一致は保証しない。
            Twistは選択軸ごとの独立した抽出で、2つを足して元回転へ再構成はできない。
            特異点では0角、±pi境界はwrap。履歴の保持・多回転アンラップはしない。
        """
        axes = "".join(sorted(axes.lower()))
        if axes not in ("x", "y", "z", "xy", "xz", "yz"):
            raise ValueError("回転軸はX/Y/Zの1軸または2軸を指定してください。")
        if mode not in ("euler", "direction", "twist"):
            raise ValueError("不明な変換方式です。")
        if direction not in ("x", "y", "z", "-x", "-y", "-z"):
            raise ValueError("狙う方向は±X/±Y/±Zを指定してください。")
        if mode == "direction" and direction[-1] in axes:
            raise ValueError("方式2の狙う軸は回転軸以外を指定してください（例: X回転ならY方向）。")
        reference = tuple(float(a) for a in reference)
        if len(reference) != 3 or not all(math.isfinite(a) for a in reference):
            raise ValueError("XYZ基準角は有限のラジアン3値を指定してください。")
        if not math.isfinite(half_range) or not 0 < half_range < math.pi:
            raise ValueError("許容半幅は0度より大きく180度未満にしてください。")
        source = Node(constraint)
        if source.type() != "aimConstraint":
            raise ValueError("aimConstraintノードを選択してください。")
        previous = cls.find(source)
        original_state = None
        if previous is not None:
            original_state = JsonText.loads(previous.container.plug("settings").get())
            previous.restore()
        target, original, compound = cls._inspect(source, axes)
        order = int(source.plug("constraintRotateOrder").get())
        if order != int(target.plug("rotateOrder").get()):
            raise ValueError("Aimと対象のRotate Orderが異なります。")
        values = [target.plug("rotate" + a.upper()).get() for a in "xyz"]
        rest_values = (original_state.get("restValues") if original_state else None)
        if rest_values is None:
            rest_values = [source.plug("restRotate" + a).get() for a in "XYZ"]
        constraint_settings = cls._captureSettings(source)
        owner = Container.create(name=source.name().split("|")[-1] + "_axisConversion")
        owner.addAttribute(longName=_TAG, attributeType="bool", defaultValue=True)
        for attr, node in (("sourceConstraint", source), ("drivenNode", target)):
            owner.addAttribute(longName=attr, attributeType="message")
            node.plug("message").connect(owner.plug(attr))
        owner.addAttribute(longName="settings", dataType="string")
        owner.plug("settings").set(JsonText.dumps(dict(
            version=1, axes=axes, mode=mode, direction=direction, order=order,
            reference=reference, halfRange=half_range, preservePose=bool(preserve_pose),
            restValues=rest_values,
            constraintSettings=constraint_settings,
            original=original, compound=compound, values=values)))
        graph = cls(owner)
        compose = graph._node("composeMatrix", "aimRotation")
        source.plug("constraintRotate").connect(compose.plug("inputRotate"))
        source.plug("constraintRotateOrder").connect(compose.plug("inputRotateOrder"))
        decompose = graph._node("decomposeMatrix", "rotation")
        compose.plug("outputMatrix").connect(decompose.plug("inputMatrix"))
        source.plug("constraintRotateOrder").connect(decompose.plug("inputRotateOrder"))
        if mode == "euler":
            outputs, valid = graph._euler(decompose, axes, reference, half_range, order)
        elif mode == "direction":
            outputs, valid = graph._direction(compose, axes, direction, order)
        else:
            outputs, valid = graph._twist(decompose, axes)
        # ノードの組み方は生成時のRotate Orderに依存する。変更後は再変換を促す。
        order_valid = graph._node("condition", "orderValid")
        source.plug("constraintRotateOrder").connect(order_valid.plug("firstTerm"))
        order_valid.plug("secondTerm").set(order)
        graph._feed(valid, order_valid.plug("colorIfTrueR"))
        order_valid.plug("colorIfFalseR").set(0)
        target_order_valid = graph._node("condition", "targetOrderValid")
        target.plug("rotateOrder").connect(target_order_valid.plug("firstTerm"))
        target_order_valid.plug("secondTerm").set(order)
        order_valid.plug("outColorR").connect(target_order_valid.plug("colorIfTrueR"))
        target_order_valid.plug("colorIfFalseR").set(0)
        owner.addAttribute(longName="valid", attributeType="double", keyable=False)
        target_order_valid.plug("outColorR").connect(owner.plug("valid"))
        owner.plug("valid").setFlags(channelBox=True)
        for i, axis in enumerate("xyz"):
            owner.addAttribute(longName="output" + axis.upper(), attributeType="doubleAngle")
            if axis not in axes:
                owner.plug("output" + axis.upper()).set(values[i])
                continue
            output = outputs[axis]
            if preserve_pose and mode != "euler":
                output = graph._sum(output, values[i] - output.get())
            graph._angle(output).connect(owner.plug("output" + axis.upper()))
        # 結果値を評価してから元接続を外す。基準値に対象回転のライブ接続は作らない。
        for axis in axes:
            owner.plug("output" + axis.upper()).get()
        if compound:
            source.plug("constraintRotate").disconnect(target.plug("rotate"))
        else:
            for axis in original:
                source.plug(original[axis]).disconnect(target.plug("rotate" + axis.upper()))
        for i, axis in enumerate("xyz"):
            destination = target.plug("rotate" + axis.upper())
            if axis in axes:
                owner.plug("output" + axis.upper()).connect(destination)
            elif axis in original:
                destination.set(values[i])
        return graph

    @undoTransaction("hrig.AimAxisConversion.restore")
    def restore(self):
        """元Aimの設定値と直接接続を復元し、変換の所有ノードを全て削除する。

        接続された回転は復元後に元Aimが計算する。Euler値の追加補正は行わない。

        Raises:
            ValueError: 対象の削除、接続の手編集、設定の新しい入力やロックがある場合。
        """
        owner = self.container
        links = [owner.plug(attr).source() for attr in ("sourceConstraint", "drivenNode")]
        if any(link is None for link in links):
            raise ValueError("元のAimまたは対象が削除されているため復元できません。")
        source, target = [link.node for link in links]
        data = JsonText.loads(owner.plug("settings").get())
        settings = data.get("constraintSettings", {})
        if not settings and "restValues" in data:
            # 旧変換が記録した初期値だけを復元し、未記録の設定は推測しない。
            settings = dict(zip(("restRotate" + a for a in "XYZ"), data["restValues"]))
        updates = []
        for attr, value in settings.items():
            plug = source.plug(attr)
            if plug.get() == value:
                continue
            parent = plug.parent() if plug.isChild() else None
            if (source.isLocked() or source.isReferenced() or plug.isLocked()
                    or plug.source() is not None
                    or (parent is not None and (parent.isLocked() or parent.source() is not None))):
                raise ValueError("元Aimの設定に入力またはロックがあるため復元できません: " + plug.fullName())
            updates.append((plug, value))
        touched = set(data["axes"]) | set(data["original"])
        for axis in touched:
            dest = target.plug("rotate" + axis.upper())
            expected = owner.plug("output" + axis.upper()) if axis in data["axes"] else None
            if (dest.isLocked() or target.plug("rotate").isLocked() or target.isLocked()
                    or target.isReferenced() or dest.source() != expected):
                raise ValueError("変換後の接続・ロックが変更されています。復元対象: " + dest.fullName())
        for axis in data["axes"]:
            target.plug("rotate" + axis.upper()).disconnectInput()
        for plug, value in updates:
            plug.set(value)
        for i, axis in enumerate("xyz"):
            if axis in touched:
                target.plug("rotate" + axis.upper()).set(data["values"][i])
        if data["compound"]:
            source.plug("constraintRotate").connect(target.plug("rotate"))
        else:
            for axis, attr in data["original"].items():
                source.plug(attr).connect(target.plug("rotate" + axis.upper()))
        owner.delete()

    @staticmethod
    def _captureSettings(source):
        """元Aimの未接続設定値を記録する。角度はラジアンで保持する。

        Args:
            source (Node): 記録するaimConstraint。

        Returns:
            dict: アトリビュートパスと値。入力で駆動された設定は記録しない。
        """
        attrs = [prefix + axis for prefix in (
            "restRotate", "offset", "aimVector", "upVector", "worldUpVector") for axis in "XYZ"]
        attrs.extend(("worldUpType", "enableRestPosition", "useOldOffsetCalculation"))
        attrs.extend(plug.fullName().split(".", 1)[1] for plug in source.weightPlugs())
        settings = {}
        for attr in attrs:
            plug = source.plug(attr)
            parent = plug.parent() if plug.isChild() else None
            if plug.source() is None and (parent is None or parent.source() is None):
                settings[attr] = plug.get()
        return settings

    @staticmethod
    def _inspect(source, axes):
        """直接の回転出力先を検証し、復元する接続を記録する。"""
        targets = {}
        for attr in ("constraintRotate", "constraintRotateX", "constraintRotateY", "constraintRotateZ"):
            for dest in source.plug(attr).destinations():
                if isinstance(dest.node, Transform) and dest.attributeName() in (
                        "rotate", "rotateX", "rotateY", "rotateZ"):
                    targets[dest.node.uuid()] = dest.node
        if len(targets) != 1:
            raise ValueError("回転へ直接接続された対象が1つのAimに対応します。間接接続・複数対象は未対応です。")
        target = next(iter(targets.values()))
        if target.isReferenced() or target.isLocked() or source.isReferenced() or source.isLocked():
            raise ValueError("参照・ロックされたAimまたは対象は変換できません。")
        compound = target.plug("rotate").source() == source.plug("constraintRotate")
        original = {}
        for axis in "xyz":
            dest = target.plug("rotate" + axis.upper())
            incoming = dest.source()
            own = source.plug("constraintRotate" + axis.upper())
            if compound or incoming == own:
                original[axis] = "constraintRotate" + axis.upper()
            elif axis in axes and incoming is not None:
                raise ValueError("別の入力接続は置換しません: " + dest.fullName())
            if (axis in axes or axis in original) and (dest.isLocked() or target.plug("rotate").isLocked()):
                raise ValueError("回転がロックされています: " + dest.fullName())
        return target, original, compound

    def _node(self, kind, role):
        """用途名を付けた標準ノードを所有containerへ作る。"""
        self._serial += 1
        return self.container.createNode(kind, name="{}_{}{}".format(self.container.name(), role, self._serial))

    @staticmethod
    def _feed(value, destination):
        """単位なしの数値またはPlugを入力する。"""
        if isinstance(value, Plug):
            value.connect(destination)
        else:
            destination.set(value)

    def _sum(self, a, b, subtract=False):
        """単位なしの加減算を作る。"""
        return self._graph.sum("sum", a, b, subtract=subtract)

    def _mul(self, a, b):
        """単位なしの乗算を作る。"""
        return self._graph.multiply("product", a, b)

    def _choose(self, a, b, yes, no):
        """a > bで値を選ぶ。"""
        return self._graph.condition("choose", a, b, yes, no)

    def _scalar(self, angle):
        """角度をUI単位に依存しないラジアンの数値へ変換する。"""
        node = self._node("unitConversion", "radians")
        angle.connect(node.plug("input"))
        node.plug("conversionFactor").set(1)
        return node.plug("output")

    def _angle(self, scalar):
        """ラジアンの数値を角度入力へ渡す明示的な単位変換を作る。"""
        node = self._node("unitConversion", "angle")
        self._feed(scalar, node.plug("input"))
        node.plug("conversionFactor").set(1)
        return node.plug("output")

    def _wrap(self, value):
        """既知の±3pi以内の値を±piへ折り返す。"""
        high = self._choose(value, math.pi, self._sum(value, -2 * math.pi), value)
        return self._choose(-math.pi, high, self._sum(high, 2 * math.pi), high)

    def _euler(self, decompose, axes, reference, width, order):
        """2組の等価解を選択軸の基準距離と範囲で評価する。"""
        candidates, scores, in_ranges = [], [], []
        middle = _ORDERS[order][1]
        for alternate in (False, True):
            values, score, inside = {}, 0.0, 1.0
            for i, axis in enumerate("xyz"):
                angle = self._scalar(decompose.plug("outputRotate" + axis.upper()))
                if alternate:
                    angle = self._sum(math.pi, angle, subtract=True) if axis == middle else self._sum(angle, math.pi)
                # 基準は何周分でも指定できるよう定数側だけ先に主値へ落とす。
                center = (reference[i] + math.pi) % (2 * math.pi) - math.pi
                delta = self._wrap(self._sum(angle, center, subtract=True))
                values[axis] = self._sum(delta, reference[i])
                if axis in axes:
                    squared = self._mul(delta, delta)
                    score = self._sum(score, squared)
                    inside = self._mul(inside, self._choose(squared, width * width, 0, 1))
            candidates.append(values)
            scores.append(score)
            in_ranges.append(inside)
        # 一方だけ範囲内ならそれを優先。双方同条件なら基準との距離で選ぶ。
        nearer = self._choose(scores[0], scores[1], 1, 0)
        select_alt = self._choose(in_ranges[1], in_ranges[0], 1,
                                  self._choose(in_ranges[0], in_ranges[1], 0, nearer))
        outputs = {a: self._choose(select_alt, 0.5, candidates[1][a], candidates[0][a]) for a in axes}
        count = self._sum(in_ranges[0], in_ranges[1])
        valid = self._choose(count, 1.5, 0, self._choose(count, 0.5, 1, 0))
        return outputs, valid

    def _atan(self, y, x):
        """angleBetween.angleと符号判定でatan2を作る。原点は0角・無効。"""
        length = self._sum(self._mul(x, x), self._mul(y, y))
        valid = self._choose(length, 1e-12, 1, 0)
        angle = self._node("angleBetween", "signedAngle")
        angle.plug("vector1").set((1, 0, 0))
        angle.plug("vector2").set((0, 0, 0))
        self._choose(valid, 0.5, x, 1).connect(angle.plug("vector2X"))
        self._choose(valid, 0.5, y, 0).connect(angle.plug("vector2Y"))
        radians = self._scalar(angle.plug("angle"))
        return self._choose(0, y, self._mul(radians, -1), radians), valid

    def _direction(self, compose, axes, direction, order):
        """全Aim姿勢の指定方向を、回転順に沿うヒンジまたは2軸角へ再解する。"""
        aim = direction[-1]
        sign = -1 if direction.startswith("-") else 1
        vector = self._node("vectorProduct", "aimDirection")
        vector.plug("operation").set(3)
        vector.plug("input1" + aim.upper()).set(sign)
        compose.plug("outputMatrix").connect(vector.plug("matrix"))
        ordered = [axis for axis in _ORDERS[order] if axis in axes]
        values = {a: vector.plug("output" + a.upper()) for a in "xyz"}

        def solve(axis, components):
            """基準方向との平面内角度を取得する。"""
            other = next(a for a in "xyz" if a not in (axis, aim))
            cross_sign = 1 if (axis + aim + other) in ("xyz", "yzx", "zxy") else -1
            return self._atan(self._mul(components[other], sign * cross_sign),
                              self._mul(components[aim], sign))

        if len(ordered) == 1:
            angle, valid = solve(ordered[0], values)
            return {ordered[0]: angle}, valid
        first, second = ordered
        outer, valid = solve(second, values)
        inverse = self._node("composeMatrix", "outerInverse")
        self._angle(self._mul(outer, -1)).connect(inverse.plug("inputRotate" + second.upper()))
        residual = self._node("vectorProduct", "residualDirection")
        residual.plug("operation").set(3)
        vector.plug("output").connect(residual.plug("input1"))
        inverse.plug("outputMatrix").connect(residual.plug("matrix"))
        inner, inner_valid = solve(first, {a: residual.plug("output" + a.upper()) for a in "xyz"})
        return {first: inner, second: outer}, self._mul(valid, inner_valid)

    def _twist(self, decompose, axes):
        """各選択軸へのQuaternion射影からTwist主値を独立に取り出す。"""
        w = decompose.plug("outputQuatW")
        ww = self._mul(w, w)
        outputs, valid = {}, 1.0
        for axis in axes:
            component = decompose.plug("outputQuat" + axis.upper())
            xx = self._mul(component, component)
            y = self._mul(self._mul(component, w), 2)
            x = self._sum(ww, xx, subtract=True)
            outputs[axis], axis_valid = self._atan(y, x)
            valid = self._mul(valid, axis_valid)
        return outputs, valid
