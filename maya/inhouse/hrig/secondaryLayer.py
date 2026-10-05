"""スカートの手付けドライバーへ、揺れとポーズ補正を重ねる。"""

from maya import cmds

import math

import hlib

from hlib.utils.dampedSpring import DampedSpring
from hrig.setups.poseRbf import PoseRbf
from hlib.decorators.undo import undoTransaction


class SecondaryLayer:
    """入力骨を保持し、別の出力骨列をconstraintへ供給するレイヤー。"""

    def __init__(self, rig):
        """スカートモジュールを保持する。

        Args:
            rig (SkirtRig): 所属モジュール。
        """
        self.rig = rig

    def groups(self):
        """登録済みドライバー列と設定グループを取得する。

        Returns:
            dict[int, Node]: 列番号と設定グループ。
        """
        root = self.rig.root
        if not root.hasAttr("secondaryGroups"):
            return {}
        return root.plug("secondaryGroups").sourceNodes()

    @staticmethod
    def _members(group, attr):
        """message配列を順に解決する。

        Args:
            group (Node): 保存先。
            attr (str): 属性。

        Returns:
            list[Node]: 参照先。
        """
        return list(group.plug(attr).sourceNodes().values())

    @staticmethod
    def _node(owner, kind, suffix):
        """計算ノードを所有containerへ登録する。

        Args:
            owner (Node): 所有container。
            kind (str): ノード型。
            suffix (str): 用途。

        Returns:
            Node: 生成ノード。
        """
        return hlib.nodes.Container(owner).createNode(kind, name=owner.name() + "_" + suffix)

    @undoTransaction("hrig.SecondaryLayer.add")
    def add(self, driver_index=0):
        """手付け骨とは別に出力骨列と設定を作る。既存なら再利用する。

        Args:
            driver_index (int): 円周ドライバー列の0始まり番号。

        Returns:
            Node: 設定グループ。
        """
        if driver_index in self.groups():
            return self.groups()[driver_index]
        chains = self.rig.driver_chains()
        if type(driver_index) is not int or not 0 <= driver_index < len(chains):
            raise ValueError("Invalid driver index")
        sources = chains[driver_index]
        root = self.rig.root
        stem = root.name() + "_secondary{:02d}".format(driver_index + 1)
        if [item.name() for item in hlib.ls(stem + "_*")]:
            raise ValueError("Secondary names already exist")
        parent = [
            item.fullName()
            for item in [
                hlib.getNode(value)
                for value in (
                    cmds.listRelatives(sources[0].fullName(), parent=True, fullPath=True) or []
                )
            ]
        ][0]
        group = hlib.createNode("transform", name=stem + "_grp", parent=parent, skipSelect=True)
        owner = hlib.nodes.Container.create(name=stem + "_graph")
        group.addAttr(longName="graph", attributeType="message")
        owner.plug("message").connectTo(group.plug("graph"))
        group.addAttr(longName="baked", attributeType="bool", defaultValue=False)
        group.addAttr(longName="bakeInfo", dataType="string").set("{}")
        group.addAttr(longName="poseGraph", attributeType="message")
        for name, value, low, high in (
            ("intensity", 1, 0, 1),
            ("frequency", 3, 0.01, 30),
            ("damping", 0.5, 0, 2),
            ("angleLimit", 45, 0.01, 170),
            ("poseIntensity", 1, 0, 1),
        ):
            group.addAttr(
                longName=name,
                attributeType="double",
                defaultValue=value,
                minValue=low,
                maxValue=high,
                keyable=name.endswith("ntensity"),
            )
            group.setAttributeFlags([name], channelBox=True)
        for attr in ("sources", "targets", "blends", "poses", "curves", "poseWeights"):
            group.addAttr(longName=attr, attributeType="message", multi=True)
        target_parent = group
        for index, source in enumerate(sources):
            target = hlib.createNode(
                "joint",
                name=stem + "_{:02d}_jnt".format(index + 1),
                parent=target_parent,
                skipSelect=True,
            )
            target.plug("segmentScaleCompensate").set(False)
            target.plug("radius").set(0.25)
            for attr in ("translate", "jointOrient", "rotateAxis", "rotateOrder"):
                source.plug(attr).connectTo(target.plug(attr))
            blend = self._node(owner, "pairBlend", "blend{}".format(index))
            blend.plug("rotInterpolation").set(1)
            source.plug("rotate").connectTo(blend.plug("inRotate1"))
            base = self._node(owner, "composeMatrix", "base{}".format(index))
            blend.plug("outRotate").connectTo(base.plug("inputRotate"))
            source.plug("rotateOrder").connectTo(base.plug("inputRotateOrder"))
            pose = self._node(owner, "composeMatrix", "pose{}".format(index))
            combine = self._node(owner, "multMatrix", "combine{}".format(index))
            pose.plug("outputMatrix").connectTo(combine.plug("matrixIn")[0])
            base.plug("outputMatrix").connectTo(combine.plug("matrixIn")[1])
            decompose = self._node(owner, "decomposeMatrix", "rotation{}".format(index))
            combine.plug("matrixSum").connectTo(decompose.plug("inputMatrix"))
            source.plug("rotateOrder").connectTo(decompose.plug("inputRotateOrder"))
            decompose.plug("outputRotate").connectTo(target.plug("rotate"))
            for attr, node in (
                ("sources", source),
                ("targets", target),
                ("blends", blend),
                ("poses", pose),
            ):
                node.plug("message").connectTo(group.plug(attr)[index])
            for axis_index, axis in enumerate("XYZ"):
                curve = self._node(owner, "animCurveTA", "cache{}_{}".format(index, axis))
                hlib.getPlug("time1.outTime").connectTo(curve.plug("input"))
                curve.plug("message").connectTo(
                    group.plug("curves")[index * 3 + axis_index]
                )
            target_parent = target
        for attr in ("secondaryGroups", "hrigOwned"):
            if not root.hasAttr(attr):
                root.addAttr(longName=attr, attributeType="message", multi=True)
        group.plug("message").connectTo(root.plug("secondaryGroups")[driver_index])
        for node in (group, owner):
            root.plug("hrigOwned").appendMessage(node)
        for kind in ("spring", "pose"):
            attr = "hrigEnabled_" + kind
            if not root.hasAttr(attr):
                root.addAttr(longName=attr, attributeType="bool", defaultValue=True)
            root.setAttributeFlags([attr], channelBox=True)
        self.update()
        from .skirtRig import SkirtRig

        jobs = SkirtRig._jobs.pop(root.uuid(), None)
        if jobs is not None:
            jobs.stop()
        SkirtRig.refresh_jobs()
        return group

    @undoTransaction("hrig.SecondaryLayer.bake")
    def bake(self, driver_index=0, start=None, end=None):
        """元のローカル回転を順次サンプルし、所有カーブへ揺れを焼き込む。

        Args:
            driver_index (int): 列番号。
            start (int | None): 計算開始フレーム。省略時は再生開始。
            end (int | None): 計算終了フレーム。省略時は再生終了。

        Returns:
            Node: 設定グループ。

        Note:
            元のアニメーションは変更しない。設定・入力を変えたら再ベイクする。
            ローカルEuler各成分の小振幅ばね。親移動による慣性と衝突は未対応。
        """
        start = cmds.playbackOptions(query=True, minTime=True) if start is None else start
        end = cmds.playbackOptions(query=True, maxTime=True) if end is None else end
        if (
            not all(math.isfinite(v) and v == int(v) for v in (start, end))
            or not 1 <= end - start <= 20000
        ):
            raise ValueError("Use an integer range of 2..20001 frames")
        group = self.add(driver_index)
        sources = self._members(group, "sources")
        frames = list(range(int(start), int(end) + 1))
        original = cmds.currentTime(query=True)
        rows = []
        try:
            for frame in frames:
                cmds.currentTime(frame, update=True)
                row = [
                    math.degrees(hlib.utils.units.angleFromUi(v))
                    for source in sources
                    for v in hlib.getAttr(source.plug("rotate"))
                ]
                if rows:
                    row = [
                        v + 360 * round((previous - v) / 360) for v, previous in zip(row, rows[-1])
                    ]
                rows.append(row)
            settings = {
                name: group.plug(name).get() for name in ("frequency", "damping", "angleLimit")
            }
            interval = hlib.utils.units.secondsPerFrame()
            solved = DampedSpring.solve(
                rows, interval, settings["frequency"], settings["damping"], settings["angleLimit"]
            )
            for column, curve in enumerate(self._members(group, "curves")):
                # 全キーを先に消すとMayaが空のanimCurve自体を削除することがある。
                # 新しい範囲を上書きしてから、不要になった旧キーだけを消す。
                old_times = set(cmds.keyframe(curve.fullName(), query=True, timeChange=True) or [])
                for frame, row in zip(frames, solved):
                    value = hlib.utils.units.angleToUi(math.radians(row[column]))
                    cmds.setKeyframe(
                        curve.fullName(),
                        time=frame,
                        value=value,
                        inTangentType="linear",
                        outTangentType="linear",
                    )
                for time in old_times - set(frames):
                    cmds.cutKey(curve.fullName(), time=(time, time), clear=True)
            group.plug("baked").set(True)
            group.plug("bakeInfo").set(
                hlib.json.JsonText.dumps(
                    dict(start=start, end=end, secondsPerFrame=interval, **settings)
                )
            )
            self.update()
        finally:
            cmds.currentTime(original, update=True)
        return group

    @undoTransaction("hrig.SecondaryLayer.add_pose")
    def add_pose(self, driver_index, drivers, poses, values, scales):
        """多入力ポーズから出力列の各骨XYZ回転補正を生成する。

        Args:
            driver_index (int): 補正する列。
            drivers (Sequence[str | Plug]): 元の手付け骨の数値入力。
            poses (Sequence[Sequence[float]]): 登録入力。
            values (Sequence[Sequence[float]]): 一列の骨数×3の補正角度、度。
            scales (Sequence[float]): 入力距離スケール。

        Returns:
            PoseRbf: 出力値を編集できる計算オブジェクト。
        """
        group = self.add(driver_index)
        if group.plug("poseGraph").sourceWithConversion() is not None:
            raise ValueError("Pose graph already exists; edit its set_values instead")
        count = len(self._members(group, "sources")) * 3
        if not values or any(len(row) != count for row in values):
            raise ValueError("Use three output angles per joint")
        # フィードバックを避けるため入力は元の手付けドライバーの回転だけに限定する。
        allowed = {node.uuid() for chain in self.rig.driver_chains() for node in chain}
        for driver in drivers:
            plug = hlib.getPlug(driver)
            if plug.node().uuid() not in allowed or plug.longName() not in ("rotateX", "rotateY", "rotateZ"):
                raise ValueError("Use original driver joint rotation attributes")
        graph = PoseRbf.create(drivers, poses, values, scales, name=group.name() + "_poses")
        graph.container.plug("message").connectTo(group.plug("poseGraph"))
        root = self.rig.root
        root.plug("hrigOwned").appendMessage(graph.container)
        owner = group.plug("graph").sourceWithConversion().node()
        for index in range(count):
            weight = self._node(owner, "multDoubleLinear", "poseWeight{}".format(index))
            graph.container.plug("outputs")[index].connectTo(weight.plug("input1"))
            group.plug("poseIntensity").connectTo(weight.plug("input2"))
            convert = self._node(owner, "unitConversion", "poseRadians{}".format(index))
            weight.plug("output").connectTo(convert.plug("input"))
            convert.plug("conversionFactor").set(math.pi / 180)
            convert.plug("message").connectTo(group.plug("poseWeights")[index])
        self.update()
        return graph

    def _route(self, group, active):
        """constraintの参照を手付け骨または出力骨へ切り替える。

        Args:
            group (Node): 設定。
            active (bool): 追加レイヤーが有効か。
        """
        sources, targets = self._members(group, "sources"), self._members(group, "targets")
        mapping = {
            old.uuid(): new
            for old, new in zip(sources if active else targets, targets if active else sources)
        }
        for constraint in self.rig._members("constraints"):
            connections = [
                hlib.getPlug(value)
                for value in (
                    cmds.listConnections(
                        constraint.fullName(),
                        source=True,
                        destination=False,
                        plugs=True,
                        connections=True,
                    )
                    or []
                )
            ] or []
            for destination, source in zip(connections[::2], connections[1::2]):
                if source.node().uuid() in mapping:
                    destination.disconnect(source)
                    mapping[source.node().uuid()].plug(source.attrName()[1:]).connectTo(destination)

    def update(self):
        """停止レイヤーの入力を切断し、両方停止なら元の骨へ接続を戻す。"""
        for group in self.groups().values():
            spring = (
                self.rig.lod() == 1
                and self.rig.layer_enabled("spring")
                and group.plug("baked").get()
            )
            pose = (
                self.rig.lod() == 1
                and self.rig.layer_enabled("pose")
                and group.plug("poseGraph").sourceWithConversion() is not None
            )
            curves = self._members(group, "curves")
            for index, blend in enumerate(self._members(group, "blends")):
                weight = blend.plug("weight")
                if weight.sourceWithConversion() is not None:
                    weight.disconnect(weight.sourceWithConversion())
                if spring:
                    group.plug("intensity").connectTo(weight)
                else:
                    weight.set(0)
                for axis_index, axis in enumerate("XYZ"):
                    target = blend.plug("inRotate" + axis + "2")
                    if target.sourceWithConversion() is not None:
                        target.disconnect(target.sourceWithConversion())
                    curve = curves[index * 3 + axis_index]
                    curve.plug("nodeState").set(0 if spring else 2)
                    if spring:
                        curve.plug("output").connectTo(target)
            weights = self._members(group, "poseWeights")
            for index, compose in enumerate(self._members(group, "poses")):
                for axis_index, axis in enumerate("XYZ"):
                    target = compose.plug("inputRotate" + axis)
                    if target.sourceWithConversion() is not None:
                        target.disconnect(target.sourceWithConversion())
                    if pose:
                        weights[index * 3 + axis_index].plug("output").connectTo(target)
                    else:
                        target.set(0)
            self._route(group, spring or pose)
            group.plug("visibility").set(False)

    def needs_update(self):
        """属性監視で空のUndo更新を避けるため実接続との差を調べる。

        Returns:
            bool: 評価接続の更新が必要ならTrue。
        """
        for group in self.groups().values():
            spring = (
                self.rig.lod() == 1
                and self.rig.layer_enabled("spring")
                and group.plug("baked").get()
            )
            pose = (
                self.rig.lod() == 1
                and self.rig.layer_enabled("pose")
                and group.plug("poseGraph").sourceWithConversion() is not None
            )
            if (self._members(group, "blends")[0].plug("weight").sourceWithConversion() is not None) != bool(
                spring
            ):
                return True
            if (self._members(group, "poses")[0].plug("inputRotateX").sourceWithConversion() is not None) != bool(
                pose
            ):
                return True
        return False
