"""レイヤーエディター用のサンプル構成を生成する。"""

from maya import cmds

import hlib
from hlib.decorators.undo import undo_transaction


class SampleBuilder:
    """UIとテストから共通に使う、サンプル生成の入口。"""

    @staticmethod
    @undo_transaction("hrig.SampleBuilder.module")
    def module(name, demo=False):
        """独立した3関節モジュールを生成する。

        Args:
            name (str): 新規の一意なルート名。
            demo (bool): Trueなら高低メッシュ付きの全体デモ。

        Returns:
            LimbRig: 生成した部位。
        """
        if demo:
            from .examples.limb_demo import build_demo

            return build_demo(name=name)["rig"]
        from . import build_limb, limb_definition

        rig = build_limb(limb_definition(name))
        rig.set_layer_enabled("soft", False)
        rig.set_layer_enabled("helper", False)
        for role, control in rig.controls().items():
            from hrig.setups import ControlShape

            ControlShape.circle(control, radius=0.45, color=17 if role.startswith("fk") else 6)
        return rig

    @staticmethod
    def next_id(existing, prefix):
        """登録済みIDと重複しないサンプル名を取得する。

        Args:
            existing (Container[str]): 登録済み識別子。
            prefix (str): 接頭辞。

        Returns:
            str: 一意なID。
        """
        index = 1
        while prefix + str(index) in existing:
            index += 1
        return prefix + str(index)

    @staticmethod
    @undo_transaction("hrig.SampleBuilder.layer")
    def layer(rig, kind, count=3, component="swingZ", axis="x", ratio=0.5):
        """選択部位へサンプルを追加し、設定先を返す。

        Args:
            rig (LimbRig): 所属部位。
            kind (str): twist/bend/driven/foot/soft/helper。
            count (int): ツイスト骨数。
            component (str): SDKの入力成分。
            axis (str): SDKのTwist軸。
            ratio (float): 回転追従の割合。

        Returns:
            str: 選択・設定するノード。
        """
        if kind == "stretch":
            group = rig.add_stretch()
            rig.set_layer_enabled("stretch", True)
            return group.full_name()
        if kind == "spring":
            group = rig.bake_spring(0)
            rig.set_layer_enabled("spring", True)
            return group.full_name()
        if kind == "pose":
            joint = rig.driver_chains()[0][0]
            size = len(rig.driver_chains()[0]) * 3
            values = [[0.0] * size for _ in range(4)]
            values[1][2], values[2][0] = 20, -15
            values[3][0], values[3][2] = -20, 25
            graph = rig.add_pose_correction(
                0,
                [joint.plug("rx"), joint.plug("rz")],
                [[0, 0], [60, 0], [0, 60], [60, 60]],
                values,
                [60, 60],
            )
            rig.set_layer_enabled("pose", True)
            return graph.container.full_name()
        if kind in ("followTwist", "followSwing", "followHalf"):
            from .followLayer import FollowLayer

            identifier = SampleBuilder.next_id(FollowLayer(rig).groups(), kind)
            mode = {"followTwist": "twist", "followSwing": "swing", "followHalf": "full"}[kind]
            rig.add_follow(identifier, mode=mode, axis=axis, ratio=ratio)
            rig.set_layer_enabled("follow", True)
            return rig.follow_settings(identifier).full_name()
        if kind == "twist":
            from .twistLayer import TwistLayer

            identifier = SampleBuilder.next_id(TwistLayer(rig).segments(), "upper")
            rig.add_twist(identifier, *rig.joints()[:2], count=count)
            target = TwistLayer(rig).segments()[identifier].full_name()
        elif kind == "bend":
            from .bendLayer import BendLayer

            identifier = SampleBuilder.next_id(BendLayer(rig).groups(), "bend")
            rig.add_bend(identifier)
            target = rig.bend_settings(identifier).full_name()
        elif kind == "driven":
            from .drivenLayer import DrivenLayer

            identifier = SampleBuilder.next_id(DrivenLayer(rig).graphs(), "sdk")
            group_name = rig.node_name("drivenSet").removesuffix("_set") + "_" + identifier + "_grp"
            if cmds.objExists(group_name) or cmds.objExists(
                group_name.removesuffix("_grp") + "_jnt"
            ):
                raise ValueError("SDK sample names already exist")
            group = hlib.createNode(
                "transform", name=group_name, parent=rig.joints()[0], skipSelect=True
            )
            group.plug("translateX").set(5)
            bone = hlib.createNode(
                "joint",
                name=group_name.removesuffix("_grp") + "_jnt",
                parent=group,
                skipSelect=True,
            )
            bone.plug("radius").set(0.45)
            bone.plug("segmentScaleCompensate").set(False)
            graph = rig.add_driven(
                identifier, rig.joints()[1], bone.plug("translateY"), component, axis
            )
            rig.root.plug("hrigOwned").append_message(group)
            rig._layer_members("drivenSet", [group.full_name()])
            target = graph.full_name()
        elif kind == "foot":
            from .reverse_foot import add_reverse_foot

            add_reverse_foot(rig)
            target = rig.controls()["target"]
        elif kind in ("soft", "helper"):
            target = rig._member("channel_" + kind)
        else:
            raise ValueError("Unknown sample layer")
        rig.set_layer_enabled(kind, True)
        return target
