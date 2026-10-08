"""HumanIKキャラクター定義。Maya標準MELを必要な操作時だけ利用する。"""

import json

import maya.cmds as cmds
import maya.mel as mel

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common.plugin import Plugin
from ..decorator import undoChunk
from .node import Node


def _prepare():
    """標準HumanIK実装をロードする。UIは作成しない。"""
    Plugin('mayaHIK').ensureLoaded()
    for script, procedure in (
            ('hikGlobalUtils.mel', 'hikCreateCharacter'),
            ('hikCharacterControlsUtils.mel', 'hikGetControlRig'),
            ('hikDefinitionUtils.mel', 'hikSetCharacterObject'),
            ('hikInputSourceUtils.mel', 'hikSetCharacterInput')):
        if not mel.eval('exists "{}";'.format(procedure)):
            mel.eval('source "{}";'.format(script))


def _quote(value):
    """日本語名を保ったままMELの文字列リテラルへ変換する。

    Args:
        value: 変換・設定する入力値。
    """
    return json.dumps(value, ensure_ascii=False)


class HIKCharacterNode(Node):
    """HumanIKノードの定義割当と既存キャラクター間の接続を扱う。"""

    @classmethod
    def createCharacter(cls, name='Character'):
        """標準MELでキャラクター一式を作る。現在キャラクターも変更される。

        Args:
            name (str): 作成する空でないキャラクタ名。

        Returns:
            HIKCharacterNode: 作成したキャラクタ。MEL の作成処理は現在のキャラクタも変更する。
        """
        if not isinstance(name, str) or not name:
            raise ValueError('Expected a character name')
        _prepare()
        return cls(mel.eval('hikCreateCharacter({});'.format(_quote(name))))

    def isDefinitionLocked(self):
        """キャラクタライズがロック済みか照会する。

        Returns:
            bool: キャラクタライズがロック済みか照会する。
        """
        return bool(cmds.getAttr(self.getFullName() + '.InputCharacterizationLock'))

    def joint(self, role):
        """Node | None: 指定役割に割り当てられた骨を取得する。

        Args:
            role (str): HIK のジョイントロール名。

        Returns:
            Node | None: ロールに接続された最初のノード。未割り当てなら None。
        """
        _prepare()
        index = cmds.hikGetNodeIdFromName(role)
        if index < 0 or cmds.GetHIKNodeName(index) != role:
            raise ValueError('Unknown HumanIK role: ' + role)
        values = cmds.listConnections(self.getFullName() + '.' + role,
                                      source=True, destination=False) or []
        return Node(values[0]) if values else None

    @undoChunk('hlib.HIKCharacterNode.setJoint')
    def setJoint(self, role, joint):
        """ロック前の定義へ骨を割り当てる。

        Args:
            role (str): HumanIK標準の骨名。例: Hips、LeftArm。
            joint: hlibで解決可能なjoint。
        Note:
            定義の検証・ロックはMayaのHumanIK UIで行う。
        """
        from .node import Node as _InputNode
        _prepare()
        if self.isDefinitionLocked():
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
            _quote(name), _quote(self.getFullName()), index))
        if not self.joint(role) or self.joint(role).getFullName() != name:
            raise RuntimeError('HumanIK did not assign the joint')

    def getSource(self):
        """現在のリターゲット入力を取得する。

        Returns:
            HIKCharacterNode | None: 現在のリターゲット入力を取得する。
        """
        _prepare()
        value = mel.eval('hikGetRetargetCharacterInput({});'.format(_quote(self.getFullName())))
        return HIKCharacterNode(value) if value else None

    @flag_aliases(src="source")
    @undoChunk('hlib.HIKCharacterNode.setSource')
    def setSource(self, source):
        """検証・ロック済みの別キャラクターをリターゲット入力にする。

        Args:
            source (HIKCharacterNode | str): 自分以外のソースキャラクタ。
                両キャラクタの定義がロック済みであること。 別名 ``src`` も使用可能。
        """
        _prepare()
        source = Node(source)
        if not isinstance(source, HIKCharacterNode) or source == self:
            raise ValueError('Expected a different HIKCharacterNode')
        if not self.isDefinitionLocked() or not source.isDefinitionLocked():
            raise RuntimeError('Both character definitions must be validated and locked')
        mel.eval('hikSetCharacterInput({}, {});'.format(
            _quote(self.getFullName()), _quote(source.getFullName())))
        actual = self.getSourceWithConversion()
        if actual is None or actual.getFullName() != source.getFullName():
            raise RuntimeError('HumanIK did not connect the requested source')

    @_getter_alias(getSource)
    def source(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSource(*args, **kwargs)
