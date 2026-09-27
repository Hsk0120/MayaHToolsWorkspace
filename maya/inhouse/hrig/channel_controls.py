"""標準アウトライナーとチャンネルボックスによる構成操作。

GUIのscriptJobを使用し、操作と接続変更を同じUndoへまとめる。
設定はアニメーション用ではない。バッチではLimbRigのメソッドを使用する。
"""

from functools import partial
from maya import cmds

import hlib
from hlib.decorators.undo import undo_transaction

# reload時に旧コールバックを残さない。hlibの再読込では所有参照を維持する。
for _owner in globals().get('_jobs', {}).values():
    _owner.stop()
if globals().get('_events') is not None:
    _events.stop()
_jobs = {}
_events = hlib.events.ScriptJobs()
_busy = False
LAYERS = ('fk', 'ik', 'soft', 'helper', 'foot')
LABELS = {'fk': 'fk', 'ik': 'ik', 'soft': 'soft_ik',
          'helper': 'helper', 'foot': 'reverse_foot'}


def _write(plug, value):
    """表示属性を同期する。ロックと変更通知の管理はhlibに委譲する。

    Args:
        plug (str): 表示属性の名前。
        value (bool | int): 適用済みの状態。
    """
    hlib.plug(plug).set_if_changed(value, unlock=True)


def _attribute(node, name, kind='bool', default=0, enum=None, readonly=False):
    """キー対象外の設定・状態属性をチャンネルボックスへ表示する。
    
    Args:
        node (str): 追加先ノード。
        name (str): 属性名。
        kind (str): Mayaの属性型。既定はbool。
        default (bool | int): 属性の既定値。
        enum (str | None): コロン区切りのenum名。
        readonly (bool): Trueなら属性をロックする。
    """
    args = {'long_name': name, 'attribute_type': kind, 'default_value': default}
    if enum:
        args['enumName'] = enum
    reference = hlib.node(node)
    reference.add_attr(**args)
    reference.set_attr_flags([name], keyable=False, channel_box=True, locked=readonly)


def _exists(rig):
    """構成表示が接続済みかを照会する。
    
    Args:
        rig (LimbRig): 照会するリグ。
    

    Returns:
        bool: 表示用モジュールの参照があればTrue。
    """
    return rig.root.has_attr('channelModule') and rig.root.plug('channelModule').source() is not None


def _states(rig):
    """計算経路へ適用したレイヤー状態を計算する。
    
    Args:
        rig (LimbRig): 照会するリグ。
    

    Returns:
        dict[str, bool]: レイヤー識別子と実際の有効状態。
    """
    ik = rig.mode() == 'ik'
    detail = rig.lod() == 1
    return {'fk': not ik, 'ik': ik,
            'soft': ik and detail and rig.layer_enabled('soft'),
            'helper': detail and rig.layer_enabled('helper'),
            'foot': ik and detail and rig.layer_enabled('foot') and hlib.node(rig.root.full_name()).has_attr('footMatrix')}


def sync_display(rig):
    """適用済み状態を表示へ同期する。既存Python操作からも呼ばれる。
    
    Args:
        rig (LimbRig): 状態の取得元リグ。
    """
    if not _exists(rig):
        return
    module = rig._member('channelModule')
    _write(module + '.mode', int(rig.mode() == 'ik'))
    _write(module + '.lod', rig.lod())
    for layer, active in _states(rig).items():
        node = rig._member('channel_' + layer)
        if layer in ('soft', 'helper', 'foot'):
            _write(node + '.enabled', rig.layer_enabled(layer))
        _write(node + '.active', active)
        color = (0.35, 0.8, 0.45) if active else (0.4, 0.4, 0.4)
        if any(abs(a-b) > 1e-6 for a,b in zip(hlib.plug(node + '.outlinerColor').get(), color)):
            hlib.plug(node + '.outlinerColor').set((*color,))


@undo_transaction('hrig.channel_controls.attach')
def attach(rig):
    """構成表示階層を追加する。既存リグにも明示的に追加できる。

    Args:
        rig (LimbRig): 操作対象。

    Returns:
        str: チャンネルボックス操作用モジュール。
    """
    if _exists(rig):
        install()
        return rig._member('channelModule')
    from .limb import _lock_group
    root = rig.root.full_name()
    stem = rig.node_name('moduleSet').removesuffix('_set')
    group_name = 'modules_grp' if root.rsplit('|', 1)[-1] == 'rig' else root.rsplit('|', 1)[-1] + '_modules_grp'
    names = [group_name, stem] + [stem + '_' + LABELS[layer] + '_layer' for layer in LAYERS]
    if any(hlib.objExists(name) for name in names):
        raise ValueError('Module display names already exist')
    nodes = []
    group = hlib.createNode('transform', name=group_name, parent=root, skipSelect=True).full_name()
    cmds.reorder(group, front=True)
    module = hlib.createNode('transform', name=stem, parent=group, skipSelect=True).full_name()
    nodes.extend((group, module))
    rig._bind('channelModule', module)
    hlib.node(module).add_attr(long_name='hrigChannelRoot', attribute_type='message')
    hlib.plug(root + '.message').connect(module + '.hrigChannelRoot')
    _attribute(module, 'mode', 'enum', int(rig.mode() == 'ik'), 'FK:IK')
    _attribute(module, 'lod', 'enum', rig.lod(), 'Low:Full')
    _attribute(module, 'matchOnSwitch', default=True)
    for layer, name in zip(LAYERS, names[2:]):
        node = hlib.createNode('transform', name=name, parent=module, skipSelect=True).full_name()
        nodes.append(node)
        rig._bind('channel_' + layer, node)
        if layer in ('soft', 'helper', 'foot'):
            attr = 'hrigEnabled_' + layer
            if not hlib.node(root).has_attr(attr):
                hlib.node(root).add_attr(long_name=attr, attribute_type='bool', default_value=True)
            _attribute(node, 'enabled', default=rig.layer_enabled(layer))
        _attribute(node, 'active', readonly=True)
        hlib.plug(node + '.useOutlinerColor').set(True)
    for node in nodes:
        _lock_group(node)
        hlib.node(node).set_attr_flags(['visibility'], keyable=False, channel_box=False, locked=True)
    indices = cmds.getAttr(root + '.hrigOwned', multiIndices=True) or []
    for index, node in enumerate(nodes, max(indices, default=-1) + 1):
        hlib.plug(node + '.message').connect(root + '.hrigOwned[{}]'.format(index))
    sync_display(rig)
    install()
    return module


def apply(rig):
    """表示側の要求を適用する。GUI以外の検証でも明示的に呼べる。

    Args:
        rig (LimbRig): 構成表示を持つリグ。
    """
    module = rig._member('channelModule')
    mode = ('fk', 'ik')[hlib.plug(module + '.mode').get()]
    lod = hlib.plug(module + '.lod').get()
    enabled = {layer: bool(hlib.plug(rig._member('channel_' + layer) + '.enabled').get())
               for layer in ('soft', 'helper', 'foot')}
    if (mode == rig.mode() and lod == rig.lod()
            and all(value == rig.layer_enabled(layer) for layer, value in enabled.items())):
        return
    try:
        with undo_transaction('hrig.channel_controls.apply'):
            if mode != rig.mode() and hlib.plug(module + '.matchOnSwitch').get():
                # 通常のチャンネルボックス操作は一度に一属性だけ変更する。
                # モードと詳細設定を同時変更するスクリプトは公開メソッドを順に使う。
                if mode == 'fk':
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
    roots = cmds.ls(root_uuid, long=True) or []
    if not roots:
        return
    _busy = True
    try:
        from .limb import LimbRig
        apply(LimbRig(roots[0]))
    except Exception as error:
        cmds.warning('hrig: ' + str(error))
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
    for plug in cmds.ls('*.hrigChannelRoot', recursive=True) or []:
        module = plug.rsplit('.', 1)[0]
        source = hlib.plug(plug).source()
        if source is None:
            continue
        root = source.node
        key = root.uuid()
        if key in _jobs:
            continue
        rig = LimbRig(root)
        attrs = [module + '.mode', module + '.lod']
        attrs += [rig._member('channel_' + layer) + '.enabled' for layer in ('soft', 'helper', 'foot')]
        jobs = hlib.events.ScriptJobs()
        try:
            for attr in attrs:
                jobs.add(attr, attribute=attr, callback=partial(_changed, key),
                         kill_with_scene=True, compress_undo=True)
        except Exception:
            jobs.stop()
            raise
        _jobs[key] = jobs


def install():
    """GUIで監視を開始する。多重登録せず、シーンへ実行スクリプトを埋め込まない。"""
    if cmds.about(batch=True):
        return
    for event in ('PostSceneRead', 'NewSceneOpened', 'Undo', 'Redo'):
        _events.add(event, event=event, callback=refresh_jobs)
    refresh_jobs()
