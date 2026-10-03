"""標準アウトライナーとチャンネルボックスによる構成操作。

GUIのscriptJobを使用し、操作と接続変更を同じUndoへまとめる。
設定はアニメーション用ではない。バッチではLimbRigのメソッドを使用する。
"""

from maya import cmds

from functools import partial
import hlib

from hlib.decorators.undo import undoTransaction

# reload時に旧コールバックを残さない。hlibの再読込では所有参照を維持する。
for _owner in globals().get("_jobs", {}).values():
    _owner.stop()
if globals().get("_events") is not None:
    _events.stop()
_jobs = {}
_events = hlib.events.ScriptJobs()
_busy = False
LAYERS = (
    "fk",
    "ik",
    "soft",
    "helper",
    "foot",
    "space",
    "twist",
    "bend",
    "driven",
    "follow",
    "stretch",
)
LABELS = {
    "fk": "fk",
    "ik": "ik",
    "soft": "soft_ik",
    "helper": "helper",
    "foot": "reverse_foot",
    "space": "space",
    "twist": "twist",
    "bend": "bend",
    "driven": "driven",
    "follow": "follow",
    "stretch": "stretch",
}


def _write(plug, value):
    """表示属性を同期する。ロックと変更通知の管理はhlibに委譲する。

    Args:
        plug (str): 表示属性の名前。
        value (bool | int): 適用済みの状態。
    """
    hlib.getPlug(plug).setIfChanged(value, unlock=True)


def _attribute(node, name, kind="bool", default=0, enum=None, readonly=False):
    """キー対象外の設定・状態属性をチャンネルボックスへ表示する。

    Args:
        node (str): 追加先ノード。
        name (str): 属性名。
        kind (str): Mayaの属性型。既定はbool。
        default (bool | int): 属性の既定値。
        enum (str | None): コロン区切りのenum名。
        readonly (bool): Trueなら属性をロックする。
    """
    args = {"longName": name, "attributeType": kind, "defaultValue": default}
    if enum:
        args["enumName"] = enum
    reference = hlib.getNode(node)
    reference.addAttribute(**args)
    reference.setAttributeFlags([name], keyable=False, channelBox=True, locked=readonly)


def _exists(rig):
    """構成表示が接続済みかを照会する。

    Args:
        rig (LimbRig): 照会するリグ。


    Returns:
        bool: 表示用モジュールの参照があればTrue。
    """
    return (
        rig.root.hasAttribute("channelModule") and rig.root.plug("channelModule").source() is not None
    )


def _states(rig):
    """計算経路へ適用したレイヤー状態を計算する。

    Args:
        rig (LimbRig): 照会するリグ。


    Returns:
        dict[str, bool]: レイヤー識別子と実際の有効状態。
    """
    ik = rig.mode() == "ik"
    detail = rig.lod() == 1
    states = {
        "fk": not ik,
        "ik": ik,
        "soft": ik and detail and rig.layer_enabled("soft"),
        "helper": detail and rig.layer_enabled("helper"),
        "foot": ik
        and detail
        and rig.layer_enabled("foot")
        and hlib.getNode(rig.root.fullName()).hasAttribute("footMatrix"),
    }
    if rig.root.hasAttribute("targetSpace"):
        states["space"] = True
    if rig.root.hasAttribute("channel_twist"):
        states["twist"] = detail and rig.layer_enabled("twist") and bool(rig.twist_joints())
    if rig.root.hasAttribute("channel_bend"):
        states["bend"] = detail and rig.layer_enabled("bend") and bool(rig.bend_joints())
    if rig.root.hasAttribute("channel_driven"):
        from .drivenLayer import DrivenLayer

        states["driven"] = (
            detail and rig.layer_enabled("driven") and bool(DrivenLayer(rig).graphs())
        )
    if rig.root.hasAttribute("channel_follow"):
        states["follow"] = detail and rig.layer_enabled("follow") and bool(rig.follow_joints())
    if rig.root.hasAttribute("channel_stretch"):
        from .limbStretchLayer import LimbStretchLayer

        states["stretch"] = LimbStretchLayer(rig).active()
    return states


def sync_display(rig):
    """適用済み状態を表示へ同期する。既存Python操作からも呼ばれる。

    Args:
        rig (LimbRig): 状態の取得元リグ。
    """
    if not _exists(rig):
        return
    if rig.root.hasAttribute("targetSpace"):
        from .spaceLayer import SpaceLayer

        SpaceLayer(rig).sync()
    module = rig._member("channelModule")
    _write(module + ".mode", int(rig.mode() == "ik"))
    _write(module + ".lod", rig.lod())
    for layer, active in _states(rig).items():
        node = rig._member("channel_" + layer)
        if layer in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch"):
            _write(node + ".enabled", rig.layer_enabled(layer))
        _write(node + ".active", active)
        color = (0.35, 0.8, 0.45) if active else (0.4, 0.4, 0.4)
        if any(abs(a - b) > 1e-6 for a, b in zip(hlib.getPlug(node + ".outlinerColor").get(), color)):
            hlib.getPlug(node + ".outlinerColor").set((*color,))


@undoTransaction("hrig.channel_controls.attach")
def attach(rig):
    """構成表示階層を追加する。既存リグにも明示的に追加できる。

    Args:
        rig (LimbRig): 操作対象。

    Returns:
        str: チャンネルボックス操作用モジュール。
    """
    if _exists(rig):
        install()
        return rig._member("channelModule")
    from .limb import _lock_group

    root = rig.root.fullName()
    stem = rig.nodeName("moduleSet").removesuffix("_set")
    group_name = (
        "modules_grp"
        if root.rsplit("|", 1)[-1] == "rig"
        else root.rsplit("|", 1)[-1] + "_modules_grp"
    )
    names = [group_name, stem] + [stem + "_" + LABELS[layer] + "_layer" for layer in LAYERS]
    if any(cmds.objExists(name) for name in names):
        raise ValueError("Module display names already exist")
    nodes = []
    group = hlib.createNode("transform", name=group_name, parent=root, skipSelect=True).fullName()
    hlib.reorder(group, front=True)
    module = hlib.createNode("transform", name=stem, parent=group, skipSelect=True).fullName()
    nodes.extend((group, module))
    rig._bind("channelModule", module)
    hlib.getNode(module).addAttribute(longName="hrigChannelRoot", attributeType="message")
    hlib.getPlug(root + ".message").connect(module + ".hrigChannelRoot")
    _attribute(module, "mode", "enum", int(rig.mode() == "ik"), "FK:IK")
    _attribute(module, "lod", "enum", rig.lod(), "Low:Full")
    _attribute(module, "matchOnSwitch", default=True)
    for layer, name in zip(LAYERS, names[2:]):
        node = hlib.createNode("transform", name=name, parent=module, skipSelect=True).fullName()
        nodes.append(node)
        rig._bind("channel_" + layer, node)
        if layer in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch"):
            attr = "hrigEnabled_" + layer
            if not hlib.getNode(root).hasAttribute(attr):
                hlib.getNode(root).addAttribute(longName=attr, attributeType="bool", defaultValue=True)
            _attribute(node, "enabled", default=rig.layer_enabled(layer))
        _attribute(node, "active", readonly=True)
        hlib.getPlug(node + ".useOutlinerColor").set(True)
    for node in nodes:
        _lock_group(node)
        hlib.getNode(node).setAttributeFlags(
            ["visibility"], keyable=False, channelBox=False, locked=True
        )
    for node in nodes:
        hlib.getNode(root).plug("hrigOwned").appendMessage(node)
    sync_display(rig)
    install()
    return module


def apply(rig):
    """表示側の要求を適用する。GUI以外の検証でも明示的に呼べる。

    Args:
        rig (LimbRig): 構成表示を持つリグ。
    """
    module = rig._member("channelModule")
    mode = ("fk", "ik")[hlib.getPlug(module + ".mode").get()]
    lod = hlib.getPlug(module + ".lod").get()
    enabled = {
        layer: bool(hlib.getPlug(rig._member("channel_" + layer) + ".enabled").get())
        for layer in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch")
        if rig.root.hasAttribute("channel_" + layer)
    }
    spaces = {}
    if rig.root.hasAttribute("targetSpace"):
        for role in ("target", "pole"):
            switch = rig.space_switch(role)
            requested = hlib.getPlug(rig._member(role) + ".space").get()
            spaces[role] = switch.labels()[requested]
    if (
        all(rig.space_switch(role).current() == label for role, label in spaces.items())
        and mode == rig.mode()
        and lod == rig.lod()
        and all(value == rig.layer_enabled(layer) for layer, value in enabled.items())
    ):
        return
    try:
        with undoTransaction("hrig.channel_controls.apply"):
            for role, label in spaces.items():
                if rig.space_switch(role).current() != label:
                    rig.set_space(role, label)
            if mode != rig.mode() and hlib.getPlug(module + ".matchOnSwitch").get():
                # 通常のチャンネルボックス操作は一度に一属性だけ変更する。
                # モードと詳細設定を同時変更するスクリプトは公開メソッドを順に使う。
                if mode == "fk":
                    rig.match_fk()
                else:
                    rig.match_ik()
            if mode != rig.mode():
                rig.set_mode(mode)
            if lod != rig.lod():
                rig.set_lod(lod)
            for layer, value in enabled.items():
                if rig.layer_enabled(layer) != value:
                    rig.set_layer_enabled(layer, value)
    except Exception:
        sync_display(rig)
        raise


def _changed(root_uuid):
    """属性変更をまとめて適用する。削除・改名と再入を考慮する。

    Args:
        root_uuid (str): 操作対象ルートのUUID。
    """
    global _busy
    if _busy:
        return
    roots = [item.fullName() for item in hlib.ls(root_uuid, long=True)] or []
    if not roots:
        return
    _busy = True
    try:
        from .limb import LimbRig

        apply(LimbRig(roots[0]))
    except Exception as error:
        hlib.utils.logger.warning("hrig: " + str(error))
    finally:
        _busy = False


def refresh_jobs():
    """シーン読込・Undo/Redo後に、生存するリグだけを監視する。"""
    if cmds.about(batch=True):
        return
    from .limb import LimbRig

    for key, jobs in list(_jobs.items()):
        if not hlib.ls(key) or not jobs.exists():
            jobs.stop()
            del _jobs[key]
    for plug in [item.fullName() for item in hlib.ls("*.hrigChannelRoot", recursive=True)] or []:
        module = plug.rsplit(".", 1)[0]
        source = hlib.getPlug(plug).source()
        if source is None:
            continue
        root = source.node
        key = root.uuid()
        if key in _jobs:
            continue
        rig = LimbRig(root)
        attrs = [module + ".mode", module + ".lod"]
        attrs += [
            rig._member("channel_" + layer) + ".enabled"
            for layer in ("soft", "helper", "foot", "twist", "bend", "driven", "follow", "stretch")
            if rig.root.hasAttribute("channel_" + layer)
        ]
        if rig.root.hasAttribute("targetSpace"):
            attrs += [rig._member(role) + ".space" for role in ("target", "pole")]
        jobs = hlib.events.ScriptJobs()
        try:
            for attr in attrs:
                jobs.add(
                    attr,
                    attribute=attr,
                    callback=partial(_changed, key),
                    kill_with_scene=True,
                    compress_undo=True,
                )
        except Exception:
            jobs.stop()
            raise
        _jobs[key] = jobs

    from .skirtRig import SkirtRig

    SkirtRig.refresh_jobs()
    from .splineRig import SplineRig

    SplineRig.refresh_jobs()
    from .controlRig import ControlRig
    from .tweakLayer import TweakLayer

    ControlRig.refresh_jobs()
    TweakLayer.refresh_jobs()


def install():
    """GUIで監視を開始する。多重登録せず、シーンへ実行スクリプトを埋め込まない。"""
    if cmds.about(batch=True):
        return
    for event in ("PostSceneRead", "NewSceneOpened", "Undo", "Redo"):
        _events.add(event, event=event, callback=refresh_jobs)
    refresh_jobs()
