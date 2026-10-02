"""HumanIKキャラクター定義。Maya標準MELを必要な操作時だけ利用する。"""

import json
from maya import cmds, mel
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from hlib.environment import Plugin
from .node import Node


def _prepare():
    """標準HumanIK実装をロードする。UIは作成しない。"""
    Plugin('mayaHIK').ensure_loaded()
    for script, procedure in (
            ('hikGlobalUtils.mel', 'hikCreateCharacter'),
            ('hikCharacterControlsUtils.mel', 'hikGetControlRig'),
            ('hikDefinitionUtils.mel', 'hikSetCharacterObject'),
            ('hikInputSourceUtils.mel', 'hikSetCharacterInput')):
        if not mel.eval('exists "{}";'.format(procedure)):
            mel.eval('source "{}";'.format(script))


def _quote(value):
    """日本語名を保ったままMELの文字列リテラルへ変換する。"""
    return json.dumps(value, ensure_ascii=False)


@node_wrapper('HIKCharacterNode')
class HIKCharacterNode(Node):
    """HumanIKノードの定義割当と既存キャラクター間の接続を扱う。"""

    @classmethod
    def create_character(cls, name='Character'):
        """標準MELでキャラクター一式を作る。現在キャラクターも変更される。"""
        if not isinstance(name, str) or not name:
            raise ValueError('Expected a character name')
        _prepare()
        return cls(mel.eval('hikCreateCharacter({});'.format(_quote(name))))

    def is_definition_locked(self):
        """bool: キャラクタライズがロック済みか照会する。"""
        return bool(cmds.getAttr(self.full_name() + '.InputCharacterizationLock'))

    @undo_chunk('hlib.HIKCharacterNode.set_joint')
    def set_joint(self, role, joint):
        """ロック前の定義へ骨を割り当てる。

        Args:
            role (str): HumanIK標準の骨名。例: Hips、LeftArm。
            joint: hlibで解決可能なjoint。
        Note:
            定義の検証・ロックはMayaのHumanIK UIで行う。
        """
        from hlib.nodes.node import Node as _InputNode
        _prepare()
        if self.is_definition_locked():
            raise RuntimeError('Unlock the character definition before editing')
        name = _InputNode._input_name(joint)
        if cmds.nodeType(name) != 'joint':
            raise TypeError('Expected a joint')
        if not isinstance(role, str):
            raise TypeError('role must be a HumanIK bone name')
        index = cmds.hikGetNodeIdFromName(role)
        if index < 0 or cmds.GetHIKNodeName(index) != role:
            raise ValueError('Unknown HumanIK role: ' + role)
        mel.eval('hikSetCharacterObject({}, {}, {}, 0);'.format(
            _quote(name), _quote(self.full_name()), index))
        if not self.joint(role) or self.joint(role).full_name() != name:
            raise RuntimeError('HumanIK did not assign the joint')

    def joint(self, role):
        """Node | None: 指定役割に割り当てられた骨を取得する。"""
        _prepare()
        index = cmds.hikGetNodeIdFromName(role)
        if index < 0 or cmds.GetHIKNodeName(index) != role:
            raise ValueError('Unknown HumanIK role: ' + role)
        values = cmds.listConnections(self.full_name() + '.' + role,
                                      source=True, destination=False) or []
        return Node(values[0]) if values else None

    @undo_chunk('hlib.HIKCharacterNode.set_source')
    def set_source(self, source):
        """検証・ロック済みの別キャラクターをリターゲット入力にする。"""
        _prepare()
        source = Node(source)
        if not isinstance(source, HIKCharacterNode) or source == self:
            raise ValueError('Expected a different HIKCharacterNode')
        if not self.is_definition_locked() or not source.is_definition_locked():
            raise RuntimeError('Both character definitions must be validated and locked')
        mel.eval('hikSetCharacterInput({}, {});'.format(
            _quote(self.full_name()), _quote(source.full_name())))
        actual = self.source()
        if actual is None or actual.full_name() != source.full_name():
            raise RuntimeError('HumanIK did not connect the requested source')

    def source(self):
        """HIKCharacterNode | None: 現在のリターゲット入力を取得する。"""
        _prepare()
        value = mel.eval('hikGetRetargetCharacterInput({});'.format(_quote(self.full_name())))
        return HIKCharacterNode(value) if value else None
