"""既存Aimの出力を1〜2軸へ変換し、元の接続を復元する。"""

import math

import hlib
from hlib.decorators.undo import undoTransaction
from hlib.json import JsonText
from hlib.nodes import Container, Node, Transform
from hlib.plugs import Plug
from hlib.utils.scalarGraph import ScalarGraph


_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
_TAG = "hrigAimAxisConversion"


class AimAxisConversion:
    """標準DGだけで動く変換。管理ノードが生成ノードと復元情報を保持する。

    sourceの全Euler出力から同じ回転行列を再構成するため、部分Eulerの別解切替を
    そのまま採用しない。元の循環接続やWorld Upの特異点を修復するものではない。
    """

    def __init__(self, container):
        """保存済み管理ノードを参照する。

        Args:
            container (str | Node): 本ツールで作成したcontainerまたはnetwork。
        """
        self.container = Node(container)
        if not self.container.hasAttr(_TAG):
            raise ValueError("Aim軸変換の管理ノードではありません。")
        self._graph = ScalarGraph(create_node=self._createNode)
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
        for plug in source.plug("message").destinationsWithConversions():
            if plug.node().type() in ("container", "network") and plug.node().hasAttr(_TAG):
                return cls(plug.node())
        return None

    @classmethod
    @undoTransaction("hrig.AimAxisConversion.convert")
    def create(cls, constraint, axes="x", mode="euler", direction="x",
               reference=(0.0, 0.0, 0.0), half_range=math.radians(85),
               preserve_pose=True, use_container=True):
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
            use_container (bool): Falseなら演算ノードから直接接続し、復元情報をnetworkに保存。

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
            rest_values = source.getRestRotation()
        constraint_settings = cls._captureSettings(source)
        name = source.name().split("|")[-1] + "_axisConversion"
        owner = (Container.create(name=name) if use_container else
                 Node.create("network", name=name, skipSelect=True))
        owner.addAttr(longName=_TAG, attributeType="bool", defaultValue=True)
        for attr, node in (("sourceConstraint", source), ("drivenNode", target)):
            owner.addAttr(longName=attr, attributeType="message")
            node.plug("message").connectTo(owner.plug(attr))
        owner.addAttr(longName="settings", dataType="string")
        owner.plug("settings").set(JsonText.dumps(dict(
            version=1, axes=axes, mode=mode, direction=direction, order=order,
            reference=reference, halfRange=half_range, preservePose=bool(preserve_pose),
            restValues=rest_values, useContainer=bool(use_container),
            constraintSettings=constraint_settings,
            original=original, compound=compound, values=values)))
        graph = cls(owner)
        if not use_container:
            owner.addAttr(longName="generatedNodes", attributeType="message", multi=True)
        compose = graph._node("composeMatrix", "aimRotation")
        source.plug("constraintRotate").connectTo(compose.plug("inputRotate"))
        source.plug("constraintRotateOrder").connectTo(compose.plug("inputRotateOrder"))
        decompose = graph._node("decomposeMatrix", "rotation")
        compose.plug("outputMatrix").connectTo(decompose.plug("inputMatrix"))
        source.plug("constraintRotateOrder").connectTo(decompose.plug("inputRotateOrder"))
        if mode == "euler":
            outputs, valid = graph._euler(decompose, axes, reference, half_range, order)
        elif mode == "direction":
            outputs, valid = graph._direction(compose, axes, direction, order)
        else:
            outputs, valid = graph._twist(decompose, axes)
        # ノードの組み方は生成時のRotate Orderに依存する。変更後は再変換を促す。
        order_valid = graph._node("condition", "orderValid")
        source.plug("constraintRotateOrder").connectTo(order_valid.plug("firstTerm"))
        order_valid.plug("secondTerm").set(order)
        graph._feed(valid, order_valid.plug("colorIfTrueR"))
        order_valid.plug("colorIfFalseR").set(0)
        target_order_valid = graph._node("condition", "targetOrderValid")
        target.plug("rotateOrder").connectTo(target_order_valid.plug("firstTerm"))
        target_order_valid.plug("secondTerm").set(order)
        order_valid.plug("outColorR").connectTo(target_order_valid.plug("colorIfTrueR"))
        target_order_valid.plug("colorIfFalseR").set(0)
        owner.addAttr(longName="valid", attributeType="double", keyable=False)
        target_order_valid.plug("outColorR").connectTo(owner.plug("valid"))
        owner.plug("valid").setFlags(channelBox=True)
        for i, axis in enumerate("xyz"):
            owner.addAttr(longName="output" + axis.upper(), attributeType="doubleAngle")
            if axis not in axes:
                owner.plug("output" + axis.upper()).set(values[i])
                continue
            output = outputs[axis]
            if preserve_pose and mode != "euler":
                output = graph._sum(output, values[i] - output.get())
            graph._angle(output).connectTo(owner.plug("output" + axis.upper()))
        # 結果値を評価してから元接続を外す。基準値に対象回転のライブ接続は作らない。
        for axis in axes:
            owner.plug("output" + axis.upper()).get()
        if compound:
            target.plug("rotate").disconnect(source.plug("constraintRotate"))
        else:
            for axis in original:
                target.plug("rotate" + axis.upper()).disconnect(source.plug(original[axis]))
        for i, axis in enumerate("xyz"):
            destination = target.plug("rotate" + axis.upper())
            if axis in axes:
                output = owner.plug("output" + axis.upper())
                (output if use_container else output.sourceWithConversion()).connectTo(destination)
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
        links = [owner.plug(attr).sourceWithConversion() for attr in ("sourceConstraint", "drivenNode")]
        if any(link is None for link in links):
            raise ValueError("元のAimまたは対象が削除されているため復元できません。")
        source, target = [link.node() for link in links]
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
            if (source.isLocked() or source.isFromReferencedFile() or plug.isLocked()
                    or plug.sourceWithConversion() is not None
                    or (parent is not None and (parent.isLocked() or parent.sourceWithConversion() is not None))):
                raise ValueError("元Aimの設定に入力またはロックがあるため復元できません: " + plug.fullName())
            updates.append((plug, value))
        touched = set(data["axes"]) | set(data["original"])
        for axis in touched:
            dest = target.plug("rotate" + axis.upper())
            expected = owner.plug("output" + axis.upper()) if axis in data["axes"] else None
            if expected is not None and owner.type() == "network":
                expected = expected.sourceWithConversion()
            if (dest.isLocked() or target.plug("rotate").isLocked() or target.isLocked()
                    or target.isFromReferencedFile() or dest.sourceWithConversion() != expected):
                raise ValueError("変換後の接続・ロックが変更されています。復元対象: " + dest.fullName())
        for axis in data["axes"]:
            target.plug("rotate" + axis.upper()).disconnectInput()
        for plug, value in updates:
            plug.set(value)
        for i, axis in enumerate("xyz"):
            if axis in touched:
                target.plug("rotate" + axis.upper()).set(data["values"][i])
        if data["compound"]:
            source.plug("constraintRotate").connectTo(target.plug("rotate"))
        else:
            for axis, attr in data["original"].items():
                source.plug(attr).connectTo(target.plug("rotate" + axis.upper()))
        if owner.type() == "network":
            members = list(owner.plug("generatedNodes").sourceNodes().values())
            if members:
                hlib.delete(members)
        owner.delete()

    @staticmethod
    def _captureSettings(source):
        """元Aimの未接続設定値を記録する。角度はラジアンで保持する。

        Args:
            source (Node): 記録するaimConstraint。

        Returns:
            dict: アトリビュートパスと値。入力で駆動された設定は記録しない。
        """
        settings = {}
        for plug in source.settingPlugs() + source.weightPlugs():
            parent = plug.parent() if plug.isChild() else None
            if plug.sourceWithConversion() is None and (parent is None or parent.sourceWithConversion() is None):
                settings[plug.fullName().split(".", 1)[1]] = plug.get()
        return settings

    @staticmethod
    def _inspect(source, axes):
        """直接の回転出力先を検証し、復元する接続を記録する。

        Args:
            source: 接続・変換・探索の元または先となる対象。
            axes: 処理対象の回転軸。
        """
        targets = {}
        for _, dest in source.rotationConnections():
            if isinstance(dest.node(), Transform) and dest.longName() in (
                    "rotate", "rotateX", "rotateY", "rotateZ"):
                targets[dest.node().uuid()] = dest.node()
        if len(targets) != 1:
            raise ValueError("回転へ直接接続された対象が1つのAimに対応します。間接接続・複数対象は未対応です。")
        target = next(iter(targets.values()))
        if target.isFromReferencedFile() or target.isLocked() or source.isFromReferencedFile() or source.isLocked():
            raise ValueError("参照・ロックされたAimまたは対象は変換できません。")
        compound = target.plug("rotate").sourceWithConversion() == source.plug("constraintRotate")
        original = {}
        for axis in "xyz":
            dest = target.plug("rotate" + axis.upper())
            incoming = dest.sourceWithConversion()
            own = source.plug("constraintRotate" + axis.upper())
            if compound or incoming == own:
                original[axis] = "constraintRotate" + axis.upper()
            elif axis in axes and incoming is not None:
                raise ValueError("別の入力接続は置換しません: " + dest.fullName())
            if (axis in axes or axis in original) and (dest.isLocked() or target.plug("rotate").isLocked()):
                raise ValueError("回転がロックされています: " + dest.fullName())
        return target, original, compound

    def _node(self, kind, role):
        """用途名を付けた標準ノードを所有containerへ作る。

        Args:
            kind: 処理方式または作成するノード型。
            role: 生成ノード名に付ける用途識別子。
        """
        self._serial += 1
        return self._createNode(kind, name="{}{}".format(role, self._serial))

    def _createNode(self, kind, name=None):
        """生成物をcontainerまたはmessage配列へ登録する。

        Args:
            kind (str): 標準ノード型。
            name (str | None): 用途名。

        Returns:
            Node: 登録済みの生成ノード。
        """
        name = self.container.name() + "_" + (name or kind)
        if isinstance(self.container, Container):
            return self.container.createNode(kind, name=name)
        node = Node.create(kind, name=name, skipSelect=True)
        self.container.plug("generatedNodes").appendMessage(node)
        return node

    @staticmethod
    def _feed(value, destination):
        """単位なしの数値またはPlugを入力する。

        Args:
            value: 変換・設定する入力値。
            destination: 接続・変換・探索の元または先となる対象。
        """
        if isinstance(value, Plug):
            value.connectTo(destination)
        else:
            destination.set(value)

    def _sum(self, a, b, subtract=False):
        """単位なしの加減算を作る。

        Args:
            a: 計算する左辺または右辺の値。
            b: 計算する左辺または右辺の値。
            subtract: Trueは減算、Falseは加算。
        """
        return self._graph.sum("sum", a, b, subtract=subtract)

    def _mul(self, a, b):
        """単位なしの乗算を作る。

        Args:
            a: 計算する左辺または右辺の値。
            b: 計算する左辺または右辺の値。
        """
        return self._graph.multiply("product", a, b)

    def _choose(self, a, b, yes, no):
        """a > bで値を選ぶ。

        Args:
            a: 計算する左辺または右辺の値。
            b: 計算する左辺または右辺の値。
            yes: 条件が成立する場合または成立しない場合に選ぶ値。
            no: 条件が成立する場合または成立しない場合に選ぶ値。
        """
        return self._graph.condition("choose", a, b, yes, no)

    def _scalar(self, angle):
        """角度をUI単位に依存しないラジアンの数値へ変換する。

        Args:
            angle: 回転・配置の角度。radians指定はラジアン。
        """
        node = self._node("unitConversion", "radians")
        angle.connectTo(node.plug("input"))
        node.plug("conversionFactor").set(1)
        return node.plug("output")

    def _angle(self, scalar):
        """ラジアンの数値を角度入力へ渡す明示的な単位変換を作る。

        Args:
            scalar: 単位なしの数値または数値を出力するPlug。
        """
        node = self._node("unitConversion", "angle")
        self._feed(scalar, node.plug("input"))
        node.plug("conversionFactor").set(1)
        return node.plug("output")

    def _wrap(self, value):
        """既知の±3pi以内の値を±piへ折り返す。

        Args:
            value: 変換・設定する入力値。
        """
        high = self._choose(value, math.pi, self._sum(value, -2 * math.pi), value)
        return self._choose(-math.pi, high, self._sum(high, 2 * math.pi), high)

    def _euler(self, decompose, axes, reference, width, order):
        """2組の等価解を選択軸の基準距離と範囲で評価する。

        Args:
            decompose: 姿勢を合成または分解するノード。
            axes: 処理対象の回転軸。
            reference: 比較・復元の基準となる値または参照。
            width: 基準解から許可する角度範囲。
            order: Euler回転順序。
        """
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
        """angleBetween.angleと符号判定でatan2を作る。原点は0角・無効。

        Args:
            y: 座標成分またはatan2の入力成分。
            x: 座標成分またはatan2の入力成分。
        """
        length = self._sum(self._mul(x, x), self._mul(y, y))
        valid = self._choose(length, 1e-12, 1, 0)
        angle = self._node("angleBetween", "signedAngle")
        angle.plug("vector1").set((1, 0, 0))
        angle.plug("vector2").set((0, 0, 0))
        self._choose(valid, 0.5, x, 1).connectTo(angle.plug("vector2X"))
        self._choose(valid, 0.5, y, 0).connectTo(angle.plug("vector2Y"))
        radians = self._scalar(angle.plug("angle"))
        return self._choose(0, y, self._mul(radians, -1), radians), valid

    def _direction(self, compose, axes, direction, order):
        """全Aim姿勢の指定方向を、回転順に沿うヒンジまたは2軸角へ再解する。

        Args:
            compose: 姿勢を合成または分解するノード。
            axes: 処理対象の回転軸。
            direction: 姿勢から取り出す方向ベクトル。
            order: Euler回転順序。
        """
        aim = direction[-1]
        sign = -1 if direction.startswith("-") else 1
        vector = self._node("vectorProduct", "aimDirection")
        vector.plug("operation").set(3)
        vector.plug("input1" + aim.upper()).set(sign)
        compose.plug("outputMatrix").connectTo(vector.plug("matrix"))
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
        self._angle(self._mul(outer, -1)).connectTo(inverse.plug("inputRotate" + second.upper()))
        residual = self._node("vectorProduct", "residualDirection")
        residual.plug("operation").set(3)
        vector.plug("output").connectTo(residual.plug("input1"))
        inverse.plug("outputMatrix").connectTo(residual.plug("matrix"))
        inner, inner_valid = solve(first, {a: residual.plug("output" + a.upper()) for a in "xyz"})
        return {first: inner, second: outer}, self._mul(valid, inner_valid)

    def _twist(self, decompose, axes):
        """各選択軸へのQuaternion射影からTwist主値を独立に取り出す。

        Args:
            decompose: 姿勢を合成または分解するノード。
            axes: 処理対象の回転軸。
        """
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
