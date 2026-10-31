"""操作用カーブと高低メッシュを持つ最小リグのデモ。"""

import mlib

from mlib.decorator import undoTransaction
from mlrig import build_limb, limb_definition
from mlrig.reverse_foot import add_reverse_foot
from mlrig.skin import bind_mesh, create_skin_lod, set_mesh_lod


@undoTransaction("mlrig.build_demo")
def build_demo(name="rig", backend="standard", twist_count=3, bend_helpers=True):
    """デモを現在シーンへ追加する。同名ノードがあれば拒否する。

    Args:
        name (str): 新しい部位ルート名。
        backend (str): standard（標準ノード）、bifrostまたはcpp。
        twist_count (int): 各区間のツイスト補助骨数。0なら生成しない。
        bend_helpers (bool): 肘の回転補間・内側・外側の補助骨を追加する。

    Returns:
        dict: rig、高低メッシュ、各skinClusterへの参照。
    """
    if type(twist_count) is not int or twist_count < 0:
        raise ValueError("twist_count must be a non-negative integer")
    prefix = "" if name == "rig" else name + "_"
    high_name, proxy_name = prefix + "body_geo", prefix + "body_proxy_geo"
    for node in (name, high_name, proxy_name):
        if mlib.objExists(node):
            raise ValueError("Demo node already exists: " + node)
    rig = build_limb(limb_definition(name), backend=backend)
    if bend_helpers:
        rig.add_bend()
        # デモのPoleは+Yで、中間関節は-Z方向に曲がるため内外も反転する。
        settings = rig.bend_settings()
        for attr, value in (
            ("bendSign", -1),
            ("innerRest", -0.5),
            ("outerRest", 0.5),
            ("innerPush", 0.2),
            ("outerPush", 0.2),
        ):
            settings.getPlug(attr).set(value)
    if twist_count:
        root, mid, tip = rig.getJoints()[:3]
        rig.add_twist("upper", root, mid, twist_count)
        rig.add_twist("lower", mid, tip, twist_count)
    from mlrig.setups import ControlShape

    for role, control in rig.controls().items():
        ControlShape.circle(control, radius=0.45, color=17 if role.startswith("fk") else 6)
    ui = mlib.common.units.distanceFromUi
    high = mlib.createPolyCube(width=ui(10), height=ui(1), depth=ui(1), subdivisions=(16, 1, 1), name=high_name).getParent()
    proxy = mlib.createPolyCube(width=ui(10), height=ui(1), depth=ui(1), subdivisions=(4, 1, 1), name=proxy_name).getParent()
    for mesh in (high, proxy):
        mesh.getPlug("translateX").set(5)
        mesh.makeIdentity(apply=True, translate=True)
        mesh.setParent(rig._member("moduleGeometry"))
    # デモの公開戻り値は従来通り名前。構築中は型付き参照で扱う。
    high, proxy = high.getFullName(), proxy.getFullName()
    high_skin = bind_mesh(rig, high)
    proxy_skin = create_skin_lod(rig, high, proxy, high_skin)
    rig._layer_members("moduleSet", [high, proxy, high_skin, proxy_skin])
    set_mesh_lod(high, high_skin, proxy, proxy_skin, proxy=True)
    add_reverse_foot(rig)
    rig.set_mode("ik")
    mlib.select(rig._member("channelModule"), replace=True)
    return {
        "rig": rig,
        "high_mesh": high,
        "high_skin": high_skin,
        "proxy_mesh": proxy,
        "proxy_skin": proxy_skin,
    }


if __name__ == "__main__":
    build_demo()
