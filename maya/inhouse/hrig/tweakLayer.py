"""既存の変形骨へ局所操作用の補助骨を追加する。"""

from maya import cmds

from functools import partial
import re
import hlib
from hlib.decorators.undo import undo_transaction


class TweakLayer:
    """骨のローカル空間に独立した手付けTRSを重ねる。"""

    _jobs = {}

    def __init__(self, rig):
        """対象モジュールを保持する。

        Args:
            rig: rootとlod()を持つhrigモジュール。
        """
        self.rig = rig

    def groups(self):
        """保存したTweakグループを取得する。

        Returns:
            dict[str, Node]: IDとグループ。
        """
        root = self.rig.root
        if not root.has_attribute("tweakGroups"):
            return {}
        return {
            node.plug("tweakId").get(): node
            for node in root.plug("tweakGroups").source_nodes().values()
        }

    def joints(self):
        """スキン対象の補助骨を取得する。

        Returns:
            tuple[str]: 完全名。
        """
        return tuple(g.plug("joint").source().node.full_name() for g in self.groups().values())

    @undo_transaction("hrig.TweakLayer.add")
    def add(self, identifier, joint):
        """選択骨の子へゼロ姿勢のTweakを追加する。スキンへは自動追加しない。

        Args:
            identifier (str): モジュール内一意ID。
            joint (str | Node): モジュール内の入力骨。

        Returns:
            Node: 操作用transform。
        """
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", identifier) or identifier in self.groups():
            raise ValueError("Use a unique tweak identifier")
        joint = hlib.getNode(joint)
        root = self.rig.root
        if joint.type() != "joint" or not joint.full_name().startswith(root.full_name() + "|"):
            raise ValueError("Select a joint inside the module")
        stem = root.name() + "_tweak_" + identifier
        group = hlib.createNode("transform", name=stem + "_grp", parent=joint, skipSelect=True)
        group.add_attribute(long_name="tweakId", data_type="string").set(identifier)
        group.add_attribute(long_name="enabled", attribute_type="bool", default_value=True)
        group.set_attribute_flags(["enabled"], channel_box=True)
        control = hlib.createNode("transform", name=stem + "_ctrl", parent=group, skipSelect=True)
        bone = hlib.createNode("joint", name=stem + "_jnt", parent=group, skipSelect=True)
        bone.plug("segmentScaleCompensate").set(False)
        bone.plug("radius").set(0.25)
        from hrig.setups import ControlShape

        ControlShape.circle(control, 0.35, (1, 0, 0), 13)
        for attr, node in (("control", control), ("joint", bone)):
            group.add_attribute(long_name=attr, attribute_type="message")
            node.plug("message").connect(group.plug(attr))
        if not root.has_attribute("tweakGroups"):
            root.add_attribute(long_name="tweakGroups", attribute_type="message", multi=True)
        root.plug("tweakGroups").append_message(group)
        group.set_attribute_flags(["translate", "rotate", "scale"], locked=True, keyable=False)
        self.update()
        from .channel_controls import install

        install()
        return control

    @undo_transaction("hrig.TweakLayer.update")
    def update(self):
        """Enabled/LODに応じて局所行列の入力を切り替える。"""
        for group in self.groups().values():
            active = bool(group.plug("enabled").get()) and self.rig.lod() == 1
            control = group.plug("control").source().node
            destination = group.plug("joint").source().node.plug("offsetParentMatrix")
            previous = destination.source()
            if active and previous is None:
                control.plug("matrix").connect(destination)
            elif not active and previous is not None:
                previous.disconnect(destination)
                destination.set(hlib.maths.Matrix())
            control.plug("visibility").set_if_changed(active)

    @classmethod
    def refresh_jobs(cls):
        """全モジュールのTweak使用設定をGUIで監視する。"""
        if cmds.about(batch=True):
            return
        from .moduleRegistry import ModuleRegistry

        for key, jobs in list(cls._jobs.items()):
            if not [item.name() for item in hlib.ls(key)] or not jobs.exists():
                jobs.stop()
                del cls._jobs[key]
        for root in ModuleRegistry.roots():
            rig = ModuleRegistry.get(root)
            for group in cls(rig).groups().values():
                key = group.uuid()
                if key in cls._jobs:
                    continue
                jobs = hlib.events.ScriptJobs()
                for plug in (
                    group.plug("enabled"),
                    rig.root.plug("hrigLod" if rig.root.has_attribute("hrigLod") else "lod"),
                ):
                    jobs.add(
                        plug.full_name(),
                        attribute=plug,
                        callback=partial(cls._changed, rig.root.uuid()),
                        kill_with_scene=True,
                        compress_undo=True,
                    )
                cls._jobs[key] = jobs

    @classmethod
    def _changed(cls, root_uuid):
        """差分があるときだけ出力を切り替える。

        Args:
            root_uuid (str): モジュールUUID。
        """
        from .moduleRegistry import ModuleRegistry

        names = [item.full_name() for item in hlib.ls(root_uuid, long=True)] or []
        if not names:
            return
        layer = cls(ModuleRegistry.get(names[0]))
        for group in layer.groups().values():
            active = bool(group.plug("enabled").get()) and layer.rig.lod() == 1
            if (
                bool(group.plug("joint").source().node.plug("offsetParentMatrix").source())
                != active
            ):
                layer.update()
                break
