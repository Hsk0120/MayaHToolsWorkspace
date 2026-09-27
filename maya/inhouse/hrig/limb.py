"""3関節のFK/IKとSoft IKの最小実装。切替は明示メソッドで行う。"""

import json
import math
from maya import cmds

import hlib
from hlib.decorators.undo import undo_chunk
from hlib.decorators.undo import undo_transaction
from .definition import limb_definition, RigDefinition
from .backends import create_soft_ik
from .naming import limb_names


def _disconnect(destination):
    """入力接続だけを切断する。出力接続は保持する。

    Args:
        destination (str | Plug): 入力を外す属性。
    """
    plug = hlib.plug(destination)
    source = plug.source()
    if source is not None:
        source.disconnect(plug)


def _lock_group(node):
    """整理専用グループの座標を固定し、部位空間の計算を維持する。

    Args:
        node (str | Node): TRSとシアーをロックするノード。
    """
    hlib.node(node).set_attr_flags(
        ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "shearXY", "shearXZ", "shearYZ"),
        locked=True,
        keyable=False,
        channel_box=False,
    )


def _set_world_matrix(node, matrix):
    """ゼロピボットの操作transformへ姿勢をローカル値として適用する。

    Args:
        node (str): hrigが作成したコントローラー。
        matrix (Sequence[float]): 目標のワールド行列。

    Note:
        xform(worldSpace=True)のRedo時の親空間再変換を避けるため、
        計算済みTRSを標準setAttrで保存する。ピボット編集は対象外。
    """
    hlib.node(node).set_matrix(matrix, ws=True)


class LimbRig:
    """構築した部位の参照。保存後はルート名を渡して再取得する。"""

    def __init__(self, root):
        """既存のhrig部位ルートを保持する。

        Args:
            root (str | Node): hrigDefinition属性を持つルート。
        """
        self.root = hlib.node(root)
        if not self.root.has_attr("hrigDefinition"):
            raise ValueError("Not an hrig root")

    def _member(self, role):
        """メッセージ接続から現在名を解決する。改名・再親子付けに追従する。

        Args:
            role (str): ルートに保存した参照の識別子。


        Returns:
            str: メンバーの完全名。
        """
        source = self.root.plug(role).source() if self.root.has_attr(role) else None
        if source is None:
            raise RuntimeError("Missing rig member: " + role)
        return source.node.full_name()

    def _bind(self, role, node):
        """生成物へのメッセージ参照を登録する。

        Args:
            role (str): 未登録の参照識別子。
            node (str): 参照するノード名。
        """
        root = self.root.full_name()
        hlib.node(root).add_attr(long_name=role, attribute_type="message")
        hlib.plug(node + ".message").connect(root + "." + role)

    def controls(self):
        """コントローラーの現在名を取得する。


        Returns:
            dict[str, str]: fk0/fk1/fk2/target/poleと完全名の対応。
        """
        return {key: self._member(key) for key in ("fk0", "fk1", "fk2", "target", "pole")}

    def space_switch(self, control):
        """コントローラーの空間切替を取得する。

        Args:
            control (str): ikまたはpole。

        Returns:
            SpaceSwitch: 空間の列挙・現在値の照会に使う共通オブジェクト。
        """
        from .spaceLayer import SpaceLayer

        return SpaceLayer(self).switcher(control)

    def add_space(self, control, label, target=None):
        """指定ノードを切替先として登録する。

        Args:
            control (str): ikまたはpole。
            label (str): 空間名。
            target (str | Node | None): 参照先。Noneはワールド。
        """
        from .spaceLayer import SpaceLayer

        SpaceLayer(self).add(control, label, target)

    def set_space(self, control, label):
        """ワールド姿勢を保持して空間を切り替える。

        Args:
            control (str): ikまたはpole。
            label (str): local/world/footまたは追加した空間名。
        """
        from .spaceLayer import SpaceLayer

        SpaceLayer(self).switch(control, label)

    def node_name(self, role):
        """保存した定義に基づく生成名を取得する。

        Args:
            role (str): 生成ロールの識別子。


        Returns:
            str: 命名規則を適用したノード名。
        """
        definition = RigDefinition.from_data(
            json.loads(hlib.plug(self.root.full_name() + ".hrigDefinition").get())
        )
        return limb_names(definition)[role]

    def _layer_members(self, role, nodes):
        """レイヤーの選択セットへ生成ノードを登録する。

        Args:
            role (str): セットの参照識別子。
            nodes (Sequence[str]): 追加するノード名。
        """
        if hlib.node(self.root.full_name()).has_attr(role):
            hlib.node(self._member(role)).add(*nodes)

    def _local_matrix(self, role):
        """オフセットを含む親コントローラー空間の行列プラグ名を取得する。

        Args:
            role (str): fk0/fk1/fk2/ik0/ik1/ik2/target。


        Returns:
            str: 旧リグではノード自身のmatrixを返す。
        """
        member = "targetMatrix" if role == "target" else "fkMatrix" + role[2:]
        if role.startswith("fk") or role == "target":
            if hlib.node(self.root.full_name()).has_attr(member):
                return self._member(member) + ".matrixSum"
        return self._member(role) + ".matrix"

    def joints(self):
        """変形用3関節・補助骨・追加ツイスト骨の現在名を取得する。


        Returns:
            tuple[str, ...]: 基本3骨・通常補助骨・ツイスト骨・曲げ補助骨の完全名。
        """
        from .tweakLayer import TweakLayer

        return (
            tuple(self._member(key) for key in ("joint0", "joint1", "joint2", "helper"))
            + self.twist_joints()
            + self.bend_joints()
            + self.follow_joints()
            + TweakLayer(self).joints()
        )

    def add_follow(self, identifier, joint=None, mode="full", axis="x", ratio=0.5):
        """回転の全成分・Twist・Swingを割合追従する補助骨を追加する。

        Args:
            identifier (str): 一意なID。
            joint (str | Node | None): 入力骨。省略時は中間骨。
            mode (str): full/twist/swing。
            axis (str): Twist軸x/y/z。
            ratio (float): 0〜1の割合。

        Returns:
            str: 補助骨の完全名。
        """
        from .followLayer import FollowLayer

        return FollowLayer(self).add(identifier, joint or self._member("joint1"), mode, axis, ratio)

    def add_stretch(self):
        """腕脚へ独立した伸縮・体積補正レイヤーを追加する。

        Returns:
            Node: Channel Boxで編集する設定グループ。
        """
        from .limbStretchLayer import LimbStretchLayer

        return LimbStretchLayer(self).add()

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

    def bend_joints(self, identifier=None):
        """肘膝の補助骨を補間・内側・外側の順に取得する。

        Args:
            identifier (str | None): 部位ID。Noneなら全て。

        Returns:
            tuple[str]: 補助骨の完全名。
        """
        from .bendLayer import BendLayer

        return BendLayer(self).joints(identifier)

    def add_driven(self, identifier, joint, driven, component="twist", axis="x", keys=None):
        """Swing/Twist成分から単一属性をSDKで駆動する。

        Args:
            identifier (str): 一意なSDK識別子。
            joint (str | Node): 回転を分解するjoint。
            driven (str | Plug): 未接続の数値属性。
            component (str): twistまたはswingX/Y/Z。度単位。
            axis (str): Twist軸x/y/z。
            keys (Sequence[tuple] | None): 入力度と出力値の組。

        Returns:
            Node: 分解とSDKを所有するcontainer。
        """
        from .drivenLayer import DrivenLayer

        return DrivenLayer(self).add(identifier, joint, driven, component, axis, keys)

    def add_bend(self, identifier="elbow", joint=None, bend_axis="z", push_axis="y"):
        """肘・膝の回転補間と内外の押引き骨を追加する。

        Args:
            identifier (str): 部位ID。
            joint (str | Node | None): 基準姿勢の関節。省略時は部位の中間骨。
            bend_axis (str): ヒンジ回転軸x/y/z。
            push_axis (str): 内外の移動軸x/y/z。

        Returns:
            tuple[str]: 補間・内側・外側の補助骨。
        """
        from .bendLayer import BendLayer

        return BendLayer(self).add(
            identifier, joint or self._member("joint1"), bend_axis, push_axis
        )

    def bend_settings(self, identifier="elbow"):
        """距離と回転割合を編集する設定グループを取得する。

        Args:
            identifier (str): 登録済み部位ID。

        Returns:
            Node: Channel Boxでも編集可能な設定グループ。
        """
        from .bendLayer import BendLayer

        return BendLayer(self).groups()[identifier]

    def twist_joints(self, segment=None):
        """登録済みのツイスト補助骨を取得する。

        Args:
            segment (str | None): 区間ID。Noneは全区間。

        Returns:
            tuple[str]: 始点から順に並ぶ補助骨。
        """
        from .twistLayer import TwistLayer

        return TwistLayer(self).joints(segment)

    def add_twist(self, segment, start, end, count=3, axis="x"):
        """二つの骨の間にツイスト分配区間を追加する。

        Args:
            segment (str): 一意な区間ID。
            start (str | Node): 始点joint。
            end (str | Node): 終点joint。
            count (int): 両端を含まない補助骨数。
            axis (str): 始点ローカルの長手軸。

        Returns:
            tuple[str]: 生成した補助骨。
        """
        from .twistLayer import TwistLayer

        return TwistLayer(self).add(segment, start, end, count, axis)

    def set_twist_count(self, segment, count):
        """未バインドの区間の本数を変更する。0なら区間を削除する。

        Args:
            segment (str): 既存の区間ID。
            count (int): 新しい補助骨数。

        Returns:
            tuple[str]: 再生成した補助骨。
        """
        from .twistLayer import TwistLayer

        return TwistLayer(self).set_count(segment, count)

    def mode(self):
        """現在の明示切替モードを照会する。


        Returns:
            str: fkまたはik。
        """
        return hlib.plug(self.root.full_name() + ".hrigMode").get()

    def lod(self):
        """現在のLODを照会する。


        Returns:
            int: 0はSoft IK・補助骨なし、1は全機能。
        """
        return hlib.plug(self.root.full_name() + ".hrigLod").get()

    @undo_transaction("hrig.LimbRig.set_backend")
    def set_backend(self, backend):
        """Soft IK実装だけを交換し、骨・コントローラー・スキンを保持する。

        Args:
            backend (str): standard（標準ノード）、bifrostまたはcpp。
        """
        if backend not in ("standard", "bifrost", "cpp"):
            raise ValueError("Unknown backend: " + backend)
        root = self.root.full_name()
        if hlib.plug(root + ".hrigBackend").get() == backend:
            return
        old = self._member("softGraph")
        old_owner = self._member("softOwner")
        if old_owner == root:
            raise RuntimeError("Invalid Soft IK ownership: rig root cannot be replaced")
        length = hlib.plug(root + ".hrigLength").get()
        source = hlib.plug(old + ".distance").source()
        graph, owner = create_soft_ik(self.node_name("soft"), length, backend)
        if owner != graph:
            from hlib.nodes import Node

            reference = Node(graph)
            parent = self._member("softSetup") if hlib.node(root).has_attr("softSetup") else root
            owner = hlib.node(owner).set_parent(parent).full_name()
            graph = reference.full_name()
            hlib.plug(graph + ".visibility").set(False)
        source.connect(graph + ".distance")
        hlib.plug(self._member("target") + ".softness").connect(graph + ".softness")
        for axis in "XYZ":
            hlib.plug(graph + ".ratio").connect(
                self._member("softScale") + ".input2" + axis, force=True
            )
        hlib.plug(graph + ".message").connect(root + ".softGraph", force=True)
        hlib.plug(owner + ".message").connect(root + ".softOwner", force=True)
        indices = cmds.getAttr(root + ".hrigOwned", multiIndices=True) or []
        hlib.plug(owner + ".message").connect(
            root + ".hrigOwned[{}]".format(max(indices, default=-1) + 1)
        )
        self._layer_members("softSet", [owner, graph])
        hlib.plug(root + ".hrigBackend").set(backend)
        self._update_evaluation()
        hlib.delete(old_owner)

    @undo_chunk("hrig.LimbRig.delete")
    def delete(self):
        """所有する生成物を削除する。外部スキンやアニメーションの保護は呼出側で行う。"""
        root = self.root.full_name()
        owned = (
            cmds.listConnections(root + ".hrigOwned", source=True, destination=False, shapes=True)
            or []
        )
        # DAGを一括で削除すると子の重複指定があり得るため、存在確認して順に消す。
        for node in owned:
            if hlib.objExists(node):
                hlib.delete(node)
        if hlib.objExists(root):
            hlib.delete(root)

    @undo_chunk("hrig.LimbRig.set_mode")
    def set_mode(self, mode):
        """FK/IKの計算経路を切り替える。姿勢合わせはmatch_fk/match_ikを先に呼ぶ。

        Args:
            mode (str): fkまたはik。
        """
        if mode not in ("fk", "ik"):
            raise ValueError("mode must be fk or ik")
        for index in range(3):
            source = self._local_matrix(("fk" if mode == "fk" else "ik") + str(index))
            destination = self._member("joint" + str(index)) + ".offsetParentMatrix"
            _disconnect(destination)
            hlib.plug(source).connect(destination)
        hlib.plug(self.root.full_name() + ".hrigMode").set(mode)
        self._update_evaluation()

    def layer_enabled(self, layer):
        """任意レイヤーの使用設定を照会する。旧シーンは有効扱い。

        Args:
            layer (str): soft/helper/foot/twist/bend/drivenの識別子。


        Returns:
            bool: 使用する設定ならTrue。実際の評価状態とは異なる。
        """
        attr = "hrigEnabled_" + layer
        root = self.root.full_name()
        return bool(hlib.plug(root + "." + attr).get()) if hlib.node(root).has_attr(attr) else True

    @undo_chunk("hrig.LimbRig.set_layer_enabled")
    def set_layer_enabled(self, layer, enabled):
        """任意レイヤーの使用設定を変更し、計算経路を更新する。

        Args:
            layer (str): soft/helper/foot/twist/bend/drivenの識別子。
            enabled (bool): Trueの場合に使用する。
        """
        if layer not in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch"):
            raise ValueError("Unknown optional layer: " + layer)
        root = self.root.full_name()
        attr = "hrigEnabled_" + layer
        if not hlib.node(root).has_attr(attr):
            hlib.node(root).add_attr(long_name=attr, attribute_type="bool", default_value=True)
        hlib.plug(root + "." + attr).set(bool(enabled))
        self._update_evaluation()

    @undo_chunk("hrig.LimbRig.set_lod")
    def set_lod(self, lod):
        """LODを選び、不要な経路を切断する。スキンLODは別操作。

        Args:
            lod (int): 0は低詳細、1は全機能。
        """
        if type(lod) is not int or lod not in (0, 1):
            raise ValueError("This prototype supports LOD 0 or 1")
        hlib.plug(self.root.full_name() + ".hrigLod").set(lod)
        self._update_evaluation()

    def _update_evaluation(self):
        """計算経路を明示的に接続/切断し、IKハンドルをブロックする。"""
        ik = self.mode() == "ik"
        detailed = self.lod() == 1
        handle, graph = self._member("handle"), self._member("softGraph")
        scale = self._member("softScale")
        root = self.root.full_name()
        target = self._member("target")
        soft = detailed and self.layer_enabled("soft")
        foot = detailed and self.layer_enabled("foot") and hlib.node(root).has_attr("footMatrix")
        position = target + ".translate"
        if hlib.node(root).has_attr("targetDecompose"):
            position = self._member("targetDecompose") + ".outputTranslate"
        position = self._member("footDecompose") + ".outputTranslate" if foot else position
        matrix = self._member("footMatrix") + ".matrixSum" if foot else self._local_matrix("target")
        for destination in (self._member("distance") + ".point2", scale + ".input1"):
            _disconnect(destination)
            hlib.plug(position).connect(destination)
        rotation_input = self._member("targetRotation") + ".offsetParentMatrix"
        _disconnect(rotation_input)
        hlib.plug(matrix).connect(rotation_input)
        hlib.plug(handle + ".nodeState").set(0 if ik else 2)
        _disconnect(handle + ".translate")
        if ik:
            source = scale + ".output" if soft else position
            hlib.plug(source).connect(handle + ".translate")
        # Bifrostを非表示にしても評価停止にはならない。接続も外してblockする。
        hlib.plug(graph + ".nodeState").set(0 if ik and soft else 2)
        helper = self._member("helper")
        _disconnect(helper + ".rotate")
        if detailed and self.layer_enabled("helper"):
            source = self._local_matrix(("ik" if ik else "fk") + "1")
            decompose = self._member("helperDecompose")
            _disconnect(decompose + ".inputMatrix")
            hlib.plug(source).connect(decompose + ".inputMatrix")
            hlib.plug(self._member("helperScale") + ".output").connect(helper + ".rotate")
        else:
            hlib.plug(helper + ".rotate").set(
                (
                    0,
                    0,
                    0,
                )
            )
        from .twistLayer import TwistLayer

        TwistLayer(self).update()
        from .bendLayer import BendLayer

        BendLayer(self).update()
        from .drivenLayer import DrivenLayer

        DrivenLayer(self).update()
        from .followLayer import FollowLayer

        FollowLayer(self).update()
        from .limbStretchLayer import LimbStretchLayer

        LimbStretchLayer(self).update()
        from .tweakLayer import TweakLayer

        TweakLayer(self).update()
        from .channel_controls import sync_display

        sync_display(self)

    @undo_chunk("hrig.LimbRig.match_fk")
    def match_fk(self):
        """現在の変形姿勢をFKへ合わせる。モード切替やキー設定は行わない。"""
        matrices = [hlib.node(j).get_matrix(ws=True) for j in self.joints()[:3]]
        for index, matrix in enumerate(matrices):
            _set_world_matrix(self._member("fk" + str(index)), matrix)

    @undo_chunk("hrig.LimbRig.match_ik")
    def match_ik(self):
        """現在姿勢からIK目標とpoleを合わせる。Soft IK分の距離を逆算する。"""
        from maya.api import OpenMaya as om

        target = self._member("target")
        for attr in (
            ("heelRoll", "toeRoll", "ballRoll") if self.lod() and self.layer_enabled("foot") else ()
        ):
            if (
                hlib.node(target).has_attr(attr)
                and abs(hlib.plug(target + "." + attr).get()) > 1e-8
            ):
                raise ValueError("Reset reverse-foot rolls before matching IK")
        joints = self.joints()[:3]
        a, b, c = [om.MVector(hlib.node(j).get_translate(ws=True)) for j in joints]
        axis = c - a
        if axis.length() < 1e-8:
            raise ValueError("Cannot match IK when the endpoint coincides with the root")
        projection = a + axis * (((b - a) * axis) / (axis * axis))
        offset = b - projection
        if offset.length() < 1e-8:
            offset = om.MVector(hlib.node(self._member("pole")).get_translate(ws=True)) - b
            offset -= axis * ((offset * axis) / (axis * axis))
        if offset.length() < 1e-8:
            raise ValueError("Choose a pole direction before matching a straight chain")
        pole_position = tuple(b + offset.normal() * axis.length())
        # 逆算は部位空間で行うため、ルートの一様スケールにも追従する。
        inverse = om.MMatrix(hlib.plug(self.root.full_name() + ".worldInverseMatrix[0]").get())
        local_end = om.MPoint(c) * inverse
        distance = om.MVector(local_end).length()
        length = hlib.plug(self.root.full_name() + ".hrigLength").get()
        soft = (
            hlib.plug(self._member("target") + ".softness").get()
            if self.lod() and self.layer_enabled("soft")
            else 0
        )
        desired = distance
        from .limbStretchLayer import LimbStretchLayer

        stretch = LimbStretchLayer(self)
        if stretch.settings() is not None and self.lod() == 1 and self.layer_enabled("stretch"):
            desired = stretch.match_distance(distance, soft, length)
        elif soft > 0 and distance > length - soft:
            if distance >= length - 1e-6:
                raise ValueError("Fully extended pose has no finite Soft IK inverse; use LOD 0")
            desired = length - soft - soft * math.log((length - distance) / soft)
        pole = self._member("pole")
        local_position = om.MPoint(om.MVector(local_end).normal() * desired)
        world_position = local_position * inverse.inverse()
        matrix = list(hlib.node(joints[-1]).get_matrix(ws=True))
        matrix[12:15] = tuple(world_position)[:3]
        _set_world_matrix(target, matrix)
        # PoleがFoot空間の場合はIK目標の移動後の親空間へ変換する。
        pole_local = om.MPoint(pole_position) * om.MMatrix(
            hlib.plug(pole + ".parentInverseMatrix[0]").get()
        )
        hlib.plug(pole + ".translate").set((*tuple(pole_local)[:3],))


@undo_chunk("hrig.build_limb")
def build_limb(definition=None, backend="standard"):
    """最小3関節リグを構築する。任意チェーンやレイヤーはまだ扱わない。

    Args:
        definition (RigDefinition | None): 単一ルート、正X軸の3関節定義。
        backend (str): Soft IK実装。standard（標準ノード）、bifrostまたはcpp。

    Returns:
        LimbRig: 保存・再取得可能な部位。
    """
    definition = definition or limb_definition()
    if not isinstance(definition, RigDefinition):
        raise TypeError("Expected RigDefinition")
    ordered = definition.joint_order()
    if len(ordered) != 3 or ordered[0].parent is not None or ordered[0].translation != (0, 0, 0):
        raise ValueError("Expected a three-joint chain with root at the origin")
    for i in (1, 2):
        if (
            ordered[i].parent != ordered[i - 1].id
            or ordered[i].translation[0] <= 0
            or ordered[i].translation[1:] != (0, 0)
        ):
            raise ValueError("Prototype joints must extend along positive local X")
    supported_layers = limb_definition().layers
    legacy_layers = tuple(layer for layer in supported_layers if layer.kind != "space")
    if definition.layers not in (supported_layers, legacy_layers):
        raise ValueError("This builder supports the default FK/IK/Soft IK/helper/space layers only")
    if hlib.objExists(definition.name):
        raise ValueError("Rig root already exists: " + definition.name)
    names = limb_names(definition)
    if len(set(names.values())) != len(names):
        raise ValueError("Joint identifiers conflict with reserved rig names")
    for name in names.values():
        if hlib.objExists(name):
            raise ValueError("Rig node already exists: " + name)
    if int(cmds.about(apiVersion=True)) < 20250000:
        raise RuntimeError("hrig requires Maya 2025 or newer")
    if backend not in ("standard", "bifrost", "cpp"):
        raise ValueError("Unknown backend: " + backend)
    if backend == "bifrost":
        from hlib_bifrost import ensure_available

        ensure_available()
    saved_selection = cmds.ls(selection=True, long=True) or []
    created = []

    def create(kind, suffix, parent=None):
        """生成ノードを失敗時の削除対象へ登録する。

        Args:
            kind (str): Mayaのノード型。
            suffix (str): 生成ロールの識別子。
            parent (str | None): DAG親。Noneならワールド直下。


        Returns:
            str: 生成したノードの完全名。
        """
        kwargs = {"parent": parent} if parent else {}
        node = hlib.createNode(kind, name=names[suffix], skipSelect=True, **kwargs).full_name()
        created.append(node)
        return node

    try:
        root = hlib.createNode("transform", name=definition.name, skipSelect=True).full_name()
        created.append(root)
        for attr in ("hrigDefinition", "hrigMode", "hrigBackend"):
            hlib.node(root).add_attr(long_name=attr, data_type="string")
        hlib.plug(root + ".hrigDefinition").set(json.dumps(definition.to_data()))
        hlib.plug(root + ".hrigBackend").set(backend)
        rig = LimbRig(root)
        hlib.node(root).add_attr(long_name="hrigLod", attribute_type="long", default_value=1)
        length = ordered[1].translation[0] + ordered[2].translation[0]
        hlib.node(root).add_attr(
            long_name="hrigLength", attribute_type="double", default_value=length
        )
        for role in ("geometryGroup", "jointGroup", "controlGroup", "setupGroup"):
            node = create("transform", role, root)
            _lock_group(node)
            rig._bind(role, node)
        hlib.plug(rig._member("setupGroup") + ".visibility").set(False)
        for role, parent_role in (
            ("moduleGeometry", "geometryGroup"),
            ("moduleJoints", "jointGroup"),
            ("moduleControls", "controlGroup"),
            ("moduleSetup", "setupGroup"),
            ("fkControls", "moduleControls"),
            ("ikControls", "moduleControls"),
            ("ikSetup", "moduleSetup"),
            ("softSetup", "moduleSetup"),
            ("helperSetup", "moduleSetup"),
        ):
            node = create("transform", role, rig._member(parent_role))
            _lock_group(node)
            rig._bind(role, node)
        for role in ("moduleSet", "fkSet", "ikSet", "softSet", "helperSet"):
            node = cmds.sets(empty=True, name=names[role])
            created.append(node)
            rig._bind(role, node)
            if role != "moduleSet":
                hlib.node(rig._member("moduleSet")).add(node)
        for chain in ("fk", "ik", "joint"):
            parent = rig._member(
                {"fk": "fkControls", "ik": "ikSetup", "joint": "moduleJoints"}[chain]
            )
            for index, spec in enumerate(ordered):
                if chain == "fk":
                    offset = create("transform", "fk" + str(index) + "Offset", parent)
                    hlib.plug(offset + ".translate").set((*spec.translation,))
                    rig._bind("fk" + str(index) + "Offset", offset)
                    parent = offset
                node = create("joint" if chain != "fk" else "transform", chain + str(index), parent)
                rig._bind(chain + str(index), node)
                if chain == "ik":
                    hlib.plug(node + ".translate").set((*spec.translation,))
                if chain == "fk":
                    matrix = create("multMatrix", "fkMatrix" + str(index))
                    rig._bind("fkMatrix" + str(index), matrix)
                    hlib.plug(node + ".matrix").connect(matrix + ".matrixIn[0]")
                    hlib.plug(offset + ".matrix").connect(matrix + ".matrixIn[1]")
                if chain != "fk":
                    hlib.plug(node + ".segmentScaleCompensate").set(False)
                if chain == "ik":
                    hlib.plug(node + ".visibility").set(False)
                parent = node
        for role, position in (
            ("target", (length * 0.8, 0, 0)),
            ("pole", (length * 0.5, length, 0)),
        ):
            offset = create("transform", role + "Offset", rig._member("ikControls"))
            hlib.plug(offset + ".translate").set((*position,))
            rig._bind(role + "Offset", offset)
            rig._bind(role, create("transform", role, offset))
        target, pole = rig._member("target"), rig._member("pole")
        matrix = create("multMatrix", "targetMatrix")
        rig._bind("targetMatrix", matrix)
        hlib.plug(target + ".matrix").connect(matrix + ".matrixIn[0]")
        hlib.plug(rig._member("targetOffset") + ".matrix").connect(matrix + ".matrixIn[1]")
        target_decompose = create("decomposeMatrix", "targetDecompose")
        rig._bind("targetDecompose", target_decompose)
        hlib.plug(matrix + ".matrixSum").connect(target_decompose + ".inputMatrix")
        target_rotation = create("transform", "targetRotation", rig._member("ikSetup"))
        rig._bind("targetRotation", target_rotation)
        hlib.node(target).add_attr(
            long_name="softness",
            attribute_type="double",
            minValue=0,
            maxValue=length,
            default_value=length * 0.1,
            keyable=True,
        )
        # preferredAngleで伸び切った初期チェーンの曲げ平面を定義する。
        hlib.plug(rig._member("ik1") + ".preferredAngleZ").set(-10)
        handle, effector = cmds.ikHandle(
            startJoint=rig._member("ik0"),
            endEffector=rig._member("ik2"),
            solver="ikRPsolver",
            name=names["handle"],
        )
        effector = hlib.node(effector).rename(names["effector"])
        created.extend((handle, effector))
        handle = hlib.node(handle).set_parent(rig._member("ikSetup")).full_name()
        rig._bind("handle", handle)
        constraints = cmds.poleVectorConstraint(
            pole, handle, name=names["handle"] + "_poleVectorConstraint"
        )
        constraints += cmds.orientConstraint(
            target_rotation,
            rig._member("ik2"),
            maintainOffset=False,
            name=names["ik2"] + "_orientConstraint",
        )
        created.extend(constraints)
        rig._layer_members("ikSet", constraints + [effector])
        hlib.plug(handle + ".visibility").set(False)
        graph, graph_parent = create_soft_ik(names["soft"], length, backend)
        created.append(graph_parent)
        if graph_parent != graph:
            from hlib.nodes import Node

            graph_ref = Node(graph)
            graph_parent = hlib.node(graph_parent).set_parent(rig._member("softSetup")).full_name()
            created[-1] = graph_parent
            graph = graph_ref.full_name()
            hlib.plug(graph + ".visibility").set(False)
        rig._bind("softGraph", graph)
        rig._bind("softOwner", graph_parent)
        distance = create("distanceBetween", "distance")
        rig._bind("distance", distance)
        hlib.plug(target + ".translate").connect(distance + ".point2")
        hlib.plug(distance + ".distance").connect(graph + ".distance")
        hlib.plug(target + ".softness").connect(graph + ".softness")
        scale = create("multiplyDivide", "softScale")
        rig._bind("softScale", scale)
        hlib.plug(target + ".translate").connect(scale + ".input1")
        for axis in "XYZ":
            hlib.plug(graph + ".ratio").connect(scale + ".input2" + axis)
        helper = create("joint", "helper", rig._member("joint1"))
        rig._bind("helper", helper)
        hlib.plug(helper + ".translateX").set(ordered[2].translation[0] * 0.5)
        hlib.plug(helper + ".segmentScaleCompensate").set(False)
        decompose = create("decomposeMatrix", "helperDecompose")
        half = create("multiplyDivide", "helperScale")
        rig._bind("helperDecompose", decompose)
        rig._bind("helperScale", half)
        hlib.plug(decompose + ".outputRotate").connect(half + ".input1")
        hlib.plug(half + ".input2").set(
            (
                0.5,
                0.5,
                0.5,
            )
        )
        for role, members in {
            "fkSet": ["fkControls"]
            + ["fk" + str(i) for i in range(3)]
            + ["fk" + str(i) + "Offset" for i in range(3)]
            + ["fkMatrix" + str(i) for i in range(3)],
            "ikSet": [
                "ikControls",
                "ikSetup",
                "target",
                "pole",
                "targetOffset",
                "poleOffset",
                "targetMatrix",
                "targetDecompose",
                "targetRotation",
                "handle",
                "ik0",
                "ik1",
                "ik2",
            ],
            "softSet": ["softSetup", "softGraph", "softOwner", "distance", "softScale"],
            "helperSet": ["helperSetup", "helper", "helperDecompose", "helperScale"],
            "moduleSet": [
                "moduleGeometry",
                "moduleJoints",
                "moduleControls",
                "moduleSetup",
                "joint0",
                "joint1",
                "joint2",
            ],
        }.items():
            rig._layer_members(role, list(set(rig._member(member) for member in members)))
        hlib.node(root).add_attr(long_name="hrigOwned", attribute_type="message", multi=True)
        for index, node in enumerate(created):
            if node != root and hlib.objExists(node):
                hlib.plug(node + ".message").connect(root + ".hrigOwned[{}]".format(index))
        from .spaceLayer import SpaceLayer

        SpaceLayer(rig).attach()
        rig.set_mode("fk")
        from .channel_controls import attach

        attach(rig)
        return rig
    except Exception:
        for node in reversed(created):
            if hlib.objExists(node):
                hlib.delete(node)
        raise
    finally:
        hlib.select(saved_selection, replace=True) if saved_selection else hlib.select(clear=True)
