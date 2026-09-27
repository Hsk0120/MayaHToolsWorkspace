"""操作用カーブと高低メッシュを持つ最小リグのデモ。"""

from maya import cmds
from hlib.decorators.undo import undo_transaction
from hrig import build_limb, limb_definition
from hrig.reverse_foot import add_reverse_foot
from hrig.skin import bind_mesh, create_skin_lod, set_mesh_lod


@undo_transaction('hrig.build_demo')
def build_demo(name='rig', backend='bifrost'):
    """デモを現在シーンへ追加する。同名ノードがあれば拒否する。

    Args:
        name (str): 新しい部位ルート名。
        backend (str): bifrostまたはcpp。
    Returns:
        dict: rig、高低メッシュ、各skinClusterへの参照。
    """
    prefix = '' if name == 'rig' else name + '_'
    high_name, proxy_name = prefix + 'body_geo', prefix + 'body_proxy_geo'
    for node in (name, high_name, proxy_name):
        if cmds.objExists(node):
            raise ValueError('Demo node already exists: '+node)
    rig=build_limb(limb_definition(name),backend=backend)
    for role,control in rig.controls().items():
        curve=cmds.circle(normal=(0,0,1),radius=0.45,constructionHistory=False)[0]
        for shape in cmds.listRelatives(curve,shapes=True,fullPath=True) or []:
            shape = cmds.parent(shape,control,shape=True,relative=True)[0]
            cmds.rename(shape,control.rsplit('|',1)[-1]+'Shape')
        cmds.delete(curve)
        cmds.setAttr(control+'.overrideEnabled',True)
        cmds.setAttr(control+'.overrideColor',17 if role.startswith('fk') else 6)
    high=cmds.polyCube(name=high_name,width=10,height=1,depth=1,subdivisionsX=16,constructionHistory=False)[0]
    proxy=cmds.polyCube(name=proxy_name,width=10,height=1,depth=1,subdivisionsX=4,constructionHistory=False)[0]
    for mesh in (high,proxy):
        cmds.setAttr(mesh+'.translateX',5)
        cmds.makeIdentity(mesh,apply=True,translate=True)
    high = cmds.parent(high, rig._member('moduleGeometry'))[0]
    proxy = cmds.parent(proxy, rig._member('moduleGeometry'))[0]
    high_skin=bind_mesh(rig,high)
    proxy_skin=create_skin_lod(rig,high,proxy,high_skin)
    rig._layer_members('moduleSet',[high,proxy,high_skin,proxy_skin])
    set_mesh_lod(high,high_skin,proxy,proxy_skin,proxy=True)
    add_reverse_foot(rig)
    rig.set_mode('ik')
    cmds.select(rig._member('channelModule'),replace=True)
    return {'rig':rig,'high_mesh':high,'high_skin':high_skin,
            'proxy_mesh':proxy,'proxy_skin':proxy_skin}


if __name__=='__main__':
    build_demo()
