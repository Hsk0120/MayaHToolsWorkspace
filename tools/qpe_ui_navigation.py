"""カラム操作の可視内容・選択・履歴を専用GUIで検証する。"""
import json
import os
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import ROOT, pause, waitFor
from qpeQt import QtCore, QtWidgets, QtTest


def columns(widget):
    """有効な表示カラムを返す。

    Args:
        widget (Explorer): 対象画面。

    Returns:
        list: 可視カラム。
    """
    # QColumnViewは空の末尾列を幅0のまま再showすることがある。
    # 画面上の領域がない列は表示カラムではない。幅を持つ空列は引き続き検出する。
    return [v for v in widget.columns.findChildren(QtWidgets.QListView)
            if v.isVisible() and v.width() > 0 and v.rootIndex().isValid()]


def visibleWidth(widget, view):
    """実際に画面内に現れている幅を取得する。

    Args:
        widget (Explorer): 対象画面。
        view (QListView): カラム。

    Returns:
        int: クリップ後の幅。
    """
    bounds = QtCore.QRect(view.mapTo(widget.columns.viewport(), QtCore.QPoint()), view.size())
    return bounds.intersected(widget.columns.viewport().rect()).width()


def inspectFolder(widget, folder, require_visible=True):
    """上下段の内容と各祖先カラムの選択を実ファイルと照合する。

    Args:
        widget (Explorer): 対象画面。
        folder (Path): 期待するフォルダー。
        require_visible (bool): 子カラムが画面内にあることも要求するか。
    """
    folder = folder.resolve()
    expected_dirs = sorted(p.name for p in folder.iterdir() if p.is_dir())
    expected_files = sorted(p.name for p in folder.iterdir() if p.is_file())
    def contentsMatch():
        """非同期のフォルダー・ファイル読込完了を待つ。"""
        if Path(widget.currentDirectory) != folder:
            return False
        if widget.columns._hintTimer.isActive():
            return False
        for model in (widget.folderModel, widget.fileModel):
            if any(model.states.get(path, ('loading', ''))[0] == 'loading' for path in model._active):
                return False
        matches = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == folder]
        empty_child = not expected_dirs and folder != Path(widget.browseRoot)
        if not matches and not empty_child:
            return False
        if empty_child:
            if matches:
                return False
            names = []
        else:
            view = matches[-1]
            model = view.model()
            names = sorted(model.fileName(model.index(i, 0, view.rootIndex())) for i in range(model.rowCount(view.rootIndex())))
        proxy = widget.fileProxy
        files = sorted(proxy.index(i, 0, widget.files.rootIndex()).data() for i in range(proxy.rowCount(widget.files.rootIndex())))
        return names == expected_dirs and files == expected_files and (empty_child or not require_visible or visibleWidth(widget, view) >= round(80 * getattr(widget.columns, 'columnScale', 1.0)))
    try:
        waitFor(contentsMatch)
    except AssertionError:
        # GUI起動の標準出力に依存せず、間欠的な失敗の状態を証跡へ残す。
        diagnostic = {
            'expected': str(folder),
            'directory': widget.currentDirectory,
            'current': widget.folderModel.filePath(widget.columns.currentIndex()),
            'hint_timer': widget.columns._hintTimer.isActive(),
            'models': [{
                'active': list(model._active),
                'states': {str(path): state for path, state in model.states.items()},
            } for model in (widget.folderModel, widget.fileModel)],
            'views': [{
                'visible': v.isVisible(), 'hidden': v.isHidden(),
                'width': v.width(), 'x': v.x(),
                'root': widget.folderModel.filePath(v.rootIndex()),
                'rows': v.model().rowCount(v.rootIndex()),
            } for v in widget.columns.findChildren(QtWidgets.QListView)],
        }
        settings = os.environ.get('QPE_SETTINGS_FILE')
        if settings:
            with (Path(settings).parent / 'navigation-failures.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(diagnostic, ensure_ascii=False, default=str) + '\n')
        print('COLUMN_CURRENT', widget.folderModel.filePath(widget.columns.currentIndex()),
              widget.folderModel.filePath(widget.columns.rootIndex()), widget.columns._hintTimer.isActive(), flush=True)
        print('COLUMN_DIAGNOSTICS', [(v.isVisible(), v.isHidden(), v.width(), v.x(),
              widget.folderModel.filePath(v.rootIndex()), v.model().rowCount(v.rootIndex()))
              for v in widget.columns.findChildren(QtWidgets.QListView)], flush=True)
        raise
    assert Path(widget.address.text()) == folder
    active = widget.folderModel.index(str(folder))
    assert widget.columns.currentIndex() == active
    # アクティブ階層以外の古いカラムが表示されたままになっていないか。
    ancestors = set([folder] + list(folder.parents))
    for view in columns(widget):
        root = Path(widget.folderModel.filePath(view.rootIndex()))
        assert root in ancestors, ('stale column', root, folder)
        if root != folder and visibleWidth(widget, view) > 0:
            child = folder
            while child.parent != root:
                child = child.parent
            selected = [Path(widget.folderModel.filePath(i)) for i in view.selectionModel().selectedIndexes() if i.column() == 0]
            assert child in selected, ('ancestor highlight mismatch', root, child, selected)


def click(widget, folder, double=False):
    """実クリックと表示内容確認を実行する。

    Args:
        widget (Explorer): 対象画面。
        folder (Path): 選択する項目。
        double (bool): ダブルクリックか。
    """
    index = widget.folderModel.index(str(folder))
    waitFor(lambda: any(v.rootIndex() == index.parent() for v in columns(widget)))
    view = [v for v in columns(widget) if v.rootIndex() == index.parent()][-1]
    view.scrollTo(index)
    position = view.visualRect(index).center()
    assert view.viewport().rect().contains(position), ('item outside viewport', folder)
    QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, position)
    if double:
        QtTest.QTest.mouseDClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, position)
    inspectFolder(widget, folder)


def main(output_dir, finished=None):
    """隔離フォルダーで回帰テストを実行し診断と画面を保存する。

    Args:
        output_dir (Path): 証跡先。
        finished (callable | None): 専用Mayaの終了通知。
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output_dir / 'settings.json')
    checks = []
    stage = 'setup'
    widget = None
    try:
        root = output_dir / 'ReviewProject'
        for part in ('Characters/Hero/Rig/Work', 'Characters/Villain/Model', 'Props/Chair/Textures', 'Empty', '日本語 空白/素材/画像'):
            (root / part).mkdir(parents=True, exist_ok=True)
        (root / 'Characters/Hero/hero.ma').write_text('// test fixture only', encoding='utf-8')
        (root / 'Characters/Villain/villain.txt').write_text('villain', encoding='utf-8')
        many = root / 'Many'
        for i in range(100):
            (many / ('item_%03d' % i) / 'child').mkdir(parents=True, exist_ok=True)
        if finished:
            import qpeHost
            widget = qpeHost.show(str(root))
        else:
            from quickPathExplorer import Explorer
            widget = Explorer()
            widget.show()
            widget.navigate(str(root))
        pause(500)
        stage = 'cold address navigation and ancestor highlights'
        inspectFolder(widget, root)
        checks.append(stage)
        stage = 'sibling clicks and exact child names'
        click(widget, root / 'Characters')
        for name in ('Hero', 'Villain', 'Hero', 'Villain', 'Hero'):
            click(widget, root / 'Characters' / name)
        checks.append(stage)
        stage = 'keyboard sibling selection updates children'
        parent_index = widget.folderModel.index(str(root / 'Characters'))
        view = [v for v in columns(widget) if v.rootIndex() == parent_index][-1]
        view.setFocus()
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Down)
        inspectFolder(widget, root / 'Characters/Villain')
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Up)
        inspectFolder(widget, root / 'Characters/Hero')
        checks.append(stage)
        stage = 'empty folder clears stale children/files'
        widget.navigate(str(root))
        click(widget, root / 'Empty')
        checks.append(stage)
        stage = 'Japanese and space path, typed address'
        widget.address.setText(str(root / '日本語 空白'))
        QtTest.QTest.keyClick(widget.address, QtCore.Qt.Key_Return)
        inspectFolder(widget, root / '日本語 空白')
        click(widget, root / '日本語 空白/素材')
        checks.append(stage)
        stage = 'deep click then keyboard navigation'
        widget.navigate(str(root / 'Characters'))
        click(widget, root / 'Characters/Hero')
        click(widget, root / 'Characters/Hero/Rig', double=True)
        click(widget, root / 'Characters/Hero/Rig/Work')
        widget.backButton.click()
        inspectFolder(widget, root / 'Characters/Hero/Rig', require_visible=False)
        widget.forwardButton.click()
        inspectFolder(widget, root / 'Characters/Hero/Rig/Work', require_visible=False)
        checks.append(stage)
        stage = 'nearest four columns preserve name widths and empty terminal is hidden'
        widget.navigate(str(root))
        pause(150)
        shallow_width = columns(widget)[-1].width()
        widget.navigate(str(root / 'Characters/Hero/Rig/Work'))
        pause(150)
        deep_width = columns(widget)[-1].width()
        assert all(v.width() >= widget.columns.contentWidth(v.rootIndex()) for v in columns(widget)[-4:])
        if sum(v.width() for v in columns(widget)) <= widget.columns.viewport().width():
            assert all(visibleWidth(widget, v) == v.width() for v in columns(widget))
        very_deep = root.joinpath(*('d%02d' % i for i in range(18)))
        very_deep.mkdir(parents=True, exist_ok=True)
        widget.navigate(str(very_deep))
        pause(200)
        inspectFolder(widget, very_deep)
        assert all(v.width() >= 80 for v in columns(widget))
        assert all(v.width() >= widget.columns.contentWidth(v.rootIndex()) for v in columns(widget)[-4:])
        assert widget.columns.horizontalScrollBar().maximum() > 0
        widget.navigate(str(root))
        pause(150)
        assert columns(widget)[-1].width() == shallow_width
        checks.append(stage)
        stage = 'vertical and horizontal scroll restoration'
        widget.navigate(str(many))
        inspectFolder(widget, many)
        view = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == many][-1]
        waitFor(lambda: view.verticalScrollBar().maximum() > 0)
        view.verticalScrollBar().setValue(45)
        y = view.verticalScrollBar().value()
        assert y > 0
        widget.columns.horizontalScrollBar().setValue(0)
        widget.navigate(str(root / 'Props'))
        widget.backButton.click()
        pause(300)
        view = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == many][-1]
        assert view.verticalScrollBar().value() == y, (y, view.verticalScrollBar().value())
        assert widget.columns.horizontalScrollBar().value() == 0
        inspectFolder(widget, many, require_visible=False)
        checks.append(stage)
        stage = 'revisited click must keep child column on screen'
        widget.navigate(str(many / 'item_099'))
        widget.columns.horizontalScrollBar().setValue(0)
        widget.navigate(str(root))
        widget.navigate(str(many))
        widget.columns.scrollTo(widget.folderModel.index(str(many)))
        click(widget, many / 'item_099')
        checks.append(stage)
        stage = 'forward history truncation after new branch'
        widget.navigate(str(root / 'Characters'))
        widget.navigate(str(root / 'Props'))
        widget.backButton.click()
        widget.navigate(str(root / 'Empty'))
        assert not widget.forwardButton.isEnabled()
        checks.append(stage)
        stage = 'invalid or removed destination preserves current display'
        before = widget.currentDirectory
        assert not widget.navigate(str(root / 'does-not-exist'))
        assert widget.currentDirectory == before
        inspectFolder(widget, Path(before), require_visible=False)
        checks.append(stage)
        stage = 'rapid alternating address navigation final state'
        for i in range(24):
            widget.navigate(str(root / ('Characters/Hero' if i % 2 else 'Props')))
        inspectFolder(widget, root / 'Characters/Hero')
        checks.append(stage)
        stage = 'resize and sidebar toggles preserve active folder'
        if finished:
            from maya import cmds
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1000, resizeHeight=650)
        else:
            widget.resize(1000, 650)
        pause(150)
        widget.sidebarButton.click()
        widget.sidebarButton.click()
        pause(100)
        widget.columns.scrollTo(widget.columns.currentIndex())
        inspectFolder(widget, root / 'Characters/Hero')
        checks.append(stage)
        stage = 'filesystem notification populates an initially empty folder'
        widget.navigate(str(root / 'Empty'))
        inspectFolder(widget, root / 'Empty', require_visible=False)
        (root / 'Empty/newChild').mkdir()
        inspectFolder(widget, root / 'Empty', require_visible=False)
        pause(100)
        widget.columns.scrollTo(widget.columns.currentIndex())
        click(widget, root / 'Empty/newChild')
        checks.append(stage)
        widget.navigate(str(root / 'Characters/Hero'))
        if finished:
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1240, resizeHeight=790)
        else:
            widget.resize(1240, 790)
        pause(250)
        widget.columns.scrollTo(widget.columns.currentIndex())
        widget.grab().save(str(output_dir / 'navigation.png'))
        result = {'status': 'passed', 'checks': checks}
    except Exception:
        result = {'status': 'error', 'stage': stage, 'checks': checks, 'error': traceback.format_exc()}
        if widget:
            widget.grab().save(str(output_dir / 'failure.png'))
            result['active'] = widget.currentDirectory
            result['history'] = widget._history
            result['file_root'] = widget.fileModel.filePath(widget.fileProxy.mapToSource(widget.files.rootIndex()))
            result['file_names'] = [widget.fileProxy.index(i, 0, widget.files.rootIndex()).data() for i in range(widget.fileProxy.rowCount(widget.files.rootIndex()))]
            result['columns'] = [{'root': widget.folderModel.filePath(v.rootIndex()), 'visibleWidth': visibleWidth(widget, v),
                                  'selected': [widget.folderModel.filePath(i) for i in v.selectionModel().selectedIndexes()]}
                                 for v in columns(widget)]
    (output_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result['status'] == 'passed' else 1)
