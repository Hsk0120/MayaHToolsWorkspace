"""Maya読込操作に渡す設定を操作ごとに保持する。"""
import re
from pathlib import Path
from qpeQt import QtCore, QtWidgets


class ReadOptions(QtWidgets.QTabWidget):
    """インポートとリファレンスの設定を独立して編集する。"""

    def __init__(self, parent=None):
        """標準fileコマンドに対応する設定欄を作成する。"""
        super().__init__(parent)
        self.controls = {}
        self.advancedToggles = {}
        for action, title in [('import', 'Import settings'), ('reference', 'Reference settings')]:
            page = QtWidgets.QWidget(self)
            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(8, 10, 8, 10)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            mode = QtWidgets.QComboBox(page)
            mode.addItems(['Use file name', 'Specify namespace', 'Root namespace (:)'])
            name = QtWidgets.QLineEdit(page)
            name.setPlaceholderText('characterA or shot:characterA')
            name.setEnabled(False)
            mode.currentIndexChanged.connect(lambda index, field=name: field.setEnabled(index == 1))
            form.addRow('Namespace', mode)
            name_label = QtWidgets.QLabel('Namespace name', page)
            form.addRow(name_label, name)
            mode.currentIndexChanged.connect(lambda index, field=name, label=name_label:
                                            (field.setVisible(index == 1), label.setVisible(index == 1)))
            name.hide()
            name_label.hide()
            values = {'mode': mode, 'name': name}
            advanced_toggle = QtWidgets.QToolButton(page)
            advanced_toggle.setText('Advanced options')
            advanced_toggle.setCheckable(True)
            advanced_toggle.setArrowType(QtCore.Qt.RightArrow)
            advanced_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            advanced = QtWidgets.QWidget(page)
            advanced_form = QtWidgets.QFormLayout(advanced)
            advanced_form.setContentsMargins(0, 0, 0, 0)
            advanced_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            advanced.hide()
            advanced_toggle.toggled.connect(lambda checked, panel=advanced, button=advanced_toggle:
                                            (panel.setVisible(checked), button.setArrowType(
                                                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)))
            self.advancedToggles[action] = advanced_toggle
            for key, label, default in [
                ('mergeNamespacesOnClash', 'Reuse existing namespace', False),
                ('groupReference', 'Group objects', False),
                ('executeScriptNodes', 'Execute script nodes', True),
            ] + ([('preserveReferences', 'Preserve references', True),
                  ('removeDuplicateNetworks', 'Remove duplicate networks', False),
                  ('mergeBaseAnimLayer', 'Merge base animation layer', False),
                  ('renameAll', 'Rename all nodes', False),
                  ('importFrameRate', 'Import frame rate', False),
                  ('ignoreVersion', 'Ignore version', False)] if action == 'import' else
                 [('deferReference', 'Defer loading', False),
                  ('lockReference', 'Lock reference', False)]):
                box = QtWidgets.QCheckBox(label, page)
                box.setChecked(default)
                if key == 'removeDuplicateNetworks':
                    box.setToolTip('Remove duplicate shading networks')
                if key == 'mergeNamespacesOnClash':
                    box.setToolTip('Reuse a matching namespace. This does not merge existing nodes.')
                (form if key in ('mergeNamespacesOnClash', 'deferReference') else advanced_form).addRow(box)
                values[key] = box
            depth = QtWidgets.QComboBox(page)
            for label, value in [('As saved', ''), ('All', 'all'), ('Top level only', 'topOnly'), ('None', 'none')]:
                depth.addItem(label, value)
            advanced_form.addRow('Load references', depth)
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
            layout.addWidget(advanced_toggle)
            layout.addWidget(advanced)
            self.addTab(page, title)
        self.setToolTip('Settings apply to the matching Import / Reference button and context menu.')
        from qpeSettings import readSettings
        self.restore(readSettings().get('readOptions', {}))

    def snapshot(self):
        """両操作の設定をJSONへ保存できる値にする。"""
        return {action: {key: (control.isChecked() if isinstance(control, QtWidgets.QCheckBox)
                         else control.currentIndex() if isinstance(control, QtWidgets.QComboBox)
                         else control.text()) for key, control in values.items()}
                for action, values in self.controls.items()}

    def restore(self, state):
        """既知の設定だけを型を確認して復元する。"""
        if not isinstance(state, dict):
            return
        for action, values in self.controls.items():
            for key, control in values.items():
                value = state.get(action, {}).get(key)
                if isinstance(control, QtWidgets.QCheckBox) and isinstance(value, bool):
                    control.setChecked(value)
                elif isinstance(control, QtWidgets.QComboBox) and isinstance(value, int) and 0 <= value < control.count():
                    control.setCurrentIndex(value)
                elif isinstance(control, QtWidgets.QLineEdit) and isinstance(value, str):
                    control.setText(value)

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
