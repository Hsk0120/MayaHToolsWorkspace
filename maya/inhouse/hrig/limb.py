"""3関節のFK/IKとSoft IKの最小実装。切替は明示メソッドで行う。"""

import json
import math
from maya import cmds
from hlib.decorators.undo import undo_chunk
from hlib.decorators.undo import undo_transaction
from .definition import limb_definition, RigDefinition
from .backends import create_soft_ik
from .naming import limb_names


def _disconnect(destination):
    """入力接続を切断する。値は呼び出し側で設定する。"""
    source = cmds.connectionInfo(destination, sourceFromDestination=True)
    if source:
        cmds.disconnectAttr(source, destination)


def _lock_group(node):
    """整理専用グループの座標を固定し、部位空間の計算を維持する。"""
    for attr in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz',
                 'shearXY', 'shearXZ', 'shearYZ'):
        cmds.setAttr(node + '.' + attr, lock=True, keyable=False, channelBox=False)


def _set_world_matrix(node, matrix):
    """ゼロピボットの操作transformへ姿勢をローカル値として適用する。

    Args:
        node (str): hrigが作成したコントローラー。
        matrix (Sequence[float]): 目標のワールド行列。
    Note:
        xform(worldSpace=True)のRedo時の親空間再変換を避けるため、
        計算済みTRSを標準setAttrで保存する。ピボット編集は対象外。
    """
    from maya.api import OpenMaya as om
    inverse = om.MMatrix(cmds.getAttr(node + '.parentInverseMatrix[0]'))
    local = om.MTransformationMatrix(om.MMatrix(matrix) * inverse)
    rotation = local.rotation()
    rotation.reorderIt(cmds.getAttr(node + '.rotateOrder'))
    cmds.setAttr(node + '.translate', *local.translation(om.MSpace.kTransform))
    cmds.setAttr(node + '.rotate', *(om.MAngle(value).asUnits(om.MAngle.uiUnit()) for value in rotation))
    cmds.setAttr(node + '.scale', *local.scale(om.MSpace.kTransform))
    cmds.setAttr(node + '.shear', *local.shear(om.MSpace.kTransform))


class LimbRig:
    """構築した部位の参照。保存後はfrom_rootで再取得する。"""

    def __init__(self, root):
        """既存のhrig部位ルートを保持する。"""
        from hlib.nodes import Node
        self.root = Node(root)
        if not cmds.attributeQuery('hrigDefinition', node=self.root.full_name(), exists=True):
            raise ValueError('Not an hrig root')

    def _member(self, role):
        """メッセージ接続から現在名を解決する。改名・再親子付けに追従する。"""
        nodes = cmds.listConnections(self.root.full_name() + '.' + role,
                                     source=True, destination=False, shapes=True) or []
        if len(nodes) != 1:
            raise RuntimeError('Missing rig member: ' + role)
        from hlib._core.coerce import to_node_name
        return to_node_name(nodes[0])

    def _bind(self, role, node):
        """生成物へのメッセージ参照を登録する。"""
        root = self.root.full_name()
        cmds.addAttr(root, longName=role, attributeType='message')
        cmds.connectAttr(node + '.message', root + '.' + role)

    def controls(self):
        """dict: FK、IK目標、poleの現在名を返す。"""
        return {key: self._member(key) for key in ('fk0', 'fk1', 'fk2', 'target', 'pole')}

    def node_name(self, role):
        """str: 保存した定義に基づく生成名を返す。"""
        definition = RigDefinition.from_data(json.loads(cmds.getAttr(
            self.root.full_name() + '.hrigDefinition')))
        return limb_names(definition)[role]

    def _layer_members(self, role, nodes):
        """レイヤーの選択セットへ生成ノードを登録する。"""
        if cmds.attributeQuery(role, node=self.root.full_name(), exists=True):
            cmds.sets(nodes, add=self._member(role))

    def _local_matrix(self, role):
        """str: オフセットを含む親コントローラー空間の行列プラグ。旧リグも扱う。"""
        member = 'targetMatrix' if role == 'target' else 'fkMatrix' + role[2:]
        if role.startswith('fk') or role == 'target':
            if cmds.attributeQuery(member, node=self.root.full_name(), exists=True):
                return self._member(member) + '.matrixSum'
        return self._member(role) + '.matrix'

    def joints(self):
        """tuple[str]: 変形用3関節と補助骨を返す。"""
        return tuple(self._member(key) for key in ('joint0', 'joint1', 'joint2', 'helper'))

    def mode(self):
        """str: 現在の明示切替モード。"""
        return cmds.getAttr(self.root.full_name() + '.hrigMode')

    def lod(self):
        """int: 現在のLOD。0はSoft IK・補助骨なし、1は全機能。"""
        return cmds.getAttr(self.root.full_name() + '.hrigLod')

    @undo_transaction('hrig.LimbRig.set_backend')
    def set_backend(self, backend):
        """Soft IK実装だけを交換し、骨・コントローラー・スキンを保持する。"""
        if backend not in ('bifrost', 'cpp'):
            raise ValueError('Unknown backend: ' + backend)
        root = self.root.full_name()
        if cmds.getAttr(root + '.hrigBackend') == backend:
            return
        old = self._member('softGraph')
        old_owner = self._member('softOwner')
        if old_owner == root:
            raise RuntimeError('Invalid Soft IK ownership: rig root cannot be replaced')
        length = cmds.getAttr(root + '.hrigLength')
        source = cmds.connectionInfo(old + '.distance', sourceFromDestination=True)
        graph, owner = create_soft_ik(self.node_name('soft'),length,backend)
        if owner != graph:
            from hlib.nodes import Node
            reference = Node(graph)
            parent = self._member('softSetup') if cmds.attributeQuery('softSetup',node=root,exists=True) else root
            owner = cmds.parent(owner,parent)[0]
            graph = reference.full_name()
            cmds.setAttr(graph+'.visibility',False)
        cmds.connectAttr(source,graph+'.distance')
        cmds.connectAttr(self._member('target')+'.softness',graph+'.softness')
        for axis in 'XYZ':
            cmds.connectAttr(graph+'.ratio',self._member('softScale')+'.input2'+axis,force=True)
        cmds.connectAttr(graph+'.message',root+'.softGraph',force=True)
        cmds.connectAttr(owner+'.message',root+'.softOwner',force=True)
        indices = cmds.getAttr(root+'.hrigOwned',multiIndices=True) or []
        cmds.connectAttr(owner+'.message',root+'.hrigOwned[{}]'.format(max(indices,default=-1)+1))
        self._layer_members('softSet', [owner, graph])
        cmds.setAttr(root+'.hrigBackend',backend,type='string')
        self._update_evaluation()
        cmds.delete(old_owner)

    @undo_chunk('hrig.LimbRig.delete')
    def delete(self):
        """所有する生成物を削除する。外部スキンやアニメーションの保護は呼出側で行う。"""
        root = self.root.full_name()
        owned = cmds.listConnections(root + '.hrigOwned', source=True, destination=False, shapes=True) or []
        # DAGを一括で削除すると子の重複指定があり得るため、存在確認して順に消す。
        for node in owned:
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.objExists(root):
            cmds.delete(root)

    @undo_chunk('hrig.LimbRig.set_mode')
    def set_mode(self, mode):
        """FK/IKを切り替える。姿勢合わせはmatch_fk/match_ikを先に呼ぶ。"""
        if mode not in ('fk', 'ik'):
            raise ValueError('mode must be fk or ik')
        for index in range(3):
            source = self._local_matrix(('fk' if mode == 'fk' else 'ik') + str(index))
            destination = self._member('joint' + str(index)) + '.offsetParentMatrix'
            _disconnect(destination)
            cmds.connectAttr(source, destination)
        cmds.setAttr(self.root.full_name() + '.hrigMode', mode, type='string')
        self._update_evaluation()

    def layer_enabled(self, layer):
        """bool: 任意レイヤーの使用設定を照会する。旧シーンは有効扱い。"""
        attr = 'hrigEnabled_' + layer
        root = self.root.full_name()
        return bool(cmds.getAttr(root + '.' + attr)) if cmds.attributeQuery(attr,node=root,exists=True) else True

    @undo_chunk('hrig.LimbRig.set_layer_enabled')
    def set_layer_enabled(self, layer, enabled):
        """Soft IK・補助骨・足レイヤーの使用設定を変更する。"""
        if layer not in ('soft', 'helper', 'foot'):
            raise ValueError('Unknown optional layer: ' + layer)
        root = self.root.full_name()
        attr = 'hrigEnabled_' + layer
        if not cmds.attributeQuery(attr,node=root,exists=True):
            cmds.addAttr(root,longName=attr,attributeType='bool',defaultValue=True)
        cmds.setAttr(root + '.' + attr, bool(enabled))
        self._update_evaluation()

    @undo_chunk('hrig.LimbRig.set_lod')
    def set_lod(self, lod):
        """0/1を選び、不要な経路を切断する。スキンLODは別操作。"""
        if type(lod) is not int or lod not in (0, 1):
            raise ValueError('This prototype supports LOD 0 or 1')
        cmds.setAttr(self.root.full_name() + '.hrigLod', lod)
        self._update_evaluation()

    def _update_evaluation(self):
        """計算経路を明示的に接続/切断し、IKハンドルをブロックする。"""
        ik = self.mode() == 'ik'
        detailed = self.lod() == 1
        handle, graph = self._member('handle'), self._member('softGraph')
        scale = self._member('softScale')
        root = self.root.full_name()
        target = self._member('target')
        soft = detailed and self.layer_enabled('soft')
        foot = detailed and self.layer_enabled('foot') and cmds.attributeQuery('footMatrix',node=root,exists=True)
        position = target+'.translate'
        if cmds.attributeQuery('targetDecompose',node=root,exists=True):
            position = self._member('targetDecompose')+'.outputTranslate'
        position = self._member('footDecompose')+'.outputTranslate' if foot else position
        matrix = self._member('footMatrix')+'.matrixSum' if foot else self._local_matrix('target')
        for destination in (self._member('distance')+'.point2', scale+'.input1'):
            _disconnect(destination)
            cmds.connectAttr(position,destination)
        rotation_input = self._member('targetRotation')+'.offsetParentMatrix'
        _disconnect(rotation_input)
        cmds.connectAttr(matrix,rotation_input)
        cmds.setAttr(handle + '.nodeState', 0 if ik else 2)
        _disconnect(handle + '.translate')
        if ik:
            source = scale + '.output' if soft else position
            cmds.connectAttr(source, handle + '.translate')
        # Bifrostを非表示にしても評価停止にはならない。接続も外してblockする。
        cmds.setAttr(graph + '.nodeState', 0 if ik and soft else 2)
        helper = self._member('helper')
        _disconnect(helper + '.rotate')
        if detailed and self.layer_enabled('helper'):
            source = self._local_matrix(('ik' if ik else 'fk') + '1')
            decompose = self._member('helperDecompose')
            _disconnect(decompose + '.inputMatrix')
            cmds.connectAttr(source, decompose + '.inputMatrix')
            cmds.connectAttr(self._member('helperScale') + '.output', helper + '.rotate')
        else:
            cmds.setAttr(helper + '.rotate', 0, 0, 0)
        from .channel_controls import sync_display
        sync_display(self)

    @undo_chunk('hrig.LimbRig.match_fk')
    def match_fk(self):
        """現在の変形姿勢をFKへ合わせる。モード切替やキー設定は行わない。"""
        matrices = [cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in self.joints()[:3]]
        for index, matrix in enumerate(matrices):
            _set_world_matrix(self._member('fk' + str(index)), matrix)

    @undo_chunk('hrig.LimbRig.match_ik')
    def match_ik(self):
        """現在姿勢からIK目標とpoleを合わせる。Soft IK分の距離を逆算する。"""
        from maya.api import OpenMaya as om
        target = self._member('target')
        for attr in ('heelRoll','toeRoll','ballRoll') if self.lod() and self.layer_enabled('foot') else ():
            if cmds.attributeQuery(attr,node=target,exists=True) and abs(cmds.getAttr(target+'.'+attr))>1e-8:
                raise ValueError('Reset reverse-foot rolls before matching IK')
        joints = self.joints()[:3]
        a, b, c = [om.MVector(cmds.xform(j, query=True, worldSpace=True, translation=True)) for j in joints]
        axis = c - a
        if axis.length() < 1e-8:
            raise ValueError('Cannot match IK when the endpoint coincides with the root')
        projection = a + axis * (((b - a) * axis) / (axis * axis))
        offset = b - projection
        if offset.length() < 1e-8:
            offset = om.MVector(cmds.xform(self._member('pole'), query=True, worldSpace=True, translation=True)) - b
            offset -= axis * ((offset * axis) / (axis * axis))
        if offset.length() < 1e-8:
            raise ValueError('Choose a pole direction before matching a straight chain')
        pole_position = tuple(b + offset.normal() * axis.length())
        # 逆算は部位空間で行うため、ルートの一様スケールにも追従する。
        inverse = om.MMatrix(cmds.getAttr(self.root.full_name() + '.worldInverseMatrix[0]'))
        local_end = om.MPoint(c) * inverse
        distance = om.MVector(local_end).length()
        length = cmds.getAttr(self.root.full_name() + '.hrigLength')
        soft = cmds.getAttr(self._member('target') + '.softness') if self.lod() and self.layer_enabled('soft') else 0
        desired = distance
        if soft > 0 and distance > length - soft:
            if distance >= length - 1e-6:
                raise ValueError('Fully extended pose has no finite Soft IK inverse; use LOD 0')
            desired = length - soft - soft * math.log((length - distance) / soft)
        pole = self._member('pole')
        pole_local = om.MPoint(pole_position) * om.MMatrix(cmds.getAttr(pole+'.parentInverseMatrix[0]'))
        cmds.setAttr(pole+'.translate', *tuple(pole_local)[:3])
        local_position = om.MPoint(om.MVector(local_end).normal() * desired)
        world_position = local_position * inverse.inverse()
        matrix = cmds.xform(joints[-1], query=True, worldSpace=True, matrix=True)
        matrix[12:15] = tuple(world_position)[:3]
        _set_world_matrix(target, matrix)


@undo_chunk('hrig.build_limb')
def build_limb(definition=None, backend='bifrost'):
    """最小3関節リグを構築する。任意チェーンやレイヤーはまだ扱わない。

    Args:
        definition (RigDefinition | None): 単一ルート、正X軸の3関節定義。
        backend (str): Soft IK実装。bifrostまたはcpp。
    Returns:
        LimbRig: 保存・再取得可能な部位。
    """
    from hlib_bifrost import ensure_available
    definition = definition or limb_definition()
    if not isinstance(definition, RigDefinition):
        raise TypeError('Expected RigDefinition')
    ordered = definition.joint_order()
    if len(ordered) != 3 or ordered[0].parent is not None or ordered[0].translation != (0, 0, 0):
        raise ValueError('Expected a three-joint chain with root at the origin')
    for i in (1, 2):
        if ordered[i].parent != ordered[i-1].id or ordered[i].translation[0] <= 0 or ordered[i].translation[1:] != (0, 0):
            raise ValueError('Prototype joints must extend along positive local X')
    if definition.layers != limb_definition().layers:
        raise ValueError('This builder supports the default FK/IK/Soft IK/helper layers only')
    if cmds.objExists(definition.name):
        raise ValueError('Rig root already exists: ' + definition.name)
    names = limb_names(definition)
    if len(set(names.values())) != len(names):
        raise ValueError('Joint identifiers conflict with reserved rig names')
    for name in names.values():
        if cmds.objExists(name):
            raise ValueError('Rig node already exists: ' + name)
    if int(cmds.about(apiVersion=True)) < 20250000:
        raise RuntimeError('hrig requires Maya 2025 or newer')
    if backend not in ('bifrost', 'cpp'):
        raise ValueError('Unknown backend: ' + backend)
    if backend == 'bifrost':
        ensure_available()
    saved_selection = cmds.ls(selection=True, long=True) or []
    created = []

    def create(kind, suffix, parent=None):
        """生成ノードを失敗時の削除対象へ登録する。"""
        kwargs = {'parent': parent} if parent else {}
        node = cmds.createNode(kind, name=names[suffix], skipSelect=True, **kwargs)
        created.append(node)
        return node

    try:
        root = cmds.createNode('transform', name=definition.name, skipSelect=True)
        created.append(root)
        for attr in ('hrigDefinition', 'hrigMode', 'hrigBackend'):
            cmds.addAttr(root, longName=attr, dataType='string')
        cmds.setAttr(root + '.hrigDefinition', json.dumps(definition.to_data()), type='string')
        cmds.setAttr(root + '.hrigBackend', backend, type='string')
        rig = LimbRig(root)
        cmds.addAttr(root, longName='hrigLod', attributeType='long', defaultValue=1)
        length = ordered[1].translation[0] + ordered[2].translation[0]
        cmds.addAttr(root, longName='hrigLength', attributeType='double', defaultValue=length)
        for role in ('geometryGroup', 'jointGroup', 'controlGroup', 'setupGroup'):
            node = create('transform', role, root)
            _lock_group(node)
            rig._bind(role, node)
        cmds.setAttr(rig._member('setupGroup') + '.visibility', False)
        for role, parent_role in (
                ('moduleGeometry', 'geometryGroup'), ('moduleJoints', 'jointGroup'),
                ('moduleControls', 'controlGroup'), ('moduleSetup', 'setupGroup'),
                ('fkControls', 'moduleControls'), ('ikControls', 'moduleControls'),
                ('ikSetup', 'moduleSetup'), ('softSetup', 'moduleSetup'),
                ('helperSetup', 'moduleSetup')):
            node = create('transform', role, rig._member(parent_role))
            _lock_group(node)
            rig._bind(role, node)
        for role in ('moduleSet', 'fkSet', 'ikSet', 'softSet', 'helperSet'):
            node = cmds.sets(empty=True, name=names[role])
            created.append(node)
            rig._bind(role, node)
            if role != 'moduleSet':
                cmds.sets(node, add=rig._member('moduleSet'))
        for chain in ('fk', 'ik', 'joint'):
            parent = rig._member({'fk': 'fkControls', 'ik': 'ikSetup', 'joint': 'moduleJoints'}[chain])
            for index, spec in enumerate(ordered):
                if chain == 'fk':
                    offset = create('transform', 'fk' + str(index) + 'Offset', parent)
                    cmds.setAttr(offset + '.translate', *spec.translation)
                    rig._bind('fk' + str(index) + 'Offset', offset)
                    parent = offset
                node = create('joint' if chain != 'fk' else 'transform', chain + str(index), parent)
                rig._bind(chain + str(index), node)
                if chain == 'ik':
                    cmds.setAttr(node + '.translate', *spec.translation)
                if chain == 'fk':
                    matrix = create('multMatrix', 'fkMatrix' + str(index))
                    rig._bind('fkMatrix' + str(index), matrix)
                    cmds.connectAttr(node + '.matrix', matrix + '.matrixIn[0]')
                    cmds.connectAttr(offset + '.matrix', matrix + '.matrixIn[1]')
                if chain != 'fk':
                    cmds.setAttr(node + '.segmentScaleCompensate', False)
                if chain == 'ik':
                    cmds.setAttr(node + '.visibility', False)
                parent = node
        for role, position in (('target', (length * 0.8, 0, 0)), ('pole', (length * 0.5, length, 0))):
            offset = create('transform', role + 'Offset', rig._member('ikControls'))
            cmds.setAttr(offset + '.translate', *position)
            rig._bind(role + 'Offset', offset)
            rig._bind(role, create('transform', role, offset))
        target, pole = rig._member('target'), rig._member('pole')
        matrix = create('multMatrix', 'targetMatrix')
        rig._bind('targetMatrix', matrix)
        cmds.connectAttr(target + '.matrix', matrix + '.matrixIn[0]')
        cmds.connectAttr(rig._member('targetOffset') + '.matrix', matrix + '.matrixIn[1]')
        target_decompose = create('decomposeMatrix', 'targetDecompose')
        rig._bind('targetDecompose', target_decompose)
        cmds.connectAttr(matrix + '.matrixSum', target_decompose + '.inputMatrix')
        target_rotation = create('transform','targetRotation',rig._member('ikSetup'))
        rig._bind('targetRotation',target_rotation)
        cmds.addAttr(target, longName='softness', attributeType='double',
                     minValue=0, maxValue=length, defaultValue=length * 0.1, keyable=True)
        # preferredAngleで伸び切った初期チェーンの曲げ平面を定義する。
        cmds.setAttr(rig._member('ik1') + '.preferredAngleZ', -10)
        handle, effector = cmds.ikHandle(startJoint=rig._member('ik0'), endEffector=rig._member('ik2'),
                                         solver='ikRPsolver', name=names['handle'])
        effector = cmds.rename(effector, names['effector'])
        created.extend((handle, effector))
        handle = cmds.parent(handle, rig._member('ikSetup'))[0]
        rig._bind('handle', handle)
        constraints = cmds.poleVectorConstraint(pole, handle, name=names['handle'] + '_poleVectorConstraint')
        constraints += cmds.orientConstraint(target_rotation, rig._member('ik2'), maintainOffset=False,
                                             name=names['ik2'] + '_orientConstraint')
        created.extend(constraints)
        rig._layer_members('ikSet', constraints + [effector])
        cmds.setAttr(handle + '.visibility', False)
        graph, graph_parent = create_soft_ik(names['soft'], length, backend)
        created.append(graph_parent)
        if graph_parent != graph:
            from hlib.nodes import Node
            graph_ref = Node(graph)
            graph_parent = cmds.parent(graph_parent, rig._member('softSetup'))[0]
            created[-1] = graph_parent
            graph = graph_ref.full_name()
            cmds.setAttr(graph + '.visibility', False)
        rig._bind('softGraph', graph)
        rig._bind('softOwner', graph_parent)
        distance = create('distanceBetween', 'distance')
        rig._bind('distance',distance)
        cmds.connectAttr(target + '.translate', distance + '.point2')
        cmds.connectAttr(distance + '.distance', graph + '.distance')
        cmds.connectAttr(target + '.softness', graph + '.softness')
        scale = create('multiplyDivide', 'softScale')
        rig._bind('softScale', scale)
        cmds.connectAttr(target + '.translate', scale + '.input1')
        for axis in 'XYZ':
            cmds.connectAttr(graph + '.ratio', scale + '.input2' + axis)
        helper = create('joint', 'helper', rig._member('joint1'))
        rig._bind('helper', helper)
        cmds.setAttr(helper + '.translateX', ordered[2].translation[0] * 0.5)
        cmds.setAttr(helper + '.segmentScaleCompensate', False)
        decompose = create('decomposeMatrix', 'helperDecompose')
        half = create('multiplyDivide', 'helperScale')
        rig._bind('helperDecompose', decompose); rig._bind('helperScale', half)
        cmds.connectAttr(decompose + '.outputRotate', half + '.input1')
        cmds.setAttr(half + '.input2', 0.5, 0.5, 0.5)
        for role, members in {
                'fkSet': ['fkControls'] + ['fk' + str(i) for i in range(3)]
                         + ['fk' + str(i) + 'Offset' for i in range(3)]
                         + ['fkMatrix' + str(i) for i in range(3)],
                'ikSet': ['ikControls', 'ikSetup', 'target', 'pole', 'targetOffset', 'poleOffset',
                          'targetMatrix', 'targetDecompose', 'targetRotation', 'handle', 'ik0', 'ik1', 'ik2'],
                'softSet': ['softSetup', 'softGraph', 'softOwner', 'distance', 'softScale'],
                'helperSet': ['helperSetup', 'helper', 'helperDecompose', 'helperScale'],
                'moduleSet': ['moduleGeometry', 'moduleJoints', 'moduleControls', 'moduleSetup',
                              'joint0', 'joint1', 'joint2'],
        }.items():
            rig._layer_members(role, list(set(rig._member(member) for member in members)))
        cmds.addAttr(root, longName='hrigOwned', attributeType='message', multi=True)
        for index, node in enumerate(created):
            if node != root and cmds.objExists(node):
                cmds.connectAttr(node + '.message', root + '.hrigOwned[{}]'.format(index))
        rig.set_mode('fk')
        from .channel_controls import attach
        attach(rig)
        return rig
    except Exception:
        for node in reversed(created):
            if cmds.objExists(node):
                cmds.delete(node)
        raise
    finally:
        cmds.select(saved_selection, replace=True) if saved_selection else cmds.select(clear=True)
