"""標準アウトライナーとチャンネルボックスによる構成操作。

GUIのscriptJobを使用し、操作と接続変更を同じUndoへまとめる。
設定はアニメーション用ではない。バッチではLimbRigのメソッドを使用する。
"""

from functools import partial
from maya import cmds
from hlib.decorators.undo import undo_transaction

_jobs = {}
_events = []
_busy = False
LAYERS = ('fk', 'ik', 'soft', 'helper', 'foot')
LABELS = {'fk': 'fk', 'ik': 'ik', 'soft': 'soft_ik',
          'helper': 'helper', 'foot': 'reverse_foot'}


def _write(plug, value):
    """変化した値だけを書き、不要なUndoと属性通知を作らない。"""
    if cmds.getAttr(plug) != value:
        locked = cmds.getAttr(plug, lock=True)
        if locked:
            cmds.setAttr(plug, lock=False)
        cmds.setAttr(plug, value)
        if locked:
            cmds.setAttr(plug, lock=True)


def _attribute(node, name, kind='bool', default=0, enum=None, readonly=False):
    """キー対象外の設定・状態属性をチャンネルボックスへ表示する。"""
    args = {'longName': name, 'attributeType': kind, 'defaultValue': default}
    if enum:
        args['enumName'] = enum
    cmds.addAttr(node, **args)
    cmds.setAttr(node + '.' + name, keyable=False, channelBox=True, lock=readonly)


def _exists(rig):
    """bool: 構成表示が接続済みかを照会する。"""
    root = rig.root.full_name()
    return cmds.attributeQuery('channelModule', node=root, exists=True) and bool(
        cmds.listConnections(root + '.channelModule', source=True, destination=False))


def _states(rig):
    """dict: 実際に接続へ適用したレイヤー状態を計算する。"""
    ik = rig.mode() == 'ik'
    detail = rig.lod() == 1
    return {'fk': not ik, 'ik': ik,
            'soft': ik and detail and rig.layer_enabled('soft'),
            'helper': detail and rig.layer_enabled('helper'),
            'foot': ik and detail and rig.layer_enabled('foot') and cmds.attributeQuery(
                'footMatrix', node=rig.root.full_name(), exists=True)}


def sync_display(rig):
    """適用済み状態を表示へ同期する。Pythonの既存操作からも呼ばれる。"""
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
        if any(abs(a-b) > 1e-6 for a,b in zip(cmds.getAttr(node + '.outlinerColor')[0], color)):
            cmds.setAttr(node + '.outlinerColor', *color)


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
    if any(cmds.objExists(name) for name in names):
        raise ValueError('Module display names already exist')
    nodes = []
    group = cmds.createNode('transform', name=group_name, parent=root, skipSelect=True)
    cmds.reorder(group, front=True)
    module = cmds.createNode('transform', name=stem, parent=group, skipSelect=True)
    nodes.extend((group, module))
    rig._bind('channelModule', module)
    cmds.addAttr(module, longName='hrigChannelRoot', attributeType='message')
    cmds.connectAttr(root + '.message', module + '.hrigChannelRoot')
    _attribute(module, 'mode', 'enum', int(rig.mode() == 'ik'), 'FK:IK')
    _attribute(module, 'lod', 'enum', rig.lod(), 'Low:Full')
    _attribute(module, 'matchOnSwitch', default=True)
    for layer, name in zip(LAYERS, names[2:]):
        node = cmds.createNode('transform', name=name, parent=module, skipSelect=True)
        nodes.append(node)
        rig._bind('channel_' + layer, node)
        if layer in ('soft', 'helper', 'foot'):
            attr = 'hrigEnabled_' + layer
            if not cmds.attributeQuery(attr, node=root, exists=True):
                cmds.addAttr(root, longName=attr, attributeType='bool', defaultValue=True)
            _attribute(node, 'enabled', default=rig.layer_enabled(layer))
        _attribute(node, 'active', readonly=True)
        cmds.setAttr(node + '.useOutlinerColor', True)
    for node in nodes:
        _lock_group(node)
        cmds.setAttr(node + '.visibility', keyable=False, channelBox=False, lock=True)
    indices = cmds.getAttr(root + '.hrigOwned', multiIndices=True) or []
    for index, node in enumerate(nodes, max(indices, default=-1) + 1):
        cmds.connectAttr(node + '.message', root + '.hrigOwned[{}]'.format(index))
    sync_display(rig)
    install()
    return module


def apply(rig):
    """表示側の要求を適用する。GUI以外の検証でも明示的に呼べる。

    Args:
        rig (LimbRig): 構成表示を持つリグ。
    """
    module = rig._member('channelModule')
    mode = ('fk', 'ik')[cmds.getAttr(module + '.mode')]
    lod = cmds.getAttr(module + '.lod')
    enabled = {layer: bool(cmds.getAttr(rig._member('channel_' + layer) + '.enabled'))
               for layer in ('soft', 'helper', 'foot')}
    if (mode == rig.mode() and lod == rig.lod()
            and all(value == rig.layer_enabled(layer) for layer, value in enabled.items())):
        return
    try:
        with undo_transaction('hrig.channel_controls.apply'):
            if mode != rig.mode() and cmds.getAttr(module + '.matchOnSwitch'):
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
    """属性変更をまとめて適用する。削除・改名と再入を考慮する。"""
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
        if not cmds.ls(key) or not all(cmds.scriptJob(exists=job) for job in jobs):
            for job in jobs:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job)
            del _jobs[key]
    for plug in cmds.ls('*.hrigChannelRoot', recursive=True) or []:
        module = plug.rsplit('.', 1)[0]
        roots = cmds.listConnections(plug, source=True, destination=False) or []
        if len(roots) != 1:
            continue
        key = cmds.ls(roots[0], uuid=True)[0]
        if key in _jobs:
            continue
        rig = LimbRig(roots[0])
        attrs = [module + '.mode', module + '.lod']
        attrs += [rig._member('channel_' + layer) + '.enabled' for layer in ('soft', 'helper', 'foot')]
        _jobs[key] = [cmds.scriptJob(attributeChange=[attr, partial(_changed, key)],
                                    killWithScene=True, compressUndo=True) for attr in attrs]


def install():
    """GUIで監視を開始する。多重登録せず、シーンへ実行スクリプトを埋め込まない。"""
    if cmds.about(batch=True):
        return
    if not _events:
        for event in ('PostSceneRead', 'NewSceneOpened', 'Undo', 'Redo'):
            _events.append(cmds.scriptJob(event=[event, refresh_jobs]))
    refresh_jobs()
