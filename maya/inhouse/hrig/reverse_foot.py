"""3関節部位のIKへ後付けする、ローカル行列ベースのリバースフット。"""

import math
import json
from maya import cmds
from hlib.decorators.undo import undo_transaction


@undo_transaction('hrig.add_reverse_foot')
def add_reverse_foot(rig, heel=(-1,0,0), toe=(2,0,0), ball=(1,0,0)):
    """IK目標の下へheel→toe→ballの回転ピボットを重ねる。

    Args:
        rig (LimbRig): 構築済みの部位。
        heel (tuple): 足首原点・目標コントローラー空間の踵位置。
        toe (tuple): 同じ空間の爪先位置。
        ball (tuple): 同じ空間の母指球位置。
    Returns:
        dict[str, str]: ピボット名と生成したtransformの対応。
    Note:
        正Xを足先、Yを上とし、ロール軸はZ。LOD 1だけで有効。
        足ロールが非ゼロの姿勢からのIKマッチは未対応。
    """
    pivots=[tuple(float(v) for v in point) for point in (heel,toe,ball)]
    if any(len(point)!=3 or not all(math.isfinite(v) for v in point) for point in pivots):
        raise ValueError('Expected finite three-component pivots')
    root=rig.root.full_name()
    if cmds.attributeQuery('footMatrix',node=root,exists=True):
        raise ValueError('A reverse-foot layer already exists')
    target=rig.controls()['target']
    for attr in ('heelRoll','toeRoll','ballRoll'):
        if cmds.attributeQuery(attr,node=target,exists=True):
            raise ValueError('Target attribute already exists: '+attr)
    group=cmds.createNode('transform',name=rig.node_name('footGroup'),parent=target,skipSelect=True)
    from .limb import _lock_group
    _lock_group(group)
    rig._bind('footGroup',group)
    parent=group; created=[group];result={}
    for role,pivot in zip(('heel','toe','ball'),pivots):
        node=cmds.createNode('transform',name=rig.node_name(role),parent=parent,skipSelect=True)
        created.append(node);result[role]=node
        cmds.setAttr(node+'.rotatePivot',*pivot)
        cmds.addAttr(target,longName=role+'Roll',attributeType='doubleAngle',keyable=True)
        cmds.connectAttr(target+'.'+role+'Roll',node+'.rotateZ')
        parent=node
    matrix=cmds.createNode('multMatrix',name=rig.node_name('footMatrix'),skipSelect=True)
    decompose=cmds.createNode('decomposeMatrix',name=rig.node_name('footDecompose'),skipSelect=True)
    created.extend((matrix,decompose))
    for index,node in enumerate((result['ball'],result['toe'],result['heel'])):
        cmds.connectAttr(node+'.matrix',matrix+'.matrixIn[{}]'.format(index))
    cmds.connectAttr(rig._local_matrix('target'),matrix+'.matrixIn[3]')
    cmds.connectAttr(matrix+'.matrixSum',decompose+'.inputMatrix')
    rig._bind('footMatrix',matrix);rig._bind('footDecompose',decompose)
    layer=cmds.sets(created, name=rig.node_name('footSet'))
    created.append(layer)
    rig._bind('footSet',layer)
    rig._layer_members('moduleSet',[layer])
    cmds.addAttr(root,longName='hrigFootSettings',dataType='string')
    cmds.setAttr(root+'.hrigFootSettings',json.dumps(dict(zip(('heel','toe','ball'),pivots))),type='string')
    indices=cmds.getAttr(root+'.hrigOwned',multiIndices=True) or []
    first=max(indices,default=-1)+1
    for index,node in enumerate(created,first):
        cmds.connectAttr(node+'.message',root+'.hrigOwned[{}]'.format(index))
    rig._update_evaluation()
    return result
