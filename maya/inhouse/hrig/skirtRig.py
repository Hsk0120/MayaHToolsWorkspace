"""少数の放射状ドライバーで、多数のスカート骨を制御する。"""

from maya import cmds

from functools import partial
import math
import re

import hlib

from hrig.setups.radialWeights import RadialWeights
from hlib.decorators.undo import undo_transaction


class SkirtRig:
    """4/8方向の骨と標準parentConstraintを所有する独立モジュール。"""

    _jobs = {}
    _busy = False

    def __init__(self, root):
        """シーン内の保存済みモジュールを参照する。

        Args:
            root (str | Node): スカートルート。
        """
        self.root = hlib.getNode(root)
        if not self.root.has_attribute("hrigSkirtDefinition"):
            raise ValueError("Not an hrig skirt module")

    @classmethod
    @undo_transaction("hrig.SkirtRig.create")
    def create(
        cls,
        name="skirt01",
        driver_count=4,
        chain_count=16,
        joints_per_chain=3,
        radius=3.0,
        length=5.0,
    ):
        """XZ円周上に、下向きのドライバー列と変形骨列を生成する。

        Args:
            name (str): 一意なモジュール名。
            driver_count (int): 4または8方向。
            chain_count (int): 円周に置く変形骨列数。方向数以上。
            joints_per_chain (int): 一列の骨数。末端を含み2以上。
            radius (float): 現在のシーン単位での半径。
            length (float): 現在のシーン単位での縦の長さ。

        Returns:
            SkirtRig: 操作用参照。

        Note:
            骨長を維持する回転のみのconstraint。スキンや布シミュレーションは作らない。
        """
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("Use an unnamespaced Maya identifier")
        if cmds.objExists(name) or [item.name() for item in hlib.ls(name + "_*")]:
            raise ValueError("Module name or prefix already exists: " + name)
        if (
            isinstance(driver_count, bool)
            or not isinstance(driver_count, int)
            or driver_count not in (4, 8)
        ):
            raise ValueError("driver_count must be 4 or 8")
        if (
            isinstance(chain_count, bool)
            or not isinstance(chain_count, int)
            or not driver_count <= chain_count <= 256
        ):
            raise ValueError("chain_count must be between driver_count and 256")
        if (
            isinstance(joints_per_chain, bool)
            or not isinstance(joints_per_chain, int)
            or not 2 <= joints_per_chain <= 32
        ):
            raise ValueError("joints_per_chain must be between 2 and 32")
        if not all(math.isfinite(v) and v > 0 for v in (radius, length)):
            raise ValueError("radius and length must be positive finite values")
        root = hlib.createNode("transform", name=name, skipSelect=True)
        root.add_attribute(long_name="hrigSkirtDefinition", data_type="string")
        root.plug("hrigSkirtDefinition").set(
            hlib.json.JsonText.dumps(
                dict(
                    version=1,
                    driver_count=driver_count,
                    chain_count=chain_count,
                    joints_per_chain=joints_per_chain,
                    radius=radius,
                    length=length,
                )
            )
        )
        root.set_attribute_flags(["hrigSkirtDefinition"], locked=True)
        for attr in ("drivers", "followers", "constraints", "graphs"):
            root.add_attribute(long_name=attr, attribute_type="message", multi=True)
        for attr in ("driverGroup", "followerGroup", "restGroup"):
            root.add_attribute(long_name=attr, attribute_type="message")
        for attr, value, low, high in (("blend", 1, 0, 1), ("falloff", 1, 0.1, 8)):
            root.add_attribute(
                long_name=attr,
                attribute_type="double",
                default_value=value,
                minValue=low,
                maxValue=high,
                keyable=True,
            )
        root.add_attribute(long_name="enabled", attribute_type="bool", default_value=True, keyable=False)
        root.add_attribute(
            long_name="lod",
            attribute_type="enum",
            enumName="Low:Full",
            default_value=1,
            keyable=False,
        )
        root.set_attribute_flags(["enabled", "lod"], channel_box=True)
        rig = cls(root)
        groups = {}
        for role in ("driver", "follower", "rest"):
            group = hlib.createNode(
                "transform", name=name + "_" + role + "_grp", parent=root, skipSelect=True
            )
            group.plug("message").connect(root.plug(role + "Group"))
            groups[role] = group
        groups["rest"].plug("visibility").set(False)
        spacing = length / (joints_per_chain - 1)
        for role, count, registry in (
            ("driver", driver_count, "drivers"),
            ("follower", chain_count, "followers"),
        ):
            for column in range(count):
                angle = math.tau * column / count
                prefix = "{}_{}{:02d}".format(name, role, column + 1)
                offset = hlib.createNode(
                    "transform", name=prefix + "_grp", parent=groups[role], skipSelect=True
                )
                offset.plug("translate").set(
                    (radius * math.cos(angle), 0, radius * math.sin(angle))
                )
                offset.plug("rotateY").set(hlib.utils.units.angle_to_ui(-angle))
                parent = offset
                for depth in range(joints_per_chain):
                    joint = hlib.createNode(
                        "joint",
                        name=prefix + "_{:02d}_jnt".format(depth + 1),
                        parent=parent,
                        skipSelect=True,
                    )
                    joint.plug("translateY").set(-spacing if depth else 0)
                    joint.plug("segmentScaleCompensate").set(False)
                    joint.plug("radius").set(0.18 if role == "follower" else 0.35)
                    joint.plug("message").connect(
                        root.plug("{}[{}]".format(registry, column * joints_per_chain + depth))
                    )
                    if role == "driver":
                        from hrig.setups import ControlShape

                        ControlShape.circle(joint, radius=0.45, normal=(0, 1, 0), color=17)
                        joint.set_attribute_flags(
                            ["translate", "scale", "visibility"], locked=True, keyable=False
                        )
                    parent = joint
        drivers, followers = rig.driver_chains(), rig.chains()
        for column, chain in enumerate(followers):
            angle = math.tau * column / chain_count
            indices, _ = RadialWeights.directions(angle, driver_count)
            graph = RadialWeights.create(
                angle, driver_count, "{}_weights{:02d}".format(name, column + 1)
            )
            graph.container.plug("message").connect(root.plug("graphs[{}]".format(column)))
            for attr in ("blend", "falloff"):
                root.plug(attr).connect(graph.container.plug(attr))
            for depth, joint in enumerate(chain):
                rest = hlib.createNode(
                    "transform", name=joint.name() + "_rest", parent=groups["rest"], skipSelect=True
                )
                rest.plug("translate").set(
                    (radius * math.cos(angle), -spacing * depth, radius * math.sin(angle))
                )
                rest.plug("rotateY").set(hlib.utils.units.angle_to_ui(-angle))
                constraint = hlib.addConstraint(
                    [rest, drivers[indices[0]][depth], drivers[indices[1]][depth]],
                    joint.full_name(),
                    maintainOffset=True,
                    skipTranslate=["x", "y", "z"],
                    name=joint.name() + "_parentConstraint",
                )
                constraint.plug("interpType").set(2)  # 最短経路。履歴依存のNo Flipは使わない。
                aliases = constraint.weight_plugs()
                for output, alias in zip(("restWeight", "weightA", "weightB"), aliases):
                    graph.container.plug(output).connect(alias)
                constraint.add_attribute(long_name="hrigDriven", attribute_type="message")
                joint.plug("message").connect(constraint.plug("hrigDriven"))
                constraint.plug("message").connect(
                    root.plug("constraints[{}]".format(column * joints_per_chain + depth))
                )
        from .channel_controls import install

        install()
        return rig

    def _members(self, attr):
        """message配列を保存順に解決する。

        Args:
            attr (str): 配列属性名。

        Returns:
            list[Node]: 参照先ノード。
        """
        return list(self.root.plug(attr).source_nodes().values())

    def _chains(self, attr):
        """骨の参照配列を列単位に区切る。

        Args:
            attr (str): 保存配列。

        Returns:
            list[list[Node]]: 円周順・根元から先端順の骨。
        """
        size = hlib.json.JsonText.loads(self.root.plug("hrigSkirtDefinition").get())[
            "joints_per_chain"
        ]
        members = self._members(attr)
        return [members[i : i + size] for i in range(0, len(members), size)]

    def chains(self):
        """円周順の変形骨列を取得する。

        Returns:
            list[list[Node]]: 変形骨。
        """
        return self._chains("followers")

    def driver_chains(self):
        """円周順のドライバー骨列を取得する。

        Returns:
            list[list[Node]]: 回転操作する骨。
        """
        return self._chains("drivers")

    def joints(self):
        """スキニング対象の変形骨だけを取得する。

        Returns:
            list[str]: 円周順・根元から先端順のフルパス。
        """
        from .tweakLayer import TweakLayer

        return (
            list(TweakLayer(self).joints())
            + [node.full_name() for node in self._members("followers")]
            + list(self.follow_joints())
        )

    def add_follow(self, identifier, joint=None, mode="full", axis="y", ratio=0.5):
        """指定骨へ回転追従補助骨を追加する。

        Args:
            identifier (str): 一意なID。
            joint (str | Node | None): 入力骨。省略時は先頭ドライバーの根元。
            mode (str): full/twist/swing。
            axis (str): Twist軸x/y/z。スカートの長手軸はy。
            ratio (float): 0〜1の割合。

        Returns:
            str: 補助骨の完全名。
        """
        from .followLayer import FollowLayer

        return FollowLayer(self).add(
            identifier, joint or self.driver_chains()[0][0], mode, axis, ratio
        )

    def follow_joints(self, identifier=None):
        """追従補助骨を取得する。

        Args:
            identifier (str | None): 省略時は全て。

        Returns:
            tuple[str]: 骨の完全名。
        """
        from .followLayer import FollowLayer

        return FollowLayer(self).joints(identifier)

    def follow_settings(self, identifier):
        """追従割合と成分の設定グループを取得する。

        Args:
            identifier (str): 登録済みID。

        Returns:
            Node: 設定グループ。
        """
        from .followLayer import FollowLayer

        return FollowLayer(self).groups()[identifier]

    def lod(self):
        """保存済みのLODを取得する。

        Returns:
            int: 0=Low、1=Full。
        """
        return int(self.root.plug("lod").get())

    def add_spring(self, driver_index=0):
        """指定ドライバー列に揺れ用の出力骨列を追加する。

        Args:
            driver_index (int): 列番号。

        Returns:
            Node: 設定グループ。反映にはbake_springが必要。
        """
        from .secondaryLayer import SecondaryLayer

        return SecondaryLayer(self).add(driver_index)

    def bake_spring(self, driver_index=0, start=None, end=None):
        """揺れを計算し、標準カーブへ焼き込む。

        Args:
            driver_index (int): 列番号。
            start (int | None): 開始フレーム。省略時は再生範囲。
            end (int | None): 終了フレーム。

        Returns:
            Node: 設定グループ。
        """
        from .secondaryLayer import SecondaryLayer

        return SecondaryLayer(self).bake(driver_index, start, end)

    def add_pose_correction(self, driver_index, drivers, poses, values, scales):
        """複数入力ポーズからドライバー列の回転補正を追加する。

        Args:
            driver_index (int): 補正する列番号。
            drivers (Sequence): 元ドライバーの回転属性。
            poses (Sequence): 登録入力、度。
            values (Sequence): 各骨XYZの補正回転、度。
            scales (Sequence): 入力距離スケール。

        Returns:
            PoseRbf: 補間グラフ。
        """
        from .secondaryLayer import SecondaryLayer

        return SecondaryLayer(self).add_pose(driver_index, drivers, poses, values, scales)

    def layer_enabled(self, layer="radial"):
        """放射状制御の使用設定を取得する。

        Args:
            layer (str): radialのみ。

        Returns:
            bool: 使用設定。
        """
        if layer in ("follow", "spring", "pose"):
            return (
                bool(self.root.plug("hrigEnabled_" + layer).get())
                if self.root.has_attribute("hrigEnabled_" + layer)
                else True
            )
        if layer != "radial":
            raise ValueError("Unknown skirt layer: " + layer)
        return bool(self.root.plug("enabled").get())

    @undo_transaction("hrig.SkirtRig.set_layer_enabled")
    def set_layer_enabled(self, layer, enabled):
        """使用設定を変更して評価接続を更新する。

        Args:
            layer (str): radialのみ。
            enabled (bool): 使用するか。
        """
        self.layer_enabled(layer)
        attr = "enabled" if layer == "radial" else "hrigEnabled_" + layer
        if not self.root.has_attribute(attr):
            self.root.add_attribute(long_name=attr, attribute_type="bool", default_value=True)
            self.root.set_attribute_flags([attr], channel_box=True)
        self.root.plug(attr).set(bool(enabled))
        self.update()

    @undo_transaction("hrig.SkirtRig.set_lod")
    def set_lod(self, value):
        """構成用LODを変更する。アニメーション切替用ではない。

        Args:
            value (int): 0または1。
        """
        if value not in (0, 1):
            raise ValueError("lod must be 0 or 1")
        self.root.plug("lod").set(value)
        self.update()

    @undo_transaction("hrig.SkirtRig.update")
    def update(self):
        """無効時は出力を切断し、変形骨を作成時の姿勢へ戻す。"""
        active = self.layer_enabled() and self.lod() == 1
        for constraint in self._members("constraints"):
            joint = constraint.plug("hrigDriven").source().node
            for axis in "XYZ":
                source = constraint.plug("constraintRotate" + axis)
                target = joint.plug("rotate" + axis)
                connected = target.source()
                if connected is not None and connected.mplug() != source.mplug():
                    raise ValueError("Skirt output was replaced: " + target.name())
                if active and connected is None:
                    source.connect(target)
                elif not active and connected is not None:
                    source.disconnect(target)
                    target.set(0)
            state = 0 if active else 2
            if constraint.plug("nodeState").get() != state:
                constraint.plug("nodeState").set(state)
        from .followLayer import FollowLayer

        FollowLayer(self).update()
        from .tweakLayer import TweakLayer

        TweakLayer(self).update()
        from .secondaryLayer import SecondaryLayer

        SecondaryLayer(self).update()

    @classmethod
    def refresh_jobs(cls):
        """GUIシーンの属性監視を復元する。バッチは明示APIで更新する。"""
        if cmds.about(batch=True):
            return
        for key, jobs in list(cls._jobs.items()):
            if not [item.name() for item in hlib.ls(key)] or not jobs.exists():
                jobs.stop()
                del cls._jobs[key]
        for attr in [
            item.full_name() for item in hlib.ls("*.hrigSkirtDefinition", recursive=True)
        ] or []:
            rig = cls(attr.rsplit(".", 1)[0])
            key = rig.root.uuid()
            if key in cls._jobs:
                continue
            jobs = hlib.general.ScriptJobs()
            attrs = ["enabled", "lod"]
            for kind in ("follow", "spring", "pose"):
                if rig.root.has_attribute("hrigEnabled_" + kind):
                    attrs.append("hrigEnabled_" + kind)
            for name in attrs:
                jobs.add(
                    name,
                    attribute=rig.root.plug(name),
                    callback=partial(cls._changed, key),
                    kill_with_scene=True,
                    compress_undo=True,
                )
            cls._jobs[key] = jobs

    @classmethod
    def _changed(cls, key):
        """改名後もUUIDから設定変更を適用する。

        Args:
            key (str): ルートUUID。
        """
        roots = [item.full_name() for item in hlib.ls(key, long=True)] or []
        if cls._busy or not roots:
            return
        cls._busy = True
        try:
            rig = cls(roots[0])
            # Undoで既に接続が復元された場合は、空のUndoチャンクも開かない。
            # 新しい編集として記録するとRedo履歴を失うため、問い合わせだけで終える。
            active = rig.layer_enabled() and rig.lod() == 1
            for constraint in rig._members("constraints"):
                joint = constraint.plug("hrigDriven").source().node
                if constraint.plug("nodeState").get() != (0 if active else 2) or any(
                    (joint.plug("rotate" + axis).source() is not None) != active for axis in "XYZ"
                ):
                    rig.update()
                    break
            else:
                from .followLayer import FollowLayer

                active = rig.layer_enabled("follow") and rig.lod() == 1
                for group in FollowLayer(rig).groups().values():
                    bone = group.plug("joint").source().node
                    if (bone.plug("offsetParentMatrix").source() is not None) != active:
                        rig.update()
                        break
                from .secondaryLayer import SecondaryLayer

                if SecondaryLayer(rig).needs_update():
                    rig.update()
        finally:
            cls._busy = False

    @undo_transaction("hrig.SkirtRig.delete")
    def delete(self):
        """所有DGと階層を削除する。スキン使用中なら拒否する。"""
        for joint in self.joints():
            if hlib.getNode(joint).connections(type="skinCluster"):
                raise ValueError("Unbind the skirt before deleting its module")
        for graph in self._members("graphs"):
            hlib.delete(graph)
        if self.root.has_attribute("hrigOwned"):
            for node in self._members("hrigOwned"):
                if cmds.objExists(node.full_name()):
                    hlib.delete(node)
        hlib.delete(self.root)
