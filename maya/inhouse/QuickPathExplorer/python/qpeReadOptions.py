"""Maya読込操作に渡す設定を操作ごとに保持する。"""
import re
from pathlib import Path
from qpeQt import QtWidgets


class ReadOptions(QtWidgets.QTabWidget):
    """インポートとリファレンスの設定を独立して編集する。"""

    def __init__(self, parent=None):
        """標準fileコマンドに対応する設定欄を作成する。"""
        super().__init__(parent)
        self.controls = {}
        for action, title in [('import', 'Import settings'), ('reference', 'Reference settings')]:
            page = QtWidgets.QWidget(self)
            form = QtWidgets.QFormLayout(page)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            mode = QtWidgets.QComboBox(page)
            mode.addItems(['File name', 'Custom namespace', 'Root (:)'])
            name = QtWidgets.QLineEdit(page)
            name.setPlaceholderText('characterA or shot:characterA')
            name.setEnabled(False)
            mode.currentIndexChanged.connect(lambda index, field=name: field.setEnabled(index == 1))
            form.addRow('Namespace', mode)
            form.addRow('Name', name)
            values = {'mode': mode, 'name': name}
            for key, label, default in [
                ('mergeNamespacesOnClash', 'Reuse existing namespace', False),
                ('groupReference', 'Group objects', False),
                ('executeScriptNodes', 'Execute script nodes', True),
            ] + ([('preserveReferences', 'Preserve references', True),
                  ('removeDuplicateNetworks', 'Remove duplicate shading networks', False),
                  ('mergeBaseAnimLayer', 'Merge base animation layer', False),
                  ('renameAll', 'Rename all nodes', False),
                  ('importFrameRate', 'Import frame rate', False),
                  ('ignoreVersion', 'Ignore version', False)] if action == 'import' else
                 [('deferReference', 'Defer loading', False),
                  ('lockReference', 'Lock reference', False)]):
                box = QtWidgets.QCheckBox(label, page)
                box.setChecked(default)
                form.addRow(box)
                values[key] = box
            depth = QtWidgets.QComboBox(page)
            for label, value in [('As saved', ''), ('All', 'all'), ('Top level only', 'topOnly'), ('None', 'none')]:
                depth.addItem(label, value)
            form.addRow('Load references', depth)
            values['loadReferenceDepth'] = depth
            if action == 'reference':
                values['deferReference'].toggled.connect(lambda checked, field=depth: field.setEnabled(not checked))
            else:
                time_range = QtWidgets.QComboBox(page)
                for label, value in [('Keep current', 'keep'), ('Override', 'override'), ('Combine', 'combine')]:
                    time_range.addItem(label, value)
                form.addRow('Playback range', time_range)
                values['importTimeRange'] = time_range
            self.controls[action] = values
            scroll = QtWidgets.QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setWidget(page)
            self.addTab(scroll, title)
        self.setMinimumHeight(225)
        self.setMaximumHeight(310)
        self.setToolTip('Settings apply to the matching Import / Reference button and context menu.')

    def fileArguments(self, action, path):
        """対象ファイル用のfile引数を検証して返す。

        Args:
            action (str): importまたはreference。
            path (str): 読み込むファイル。

        Returns:
            dict: Mayaのfileコマンド用引数。

        Raises:
            ValueError: 明示したネームスペースの書式が不正な場合。
        """
        values = self.controls[action]
        mode = values['mode'].currentIndex()
        if mode == 0:
            name = re.sub(r'[^\w]', '_', Path(path).stem) or 'file'
            if name and name[0].isdigit():
                name = '_' + name
        elif mode == 1:
            name = values['name'].text().strip()
            if not re.fullmatch(r':?[^\W\d]\w*(?::[^\W\d]\w*)*', name, re.UNICODE):
                raise ValueError('Enter a valid namespace, for example characterA or shot:characterA.')
        else:
            name = ':'
        result = {key: control.isChecked() for key, control in values.items() if isinstance(control, QtWidgets.QCheckBox)}
        depth = values['loadReferenceDepth'].currentData()
        if depth and not result.get('deferReference'):
            result['loadReferenceDepth'] = depth
        if action == 'import':
            result['importTimeRange'] = values['importTimeRange'].currentData()
        result['namespace'] = ':' + name.lstrip(':')
        if mode == 2:
            result['mergeNamespacesOnClash'] = True
        return result
