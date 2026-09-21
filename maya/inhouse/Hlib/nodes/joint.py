"""Joint wrappers and collections for Hlib."""

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..core.registry import collection_export, node_wrapper
from ..maths import EulerRotation, Matrix, Scale
from .transform import Transform


@node_wrapper("joint")
class Joint(Transform):
    """Maya joint ノード用の Transform ラッパー。

    Joint 固有の orientation、親子探索、skinCluster 連携を提供する。
    """

    @property
    def joint_orient(self):
        """jointOrient 属性を EulerRotation として取得する。

        Returns:
            EulerRotation: radian に変換した jointOrient 値。
        """
        values = self._compound_values("jointOrient")
        return EulerRotation(*(math.radians(value) for value in values))

    def _rotation_order(self):
        """Maya の rotateOrder を API の回転順序へ変換する。"""
        order_index = int(self.plug("ro").get())
        return (
            om2.MEulerRotation.kXYZ,
            om2.MEulerRotation.kYZX,
            om2.MEulerRotation.kZXY,
            om2.MEulerRotation.kXZY,
            om2.MEulerRotation.kYXZ,
            om2.MEulerRotation.kZYX,
        )[order_index]

    def _rotation_quaternion(self, attribute):
        """Euler の Maya degrees 属性を API quaternion へ変換する。"""
        values = self._compound_values(attribute)
        rotation = om2.MEulerRotation(*(math.radians(value) for value in values), self._rotation_order())
        return rotation.asQuaternion()

    def _remove_segment_scale_compensation(self, matrix):
        """ssc と inverseScale が適用された後の行列から補正前の値を戻す。"""
        if not self.plug("ssc").get():
            return matrix
        inverse_scale = self._compound_values("inverseScale")
        if any(abs(value) < 1e-12 for value in inverse_scale):
            raise ValueError("inverseScale components must be non-zero when segmentScaleCompensate is enabled")
        compensation = Matrix(scale=tuple(1.0 / value for value in inverse_scale))
        return matrix * compensation

    def _apply_local_matrix(self, matrix):
        """jointOrient と rotateAxis を保持して local 行列を適用する。"""
        matrix = self._remove_segment_scale_compensation(matrix)
        target = om2.MTransformationMatrix(matrix.to_mmatrix())
        target_quaternion = target.rotation(asQuaternion=True)
        rotate_axis = self._rotation_quaternion("rotateAxis")
        joint_orient = self._rotation_quaternion("jointOrient")
        rotate_quaternion = rotate_axis.conjugate() * target_quaternion * joint_orient.conjugate()
        rotation = om2.MEulerRotation()
        rotation.setValue(rotate_quaternion)
        rotation.reorderIt(self._rotation_order())

        name = self.full_name
        cmds.setAttr(f"{name}.translate", *matrix.translate)
        cmds.setAttr(f"{name}.rotate", *(math.degrees(component) for component in rotation))
        cmds.setAttr(f"{name}.scale", *matrix.scale)
        cmds.setAttr(f"{name}.shear", *matrix.shear)

    @property
    def orientation(self):
        """joint の orientation 成分を取得する。

        Returns:
            EulerRotation: 現在は ``joint_orient`` と同じ値。
        """
        return self.joint_orient

    @property
    def inverse_scale(self):
        """inverseScale 属性を意味付き Scale として取得する。

        Returns:
            Scale: joint の inverseScale 値。
        """
        return Scale(*self._compound_values("inverseScale"))

    def _compound_values(self, attribute):
        """compound 属性を 3 要素の tuple として取得する。"""
        if not self.is_valid():
            return (0.0, 0.0, 0.0)
        values = cmds.getAttr(f"{self.full_name}.{attribute}")
        if len(values) == 1 and isinstance(values[0], (tuple, list)):
            values = values[0]
        return tuple(values)

    def parent(self):
        """親 joint の名前を取得する。

        Returns:
            str | None: 親 joint 名。親が joint でない場合は ``None``。
        """
        if not self.is_valid():
            return None
        parent = self.parent_node()
        if parent is None or not parent.is_valid():
            return None
        if not parent.mobject().hasFn(om2.MFn.kJoint):
            return None
        return parent.name

    def children(self):
        """直接の子 joint 名を取得する。

        Returns:
            list[str]: 子 joint 名のリスト。
        """
        if not self.is_valid():
            return []
        return [
            child.name
            for child in self.child_nodes()
            if child.mobject().hasFn(om2.MFn.kJoint)
        ]

    def depth(self):
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        depth = 0
        current_joint = self.parent()
        while current_joint:
            depth += 1
            current_joint = Joint(current_joint).parent()
        return depth

    def is_joint(self):
        """ラップ対象が joint か判定する。

        Returns:
            bool: 有効な joint の場合は ``True``。
        """
        return self.is_valid() and self.mobject().hasFn(om2.MFn.kJoint)

    def skin_clusters(self):
        """この joint に接続する skinCluster を取得する。

        Returns:
            list[SkinCluster]: 重複を除いた skinCluster ラッパー。
        """
        from .skincluster import SkinCluster

        names = cmds.listConnections(self.name, type="skinCluster") or []
        return [SkinCluster(name) for name in self._unique_ordered(names)]

    def transfer_target(self, skin):
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ancestor = self.parent()
        while ancestor:
            if skin.has_influence(ancestor):
                return ancestor
            ancestor = Joint(ancestor).parent()
        return None

    def reparent_children(self, parent_joint):
        """子 joint を指定した親 joint へ付け替える。

        Args:
            parent_joint (str): 子 joint の新しい親 joint 名。
        """
        for child_joint in self.children():
            cmds.parent(child_joint, parent_joint)

    @staticmethod
    def _unique_ordered(items):
        """順序を保ったまま重複要素を除外する。"""
        seen = set()
        unique_items = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            unique_items.append(item)
        return unique_items

    def __eq__(self, other):
        """UUID を基準に別の Joint と同一か判定する。"""
        if not isinstance(other, Joint):
            return NotImplemented
        return self.uuid == other.uuid

    def __hash__(self):
        """UUID を使ったハッシュ値を返す。"""
        return hash(self.uuid)


@collection_export()
class Joints:
    """重複を除いた Joint ラッパーコレクション。

    Args:
        names (Iterable[str | Joint]): joint 名または Joint のシーケンス。
    """

    def __init__(self, names=()):
        """joint 名または Joint のシーケンスから重複なしコレクションを作成する。"""
        self._items = []
        seen = set()
        for item in names:
            joint = item if isinstance(item, Joint) else Joint(item)
            if not joint.is_joint() or joint.uuid in seen:
                continue
            seen.add(joint.uuid)
            self._items.append(joint)

    @property
    def names(self):
        """コレクション内の joint 名を取得する。

        Returns:
            list[str]: joint 名のリスト。
        """
        return [joint.name for joint in self._items]

    def sorted_by_depth(self):
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        return Joints(sorted(self._items, key=lambda joint: joint.depth(), reverse=True))

    def skin_clusters(self):
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        from .skincluster import SkinClusters

        skin_clusters = []
        seen = set()
        for joint in self._items:
            for skin in joint.skin_clusters():
                if skin.uuid in seen:
                    continue
                seen.add(skin.uuid)
                skin_clusters.append(skin)
        return SkinClusters(skin_clusters)

    def delete(self):
        """ウェイト移送後にコレクション内の joint を削除する。"""
        self.skin_clusters().remove_joints(self)

    def __iter__(self):
        """保持している Joint を順に反復する。"""
        return iter(self._items)
