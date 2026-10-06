"""3関節のFK/IKとSoft IKの最小実装。切替は明示メソッドで行う。"""
from hlib.maths import MSpace

from maya import cmds

import math
import hlib

from hlib.decorators.undo import undoChunk
from hlib.decorators.undo import undoTransaction
from .definition import limb_definition, RigDefinition
from .backends import create_soft_ik
from .naming import limb_names


def _lock_group(node):
    """整理専用グループの座標を固定し、部位空間の計算を維持する。

    Args:
        node (str | Node): TRSとシアーをロックするノード。
    """
    hlib.getNode(node).setAttrFlags(
        ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "shearXY", "shearXZ", "shearYZ"),
        locked=True,
        keyable=False,
        channelBox=False,
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
    hlib.getNode(node).setMatrix(matrix, ws=True)


class LimbRig:
    """構築した部位の参照。保存後はルート名を渡して再取得する。"""

    def __init__(self, root):
        """既存のhrig部位ルートを保持する。

        Args:
            root (str | Node): hrigDefinition属性を持つルート。
        """
        self.root = hlib.getNode(root)
        if not self.root.hasAttr("hrigDefinition"):
            raise ValueError("Not an hrig root")

    def _member(self, role):
        """メッセージ接続から現在名を解決する。改名・再親子付けに追従する。

        Args:
            role (str): ルートに保存した参照の識別子。


        Returns:
            str: メンバーの完全名。
        """
        source = self.root.getPlug(role).getSourceWithConversion() if self.root.hasAttr(role) else None
        if source is None:
            raise RuntimeError("Missing rig member: " + role)
        return source.getNode().getFullName()

    def _bind(self, role, node):
        """生成物へのメッセージ参照を登録する。

        Args:
            role (str): 未登録の参照識別子。
            node (str | Node): 参照するノード。
        """
        root = self.root.getFullName()
        hlib.getNode(root).addAttr(longName=role, attributeType="message")
        hlib.getNode(node).getPlug("message").connectTo(root + "." + role)

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

    def getNodeName(self, role):
        """保存した定義に基づく生成名を取得する。

        Args:
            role (str): 生成ロールの識別子。


        Returns:
            str: 命名規則を適用したノード名。
        """
        definition = RigDefinition.from_data(
            hlib.json.JsonText.loads(self.root.getPlug("hrigDefinition").get())
        )
        return limb_names(definition)[role]

    def _layer_members(self, role, nodes):
        """レイヤーの選択セットへ生成ノードを登録する。

        Args:
            role (str): セットの参照識別子。
            nodes (Sequence[str]): 追加するノード名。
        """
        if hlib.getNode(self.root.getFullName()).hasAttr(role):
            hlib.getNode(self._member(role)).addMembers(*nodes)

    def _local_matrix(self, role):
        """オフセットを含む親コントローラー空間の行列プラグ名を取得する。

        Args:
            role (str): fk0/fk1/fk2/ik0/ik1/ik2/target。


        Returns:
            str: 旧リグではノード自身のmatrixを返す。
        """
        member = "targetMatrix" if role == "target" else "fkMatrix" + role[2:]
        if role.startswith("fk") or role == "target":
            if hlib.getNode(self.root.getFullName()).hasAttr(member):
                return self._member(member) + ".matrixSum"
        return self._member(role) + ".matrix"

    def getJoints(self):
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
            + TweakLayer(self).getJoints()
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

        return FollowLayer(self).getJoints(identifier)

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

        return BendLayer(self).getJoints(identifier)

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

        return TwistLayer(self).getJoints(segment)

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
        return self.root.getPlug("hrigMode").get()

    def lod(self):
        """現在のLODを照会する。


        Returns:
            int: 0はSoft IK・補助骨なし、1は全機能。
        """
        return self.root.getPlug("hrigLod").get()

    @undoTransaction("hrig.LimbRig.set_backend")
    def set_backend(self, backend):
        """Soft IK実装だけを交換し、骨・コントローラー・スキンを保持する。

        Args:
            backend (str): standard（標準ノード）、bifrostまたはcpp。
        """
        if backend not in ("standard", "bifrost", "cpp"):
            raise ValueError("Unknown backend: " + backend)
        root = self.root.getFullName()
        if hlib.getPlug(root + ".hrigBackend").get() == backend:
            return
        old = self._member("softGraph")
        old_owner = self._member("softOwner")
        if old_owner == root:
            raise RuntimeError("Invalid Soft IK ownership: rig root cannot be replaced")
        length = hlib.getPlug(root + ".hrigLength").get()
        source = hlib.getPlug(old + ".distance").getSourceWithConversion()
        graph, owner = create_soft_ik(self.getNodeName("soft"), length, backend)
        if owner != graph:
            from hlib.nodes import Node

            reference = Node(graph)
            parent = self._member("softSetup") if hlib.getNode(root).hasAttr("softSetup") else root
            owner = hlib.getNode(owner).setParent(parent).getFullName()
            graph = reference.getFullName()
            hlib.getPlug(graph + ".visibility").set(False)
        source.connectTo(graph + ".distance")
        hlib.getPlug(self._member("target") + ".softness").connectTo(graph + ".softness")
        for axis in "XYZ":
            hlib.getPlug(graph + ".ratio").connectTo(
                self._member("softScale") + ".input2" + axis, force=True
            )
        hlib.getPlug(graph + ".message").connectTo(root + ".softGraph", force=True)
        hlib.getPlug(owner + ".message").connectTo(root + ".softOwner", force=True)
        hlib.getNode(root).getPlug("hrigOwned").appendMessage(owner)
        self._layer_members("softSet", [owner, graph])
        hlib.getPlug(root + ".hrigBackend").set(backend)
        self._update_evaluation()
        hlib.delete(old_owner)

    @undoChunk("hrig.LimbRig.delete")
    def delete(self):
        """所有する生成物を削除する。外部スキンやアニメーションの保護は呼出側で行う。"""
        root = self.root.getFullName()
        owned = [
            item.getFullName()
            for item in [
                hlib.getNode(value)
                for value in (
                    cmds.listConnections(
                        root + ".hrigOwned", source=True, destination=False, shapes=True
                    )
                    or []
                )
            ]
        ] or []
        # DAGを一括で削除すると子の重複指定があり得るため、存在確認して順に消す。
        for node in owned:
            if cmds.objExists(node):
                hlib.delete(node)
        if cmds.objExists(root):
            hlib.delete(root)

    @undoChunk("hrig.LimbRig.set_mode")
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
            hlib.getPlug(destination).disconnectInput()
            hlib.getPlug(source).connectTo(destination)
        self.root.getPlug("hrigMode").set(mode)
        self._update_evaluation()

    def layer_enabled(self, layer):
        """任意レイヤーの使用設定を照会する。旧シーンは有効扱い。

        Args:
            layer (str): soft/helper/foot/twist/bend/drivenの識別子。


        Returns:
            bool: 使用する設定ならTrue。実際の評価状態とは異なる。
        """
        attr = "hrigEnabled_" + layer
        root = self.root.getFullName()
        return bool(hlib.getPlug(root + "." + attr).get()) if hlib.getNode(root).hasAttr(attr) else True

    @undoChunk("hrig.LimbRig.set_layer_enabled")
    def set_layer_enabled(self, layer, enabled):
        """任意レイヤーの使用設定を変更し、計算経路を更新する。

        Args:
            layer (str): soft/helper/foot/twist/bend/drivenの識別子。
            enabled (bool): Trueの場合に使用する。
        """
        if layer not in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch"):
            raise ValueError("Unknown optional layer: " + layer)
        root = self.root.getFullName()
        attr = "hrigEnabled_" + layer
        if not hlib.getNode(root).hasAttr(attr):
            hlib.getNode(root).addAttr(longName=attr, attributeType="bool", defaultValue=True)
        hlib.getPlug(root + "." + attr).set(bool(enabled))
        self._update_evaluation()

    @undoChunk("hrig.LimbRig.set_lod")
    def set_lod(self, lod):
        """LODを選び、不要な経路を切断する。スキンLODは別操作。

        Args:
            lod (int): 0は低詳細、1は全機能。
        """
        if type(lod) is not int or lod not in (0, 1):
            raise ValueError("This prototype supports LOD 0 or 1")
        self.root.getPlug("hrigLod").set(lod)
        self._update_evaluation()

    def _update_evaluation(self):
        """計算経路を明示的に接続/切断し、IKハンドルをブロックする。"""
        ik = self.mode() == "ik"
        detailed = self.lod() == 1
        handle, graph = self._member("handle"), self._member("softGraph")
        scale = self._member("softScale")
        root = self.root.getFullName()
        target = self._member("target")
        soft = detailed and self.layer_enabled("soft")
        foot = detailed and self.layer_enabled("foot") and hlib.getNode(root).hasAttr("footMatrix")
        position = target + ".translate"
        if hlib.getNode(root).hasAttr("targetDecompose"):
            position = self._member("targetDecompose") + ".outputTranslate"
        position = self._member("footDecompose") + ".outputTranslate" if foot else position
        matrix = self._member("footMatrix") + ".matrixSum" if foot else self._local_matrix("target")
        for destination in (self._member("distance") + ".point2", scale + ".input1"):
            hlib.getPlug(destination).disconnectInput()
            hlib.getPlug(position).connectTo(destination)
        rotation_input = self._member("targetRotation") + ".offsetParentMatrix"
        hlib.getPlug(rotation_input).disconnectInput()
        hlib.getPlug(matrix).connectTo(rotation_input)
        hlib.getPlug(handle + ".nodeState").set(0 if ik else 2)
        hlib.getPlug(handle + ".translate").disconnectInput()
        if ik:
            source = scale + ".output" if soft else position
            hlib.getPlug(source).connectTo(handle + ".translate")
        # Bifrostを非表示にしても評価停止にはならない。接続も外してblockする。
        hlib.getPlug(graph + ".nodeState").set(0 if ik and soft else 2)
        helper = self._member("helper")
        hlib.getPlug(helper + ".rotate").disconnectInput()
        if detailed and self.layer_enabled("helper"):
            source = self._local_matrix(("ik" if ik else "fk") + "1")
            decompose = self._member("helperDecompose")
            hlib.getPlug(decompose + ".inputMatrix").disconnectInput()
            hlib.getPlug(source).connectTo(decompose + ".inputMatrix")
            hlib.getPlug(self._member("helperScale") + ".output").connectTo(helper + ".rotate")
        else:
            hlib.getPlug(helper + ".rotate").set(
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

    @undoChunk("hrig.LimbRig.match_fk")
    def match_fk(self):
        """現在の変形姿勢をFKへ合わせる。モード切替やキー設定は行わない。"""
        matrices = [hlib.getNode(j).getMatrix(ws=True) for j in self.getJoints()[:3]]
        for index, matrix in enumerate(matrices):
            _set_world_matrix(self._member("fk" + str(index)), matrix)

    @undoChunk("hrig.LimbRig.match_ik")
    def match_ik(self):
        """現在姿勢からIK目標とpoleを合わせる。Soft IK分の距離を逆算する。"""
        from hlib.maths import Matrix, Vector

        target = self._member("target")
        for attr in (
            ("heelRoll", "toeRoll", "ballRoll") if self.lod() and self.layer_enabled("foot") else ()
        ):
            if (
                hlib.getNode(target).hasAttr(attr)
                and abs(hlib.getPlug(target + "." + attr).get()) > 1e-8
            ):
                raise ValueError("Reset reverse-foot rolls before matching IK")
        joints = self.getJoints()[:3]
        a, b, c = [Vector(hlib.getNode(j).getTranslation(ws=True, at=4)) for j in joints]
        axis = c - a
        if axis.length() < 1e-8:
            raise ValueError("Cannot match IK when the endpoint coincides with the root")
        projection = a + axis * (((b - a) * axis) / (axis * axis))
        offset = b - projection
        if offset.length() < 1e-8:
            offset = Vector(hlib.getNode(self._member("pole")).getTranslation(ws=True, at=4)) - b
            offset -= axis * ((offset * axis) / (axis * axis))
        if offset.length() < 1e-8:
            raise ValueError("Choose a pole direction before matching a straight chain")
        pole_position = tuple(b + offset.normal() * axis.length())
        # 逆算は部位空間で行うため、ルートの一様スケールにも追従する。
        inverse = Matrix(self.root.getPlug("worldInverseMatrix")[0].get())
        local_end = inverse.transformPoint(c)
        distance = Vector(local_end).length()
        length = self.root.getPlug("hrigLength").get()
        soft = (
            hlib.getPlug(self._member("target") + ".softness").get()
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
        local_position = Vector(local_end).normal() * desired
        world_position = inverse.inverse().transformPoint(local_position)
        matrix = list(hlib.getNode(joints[-1]).getMatrix(ws=True))
        matrix[12:15] = tuple(world_position)[:3]
        _set_world_matrix(target, matrix)
        # PoleがFoot空間の場合はIK目標の移動後の親空間へ変換する。
        pole_local = Matrix(hlib.getNode(pole).getPlug("parentInverseMatrix")[0].get()).transformPoint(
            pole_position
        )
        for axis, value in zip("XYZ", tuple(pole_local)[:3]):
            hlib.getPlug(pole + ".translate" + axis).set(value)


@undoChunk("hrig.build_limb")
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
    if cmds.objExists(definition.name):
        raise ValueError("Rig root already exists: " + definition.name)
    names = limb_names(definition)
    if len(set(names.values())) != len(names):
        raise ValueError("Joint identifiers conflict with reserved rig names")
    for name in names.values():
        if cmds.objExists(name):
            raise ValueError("Rig node already exists: " + name)
    if int(cmds.about(apiVersion=True)) < 20250000:
        raise RuntimeError("hrig requires Maya 2025 or newer")
    if backend not in ("standard", "bifrost", "cpp"):
        raise ValueError("Unknown backend: " + backend)
    if backend == "bifrost":
        from hlib_bifrost.environment import Bifrost

        Bifrost.ensure_available()
    saved_selection = [item.getFullName() for item in hlib.ls(selection=True, long=True)] or []
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
        node = hlib.createNode(kind, name=names[suffix], skipSelect=True, **kwargs).getFullName()
        created.append(node)
        return node

    try:
        root = hlib.createNode("transform", name=definition.name, skipSelect=True).getFullName()
        created.append(root)
        for attr in ("hrigDefinition", "hrigMode", "hrigBackend"):
            hlib.getNode(root).addAttr(longName=attr, dataType="string")
        hlib.getPlug(root + ".hrigDefinition").set(hlib.json.JsonText.dumps(definition.to_data()))
        hlib.getPlug(root + ".hrigBackend").set(backend)
        rig = LimbRig(root)
        hlib.getNode(root).addAttr(longName="hrigLod", attributeType="long", defaultValue=1)
        length = ordered[1].translation[0] + ordered[2].translation[0]
        hlib.getNode(root).addAttr(
            longName="hrigLength", attributeType="double", defaultValue=length
        )
        for role in ("geometryGroup", "jointGroup", "controlGroup", "setupGroup"):
            node = create("transform", role, root)
            _lock_group(node)
            rig._bind(role, node)
        hlib.getPlug(rig._member("setupGroup") + ".visibility").set(False)
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
            node = hlib.createSet(empty=True, name=names[role]).getFullName()
            created.append(node)
            rig._bind(role, node)
            if role != "moduleSet":
                hlib.getNode(rig._member("moduleSet")).addMembers(node)
        for chain in ("fk", "ik", "joint"):
            parent = rig._member(
                {"fk": "fkControls", "ik": "ikSetup", "joint": "moduleJoints"}[chain]
            )
            for index, spec in enumerate(ordered):
                if chain == "fk":
                    offset = create("transform", "fk" + str(index) + "Offset", parent)
                    hlib.getPlug(offset + ".translate").set((*spec.translation,))
                    rig._bind("fk" + str(index) + "Offset", offset)
                    parent = offset
                node = create("joint" if chain != "fk" else "transform", chain + str(index), parent)
                rig._bind(chain + str(index), node)
                if chain == "ik":
                    hlib.getPlug(node + ".translate").set((*spec.translation,))
                if chain == "fk":
                    matrix = create("multMatrix", "fkMatrix" + str(index))
                    rig._bind("fkMatrix" + str(index), matrix)
                    hlib.getPlug(node + ".matrix").connectTo(hlib.getNode(matrix).getPlug("matrixIn")[0])
                    hlib.getPlug(offset + ".matrix").connectTo(hlib.getNode(matrix).getPlug("matrixIn")[1])
                if chain != "fk":
                    hlib.getPlug(node + ".segmentScaleCompensate").set(False)
                if chain == "ik":
                    hlib.getPlug(node + ".visibility").set(False)
                parent = node
        for role, position in (
            ("target", (length * 0.8, 0, 0)),
            ("pole", (length * 0.5, length, 0)),
        ):
            offset = create("transform", role + "Offset", rig._member("ikControls"))
            hlib.getPlug(offset + ".translate").set((*position,))
            rig._bind(role + "Offset", offset)
            rig._bind(role, create("transform", role, offset))
        target, pole = rig._member("target"), rig._member("pole")
        matrix = create("multMatrix", "targetMatrix")
        rig._bind("targetMatrix", matrix)
        hlib.getPlug(target + ".matrix").connectTo(hlib.getNode(matrix).getPlug("matrixIn")[0])
        hlib.getPlug(rig._member("targetOffset") + ".matrix").connectTo(hlib.getNode(matrix).getPlug("matrixIn")[1])
        target_decompose = create("decomposeMatrix", "targetDecompose")
        rig._bind("targetDecompose", target_decompose)
        hlib.getPlug(matrix + ".matrixSum").connectTo(target_decompose + ".inputMatrix")
        target_rotation = create("transform", "targetRotation", rig._member("ikSetup"))
        rig._bind("targetRotation", target_rotation)
        hlib.getNode(target).addAttr(
            longName="softness",
            attributeType="double",
            minValue=0,
            maxValue=length,
            defaultValue=length * 0.1,
            keyable=True,
        )
        # preferredAngleで伸び切った初期チェーンの曲げ平面を定義する。
        hlib.getPlug(rig._member("ik1") + ".preferredAngleZ").set(math.radians(-10))
        handle, effector = hlib.createIkHandle(
            startJoint=rig._member("ik0"),
            endEffector=rig._member("ik2"),
            solver="ikRPsolver",
            name=names["handle"],
        )
        effector = hlib.getNode(effector).rename(names["effector"])
        created.extend((handle, effector))
        handle = hlib.getNode(handle).setParent(rig._member("ikSetup")).getFullName()
        rig._bind("handle", handle)
        constraints = [
            hlib.addConstraint(
                pole, handle, type="poleVector", name=names["handle"] + "_poleVectorConstraint"
            )
        ]
        constraints.append(
            hlib.addConstraint(
                target_rotation,
                rig._member("ik2"),
                type="orient",
                maintainOffset=False,
                name=names["ik2"] + "_orientConstraint",
            )
        )
        created.extend(constraints)
        rig._layer_members("ikSet", constraints + [hlib.getNode(effector)])
        hlib.getPlug(handle + ".visibility").set(False)
        graph, graph_parent = create_soft_ik(names["soft"], length, backend)
        created.append(graph_parent)
        if graph_parent != graph:
            from hlib.nodes import Node

            graph_ref = Node(graph)
            graph_parent = hlib.getNode(graph_parent).setParent(rig._member("softSetup")).getFullName()
            created[-1] = graph_parent
            graph = graph_ref.getFullName()
            hlib.getPlug(graph + ".visibility").set(False)
        rig._bind("softGraph", graph)
        rig._bind("softOwner", graph_parent)
        distance = create("distanceBetween", "distance")
        rig._bind("distance", distance)
        hlib.getPlug(target + ".translate").connectTo(distance + ".point2")
        hlib.getPlug(distance + ".distance").connectTo(graph + ".distance")
        hlib.getPlug(target + ".softness").connectTo(graph + ".softness")
        scale = create("multiplyDivide", "softScale")
        rig._bind("softScale", scale)
        hlib.getPlug(target + ".translate").connectTo(scale + ".input1")
        for axis in "XYZ":
            hlib.getPlug(graph + ".ratio").connectTo(scale + ".input2" + axis)
        helper = create("joint", "helper", rig._member("joint1"))
        rig._bind("helper", helper)
        hlib.getPlug(helper + ".translateX").set(ordered[2].translation[0] * 0.5)
        hlib.getPlug(helper + ".segmentScaleCompensate").set(False)
        decompose = create("decomposeMatrix", "helperDecompose")
        half = create("multiplyDivide", "helperScale")
        rig._bind("helperDecompose", decompose)
        rig._bind("helperScale", half)
        hlib.getPlug(decompose + ".outputRotate").connectTo(half + ".input1")
        hlib.getPlug(half + ".input2").set(
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
        hlib.getNode(root).addAttr(longName="hrigOwned", attributeType="message", multi=True)
        for index, node in enumerate(created):
            if node != root and cmds.objExists(node):
                hlib.getNode(node).getPlug("message").connectTo(hlib.getNode(root).getPlug("hrigOwned")[index])
        from .spaceLayer import SpaceLayer

        SpaceLayer(rig).attach()
        rig.set_mode("fk")
        from .channel_controls import attach

        attach(rig)
        return rig
    except Exception:
        for node in reversed(created):
            if cmds.objExists(node):
                hlib.delete(node)
        raise
    finally:
        hlib.select(saved_selection, replace=True) if saved_selection else hlib.select(clear=True)
