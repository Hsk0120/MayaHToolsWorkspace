"""QPEのFBX読込設定と、Maya標準FBXトランスレーターへの接続。"""
import json
from pathlib import Path
import sys

from qpeQt import QtCore, QtWidgets
from qpeSettings import readSettings, writeSettings


MODES = (
    ('Open as scene', 'open'),
    ('Add', 'add'),
    ('Add and update animation', 'merge'),
    ('Update animation only', 'exmerge'),
    ('Update animation (keyed transforms)', 'exmergekeyedxforms'),
)


class FbxOptions(QtWidgets.QGroupBox):
    """FBXのOpen/ダブルクリックに使う設定を即時保存する。"""

    changed = QtCore.Signal()

    def __init__(self, parent=None):
        """標準のFile Contentに対応する選択肢を作る。"""
        super().__init__('FBX', parent)
        self.setObjectName('fbxOpenSettings')
        layout = QtWidgets.QVBoxLayout(self)
        self.mode = QtWidgets.QComboBox(self)
        self.mode.setObjectName('fbxOpenMode')
        for label, value in MODES:
            self.mode.addItem(label, value)
        layout.addWidget(QtWidgets.QLabel('File Content', self))
        layout.addWidget(self.mode)
        self.timeline = QtWidgets.QCheckBox('Update playback range', self)
        self.timeline.setToolTip('Update the current playback range from the FBX animation range.')
        layout.addWidget(self.timeline)
        self.description = QtWidgets.QLabel(self)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        state = readSettings().get('fbxOpenOptions', {})
        if isinstance(state, dict):
            index = self.mode.findData(state.get('mode', 'open'))
            self.mode.setCurrentIndex(max(0, index))
            self.timeline.setChecked(state.get('timeline') is True)
        self.mode.currentIndexChanged.connect(self._changed)
        self.timeline.toggled.connect(self._changed)
        self._describe()

    def _describe(self):
        """シーン切替と既存シーン更新を操作前に区別できる説明を出す。"""
        mode = self.mode.currentData()
        descriptions = {
            'open': 'Replace the current scene.',
            'add': 'Add objects to the current scene.',
            'merge': 'Add missing objects; update matching objects.',
            'exmerge': 'Update matching objects only. No new objects.',
            'exmergekeyedxforms': 'Update matching objects; preserve unkeyed transforms.',
        }
        self.description.setText(descriptions[mode])
        self.setToolTip('Applies to Open and double-click. Import / Reference use their own settings.')

    def _changed(self, *unused):
        """選択を保存し、サイドバーを閉じても現在モードを上部へ通知する。"""
        self._describe()
        writeSettings({'fbxOpenOptions': self.snapshot()})
        self.changed.emit()

    def snapshot(self):
        """今回の操作に固定する設定値を返す。"""
        return {'mode': self.mode.currentData(), 'timeline': self.timeline.isChecked()}


def openFbx(path, options):
    """設定を一時適用して現在のMayaでFBXを読み込む。

    Args:
        path (str): 読込元FBX。
        options (dict): modeとtimeline。openの未保存確認は呼出元が行う。

    Returns:
        bool: シーンを切り替えた場合True、現在シーンへの読込はFalse。

    Raises:
        ValueError: 設定または読込元が不正な場合。
        RuntimeError: 標準FBXプラグインの読込・設定・実行に失敗した場合。
    """
    mode = options.get('mode')
    if mode not in dict((value, label) for label, value in MODES):
        raise ValueError('Unknown FBX open mode.')
    source = Path(path)
    if source.suffix.lower() != '.fbx' or not source.is_file():
        raise ValueError('Select an existing FBX file.')
    # Windows単体版からはMayaをimportしない。読込の明示操作時だけ使う。
    from maya import cmds, mel
    if not cmds.pluginInfo('fbxmaya', query=True, loaded=True):
        cmds.loadPlugin('fbxmaya', quiet=True)
    playback = {key: cmds.playbackOptions(query=True, **{key: True})
                for key in ('minTime', 'maxTime', 'animationStartTime', 'animationEndTime')}
    mel.eval('FBXPushSettings;')
    try:
        mel.eval('FBXImportMode -v "{}";'.format('add' if mode == 'open' else mode))
        mel.eval('FBXImportFillTimeline -v {};'.format('true' if options.get('timeline') else 'false'))
        # Animationが標準設定でOFFでも更新モードはアニメーションを取り込む。
        mel.eval('FBXProperty "Import|IncludeGrp|Animation" -v true;')
        if mode == 'open':
            cmds.file(str(source), open=True, force=True, type='FBX', options='v=0;')
        else:
            mel.eval('FBXImport -f {};'.format(json.dumps(source.as_posix(), ensure_ascii=False)))
    finally:
        # 標準ダイアログや他ツールのFBX設定を、失敗時にも元へ戻す。
        failed = sys.exc_info()[0] is not None
        try:
            mel.eval('FBXPopSettings;')
        except RuntimeError as error:
            if not failed:
                raise
            cmds.warning('QuickPathExplorer: Could not restore FBX settings: ' + str(error))
        finally:
            # 更新モードではFBX側がFillTimelineを強制ONにする版がある。
            # 明示的なOFFはMayaの再生範囲を復元して保証する。
            if not options.get('timeline'):
                cmds.playbackOptions(**playback)
    return mode == 'open'
