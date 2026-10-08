"""既存の変形骨へ局所操作用の補助骨を追加する。"""

from maya import cmds

from functools import partial
import re
import hlib
from hlib.decorator import undoTransaction


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
        if not root.hasAttr("tweakGroups"):
            return {}
        return {
            node.getPlug("tweakId").get(): node
            for node in root.getPlug("tweakGroups").getSourceNodes().values()
        }

    def getJoints(self):
        """スキン対象の補助骨を取得する。

        Returns:
            tuple[str]: 完全名。
        """
        return tuple(g.getPlug("joint").getSourceWithConversion().getNode().getFullName() for g in self.groups().values())

    @undoTransaction("hrig.TweakLayer.add")
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
        if joint.getType() != "joint" or not joint.getFullName().startswith(root.getFullName() + "|"):
            raise ValueError("Select a joint inside the module")
        stem = root.getName() + "_tweak_" + identifier
        group = hlib.createNode("transform", name=stem + "_grp", parent=joint, skipSelect=True)
        group.addAttr(longName="tweakId", dataType="string").set(identifier)
        group.addAttr(longName="enabled", attributeType="bool", defaultValue=True)
        group.setAttrFlags(["enabled"], channelBox=True)
        control = hlib.createNode("transform", name=stem + "_ctrl", parent=group, skipSelect=True)
        bone = hlib.createNode("joint", name=stem + "_jnt", parent=group, skipSelect=True)
        bone.getPlug("segmentScaleCompensate").set(False)
        bone.getPlug("radius").set(0.25)
        from hrig.setups import ControlShape

        ControlShape.circle(control, 0.35, (1, 0, 0), 13)
        for attr, node in (("control", control), ("joint", bone)):
            group.addAttr(longName=attr, attributeType="message")
            node.getPlug("message").connectTo(group.getPlug(attr))
        if not root.hasAttr("tweakGroups"):
            root.addAttr(longName="tweakGroups", attributeType="message", multi=True)
        root.getPlug("tweakGroups").appendMessage(group)
        group.setAttrFlags(["translate", "rotate", "scale"], locked=True, keyable=False)
        self.update()
        from .channel_controls import install

        install()
        return control

    @undoTransaction("hrig.TweakLayer.update")
    def update(self):
        """Enabled/LODに応じて局所行列の入力を切り替える。"""
        for group in self.groups().values():
            active = bool(group.getPlug("enabled").get()) and self.rig.lod() == 1
            control = group.getPlug("control").getSourceWithConversion().getNode()
            destination = group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix")
            previous = destination.getSourceWithConversion()
            if active and previous is None:
                control.getPlug("matrix").connectTo(destination)
            elif not active and previous is not None:
                destination.disconnect(previous)
                destination.set(hlib.maths.Matrix())
            control.getPlug("visibility").setIfChanged(active)

    @classmethod
    def refresh_jobs(cls):
        """全モジュールのTweak使用設定をGUIで監視する。"""
        if cmds.about(batch=True):
            return
        from .moduleRegistry import ModuleRegistry

        for key, jobs in list(cls._jobs.items()):
            if not [item.getName() for item in hlib.ls(key)] or not jobs.exists():
                jobs.stop()
                del cls._jobs[key]
        for root in ModuleRegistry.roots():
            rig = ModuleRegistry.get(root)
            for group in cls(rig).groups().values():
                key = group.getUuid()
                if key in cls._jobs:
                    continue
                jobs = hlib.common.ScriptJobs()
                for plug in (
                    group.getPlug("enabled"),
                    rig.root.getPlug("hrigLod" if rig.root.hasAttr("hrigLod") else "lod"),
                ):
                    jobs.add(
                        plug.getFullName(),
                        attribute=plug,
                        callback=partial(cls._changed, rig.root.getUuid()),
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

        names = [item.getFullName() for item in hlib.ls(root_uuid, long=True)] or []
        if not names:
            return
        layer = cls(ModuleRegistry.get(names[0]))
        for group in layer.groups().values():
            active = bool(group.getPlug("enabled").get()) and layer.rig.lod() == 1
            if (
                bool(group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix").getSourceWithConversion())
                != active
            ):
                layer.update()
                break
