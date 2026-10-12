"""配色変更時の表示状態維持とホストへの非干渉を検証する。"""
import json
import os
import sys
import traceback
from pathlib import Path
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtWidgets, QtGui


def main(output_dir, finished=None):
    """専用データで明暗切替・Maya固定色を検証する。

    Args:
        output_dir (str): 証拠の保存先。
        finished (callable): 専用Maya実行器への終了通知。

    Returns:
        dict: 検証結果。
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'ThemeReview'
    root.mkdir(exist_ok=True)
    for index in range(60):
        (root / ('notes%02d.txt' % index)).write_text('Theme preview', encoding='utf8')
    app = QtWidgets.QApplication.instance()
    original = QtGui.QPalette(app.palette())
    checks = []
    try:
        if finished:
            import qpeHost
            widget = qpeHost.show(str(root))
        else:
            from quickPathExplorer import Explorer
            widget = Explorer()
            widget.resize(1240, 820)
            widget.show()
            widget.navigate(str(root))
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 60)
        selectFile(widget, root / 'notes40.txt')
        widget.setInspectorVisible(True)
        widget.address.setFocus()
        pause(150)
        theme = widget.appearance.theme
        theme_state = (widget.currentDirectory, widget.selectedPaths(),
                       widget.files.verticalScrollBar().value(), widget.columns.horizontalScrollBar().value())
        focus = app.focusWidget()
        for mode in ('light', 'dark', 'finder', 'light'):
            theme.setMode(mode)
            pause(50)
            assert theme.light == (mode in ('light', 'finder') and not finished)
            assert widget.files.palette().color(QtGui.QPalette.Base).lightness() > 200 if theme.light else widget.files.palette().color(QtGui.QPalette.Base).lightness() < 80
            if not finished and mode in ('light', 'dark'):
                expected_base = '#ffffff' if mode == 'light' else '#191919'
                expected_preview = '#f9f9f9' if mode == 'light' else '#222222'
                assert widget.actionsPanel.palette().color(QtGui.QPalette.Window).name() == expected_base
                assert widget.previewText.viewport().palette().color(QtGui.QPalette.Base).name() == expected_preview
                assert widget.files.palette().color(QtGui.QPalette.Highlight).name() == ('#d9d9d9' if mode == 'light' else '#505050')
            assert app.palette() == original
            assert app.focusWidget() is focus
            assert theme_state == (widget.currentDirectory, widget.selectedPaths(),
                                   widget.files.verticalScrollBar().value(), widget.columns.horizontalScrollBar().value())
            widget.grab().save(str(out / (mode + '.png')))
        checks.append('light/dark colors or Maya fixed dark; host palette, focus, selection and scroll preserved')
        if not finished:
            import qpeTheme
            reader = qpeTheme.windowsColors
            try:
                qpeTheme.windowsColors = lambda: (True, '#aa3300')
                theme.setMode('system')
                assert theme.light and theme.colors['accent'] == '#aa3300'
                qpeTheme.windowsColors = lambda: (False, '#2288aa')
                theme.refresh()
                assert not theme.light and theme.colors['accent'] == '#2288aa'
                checks.append('system preference changes refresh colors without OS writes')
            finally:
                qpeTheme.windowsColors = reader
            theme.setMode('light')
        widget.appearance.show()
        pause(100)
        widget.appearance.dialog.grab().save(str(out / 'display-settings.png'))
        checks.append('display settings opens in host theme')
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)
