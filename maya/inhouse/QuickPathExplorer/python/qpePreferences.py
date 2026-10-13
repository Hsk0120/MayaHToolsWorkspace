"""設定の移植形式と、利用者が編集できる設定画面。"""
import json
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets
from qpeSettings import readSettings, writeSettings

PORTABLE = ('preferences', 'commandKeys', 'readPresets', 'mayaAppearance', 'standaloneAppearance', 'standaloneTheme')
LOCAL = ('favorites', 'savedSearches', 'fileLabels', 'folderViews', 'previewExecutable', 'everythingExecutable', 'tabSets', 'fileLocksmith', 'pathHistory')


def validateKeys(keys):
    """設定取込と画面編集で同じ予約キー・重複規則を適用する。"""
    if any(not isinstance(value, str) for value in keys.values()):
        raise ValueError('Invalid key bindings')
    assigned = [QtGui.QKeySequence(value).toString() for value in keys.values() if value]
    reserved = {'Ctrl+C', 'Ctrl+X', 'Ctrl+V', 'Ctrl+Z', 'Ctrl+Y', 'Ctrl+F', 'Ctrl+T', 'Ctrl+W', 'Ctrl+Tab', 'Ctrl+Shift+T'}
    if len(assigned) != len(set(assigned)) or any(key in reserved or not key.startswith(('Ctrl+', 'Alt+')) for key in assigned):
        raise ValueError('Use unique Ctrl/Alt bindings. Standard file-operation keys are reserved.')


def exportPreferences(path, includeLocal=False):
    """ユーザー設定だけを書出し、Undoや実行中処理を混ぜない。"""
    current = readSettings()
    value = dict(format='qpe.preferences', version=1,
                 settings={key: current[key] for key in PORTABLE + (LOCAL if includeLocal else ()) if key in current and key != 'previewExecutable'})
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def importPreferences(path):
    """未知の形式・キーを拒否し、許可した設定だけを取り込む。"""
    if Path(path).stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Settings exceed 8 MiB')
    value = json.loads(Path(path).read_text(encoding='utf8'))
    if not isinstance(value, dict) or value.get('format') != 'qpe.preferences' or value.get('version') != 1 or not isinstance(value.get('settings'), dict):
        raise ValueError('Unsupported settings format / version')
    settings = value['settings']
    if set(settings) - set(PORTABLE + LOCAL):
        raise ValueError('Unknown settings keys')
    for key, item in settings.items():
        expected = list if key in ('favorites', 'pathHistory') else str if key.endswith('Executable') or key in ('standaloneTheme', 'fileLocksmith') else dict
        if not isinstance(item, expected):
            raise ValueError('Invalid setting: ' + key)
        if expected is list and any(not isinstance(path, str) for path in item):
            raise ValueError('Invalid path in ' + key)
    for name, conditions in settings.get('savedSearches', {}).items():
        if not isinstance(conditions, dict):
            raise ValueError('Invalid saved search: ' + name)
        for key in ('root', 'query', 'extensions', 'content', 'exclude', 'tags', 'tagMode', 'kind'):
            if key in conditions and not isinstance(conditions[key], str):
                raise ValueError('Invalid saved search field: ' + key)
        for key in ('days', 'minimum', 'maximum'):
            if key in conditions and (type(conditions[key]) is not int or conditions[key] < 0):
                raise ValueError('Invalid saved search number: ' + key)
    preferences = settings.get('preferences', {})
    for key, low, high in (('undoDays', 1, 3650), ('undoMiB', 1, 1048576)):
        if key in preferences and (type(preferences[key]) is not int or not low <= preferences[key] <= high):
            raise ValueError('Invalid retention value: ' + key)
    keys = settings.get('commandKeys', {})
    validateKeys(keys)
    for value in settings.get('folderViews', {}).values():
        if not isinstance(value, dict) or value.get('mode', 0) not in (0, 1, 2) or value.get('group', 0) not in range(5):
            raise ValueError('Invalid folder display settings')
        if value.get('sort', 0) not in range(9) or not isinstance(value.get('hidden', []), list) or not isinstance(value.get('widths', []), list):
            raise ValueError('Invalid column settings')
        if any(type(c) is not int or not 1 <= c <= 8 for c in value.get('hidden', [])) or any(type(w) is not int or not 0 <= w <= 10000 for w in value.get('widths', [])):
            raise ValueError('Invalid column dimensions')
    for value in settings.get('fileLabels', {}).values():
        if not isinstance(value, dict) or not isinstance(value.get('tags', []), list) or any(not isinstance(t, str) for t in value.get('tags', [])):
            raise ValueError('Invalid tags')
        if type(value.get('rating', 0)) is not int or not 0 <= value.get('rating', 0) <= 5:
            raise ValueError('Invalid rating')
    # 旧書出しのビューアー指定は受理するが、現在はOSの関連付けを使用する。
    settings.pop('previewExecutable', None)
    if not writeSettings(settings):
        raise OSError('Settings could not be saved')


class PreferencesDialog(QtWidgets.QDialog):
    """変更可能な項目と移植範囲を明示する。"""

    def __init__(self, workspace):
        """環境固有パスの書出しは明示的に選択させる。"""
        super().__init__(workspace.e)
        self.workspace = workspace
        self.setWindowTitle('QuickPathExplorer settings')
        self.resize(670, 580)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        values = readSettings()
        preferences = values.get('preferences', {})
        self.days, self.budget = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        self.days.setRange(1, 3650)
        self.budget.setRange(1, 1048576)
        self.days.setValue(preferences.get('undoDays', 30))
        self.budget.setValue(preferences.get('undoMiB', 1024))
        form.addRow('Undo retention (days, manual cleanup)', self.days)
        form.addRow('Undo backup size limit (MiB, manual cleanup)', self.budget)
        self.everything = QtWidgets.QLineEdit(values.get('everythingExecutable', ''))
        open_rule = 'Open uses Windows file associations.'
        if workspace.e._maya:
            open_rule += ' Maya scenes open in the current Maya.'
        open_info = QtWidgets.QLabel(open_rule)
        open_info.setWordWrap(True)
        form.addRow(open_info)
        form.addRow('Everything CLI executable', self.everything)
        self.hidden = QtWidgets.QCheckBox('Show hidden files')
        self.hidden.setChecked(workspace.tools.hidden)
        form.addRow(self.hidden)
        appearance = QtWidgets.QPushButton('Font / UI size / theme…')
        appearance.clicked.connect(workspace.e.appearance.show)
        form.addRow('Display', appearance)
        layout.addWidget(QtWidgets.QLabel('Custom keys apply only within QPE. Editing fields are protected.\nUse Ctrl/Alt with a key; Maya assignments outside QPE are unchanged.'))
        self.keys = QtWidgets.QTreeWidget()
        self.keys.setHeaderLabels(['Command', 'Keyboard shortcut'])
        self.editors = {}
        defaults = {'palette': 'Ctrl+Shift+P', 'jobs': 'Ctrl+Shift+J', 'history': 'Ctrl+Shift+H'}
        defaults.update(values.get('commandKeys', {}))
        for name, (title, unused) in workspace.commands().items():
            row = QtWidgets.QTreeWidgetItem([title])
            self.keys.addTopLevelItem(row)
            edit = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence(defaults.get(name, '')))
            self.keys.setItemWidget(row, 1, edit)
            self.editors[name] = edit
        self.keys.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.keys.header().setStretchLastSection(True)
        layout.addWidget(self.keys, 1)
        self.local = QtWidgets.QCheckBox('Include computer-specific paths / favorites / tags when exporting')
        layout.addWidget(self.local)
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        for title, callback in [('Apply', self.apply), ('Export…', self.export), ('Import…', self.load)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)

    def apply(self):
        """競合するキーを保存前に拒否する。"""
        keys = {name: editor.keySequence().toString() for name, editor in self.editors.items()}
        try:
            validateKeys(keys)
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, 'Keyboard shortcut conflict', str(error))
            return False
        if not writeSettings(dict(commandKeys=keys, preferences=dict(undoDays=self.days.value(), undoMiB=self.budget.value()),
                                  everythingExecutable=self.everything.text())):
            return False
        self.workspace.tools.setHidden(self.hidden.isChecked())
        self.workspace.installShortcuts()
        return True

    def export(self):
        """設定だけをJSONで書出す。"""
        if not self.apply():
            return
        path, unused = QtWidgets.QFileDialog.getSaveFileName(self, 'Export settings', 'qpe-settings.json', 'JSON (*.json)')
        if path:
            try:
                exportPreferences(path, self.local.isChecked())
            except (OSError, ValueError) as error:
                QtWidgets.QMessageBox.warning(self, 'Export failed', str(error))

    def load(self):
        """取込対象を確認し、再表示に反映する。"""
        path, unused = QtWidgets.QFileDialog.getOpenFileName(self, 'Import settings', '', 'JSON (*.json)')
        if not path:
            return
        if QtWidgets.QMessageBox.question(self, 'Import settings', 'Replace matching QPE settings from this file?\nOther settings and file-operation history are retained.',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
            return
        try:
            importPreferences(path)
            appearance = self.workspace.e.appearance
            values = readSettings()
            display = values.get(appearance.key, {})
            appearance.density = display.get('density', 'compact') if display.get('density', 'compact') in ('compact', 'comfortable') else 'compact'
            if not self.workspace.e._maya:
                appearance.theme.setMode(values.get('standaloneTheme', appearance.theme.mode))
            appearance.apply(display.get('fontSize', appearance.fontSize), display.get('uiPercent', appearance.uiPercent), save=False)
            self.workspace.installShortcuts()
            self.workspace.e._loadPlaces()
            self.workspace.path = ''
            self.workspace.navigate()
            self.accept()
        except (OSError, ValueError, TypeError) as error:
            QtWidgets.QMessageBox.warning(self, 'Import failed', str(error))
