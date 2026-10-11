"""本番ディレクトリモデルの結果配送に遅延と順序逆転を注入する。"""
from pathlib import Path
from qpeQt import QtCore, QtWidgets, shiboken
from qpeDirectoryModel import ScanSignals


def verify(widget, root, pause):
    """一覧の実データと更新ログでAT09/10/12を検証する。

    Args:
        widget (Explorer): 本番画面。
        root (Path): 専用データ。
        pause (callable): Qtイベント待機。

    Returns:
        dict: ケースごとの結果。
    """
    pending, logs = [], []
    models = [widget.folderModel, widget.fileModel]
    old_factories = [m.jobFactory for m in models]
    old_sinks = [m.traceSink for m in models]
    class ControlledScan(QtCore.QRunnable):
        """実行経路を変えずに完了順だけをテストから指定する。"""
        def __init__(self, path, generation):
            """識別子と結果シグナルを保持する。

            Args:
                path (str): 対象。
                generation (int): 要求番号。
            """
            super().__init__()
            self.path, self.generation = path, generation
            self.signals = ScanSignals()
            pending.append(self)
        def run(self):
            """GUIテストがシグナルを配送するためワーカは待機しない。"""

    def navigate(path):
        """対象一覧の最新要求を取得する。

        Args:
            path (Path): 移動先。

        Returns:
            list: フォルダー側とファイル側の要求。
        """
        widget.navigate(str(path))
        return [m._jobs[m._generations[str(path).replace('\\', '/')]] for m in models]

    def complete(jobs, label, error=''):
        """異なる名前の実スナップショットを本番受信スロットへ送る。

        Args:
            jobs (list): 対象要求。
            label (str): 識別可能な項目名。
            error (str): 失敗メッセージ。
        """
        for i, job in enumerate(jobs):
            job.signals.ready.emit(job.path, job.generation, [(label, i == 0, 123, 0.0)], error)
        pause(50)

    def assertRows(path, label):
        """両モデルの実際の行を照合する。

        Args:
            path (Path): 対象。
            label (str): 許される項目名。
        """
        for model in models:
            index = model.index(str(path))
            names = [model.index(row, 0, index).data() for row in range(model.rowCount(index))]
            assert names == [label], (model.objectName(), names, label)
            assert model.states[str(path).replace('\\', '/')][0] == 'ready'
        from qpe_ui_navigation import columns, visibleWidth
        views = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == path]
        assert views and visibleWidth(widget, views[-1]) > 0, ('missing visible child column', path,
            [(widget.folderModel.filePath(v.rootIndex()), v.isVisible(), v.geometry().getRect())
             for v in widget.columns.findChildren(QtWidgets.QListView)], widget.folderModel.filePath(widget.columns.currentIndex()))
        parent = next(v for v in columns(widget) if v.rootIndex() == widget.folderModel.index(str(path.parent)))
        assert parent.selectionModel().isSelected(widget.folderModel.index(str(path))), 'stale ancestor selection'
        ancestors = [path] + list(path.parents)
        assert all(Path(widget.folderModel.filePath(v.rootIndex())) in ancestors for v in columns(widget)), 'stale visible column'

    results = {}
    try:
        for model in models:
            model.jobFactory = ControlledScan
            model.traceSink = logs.append
        a = navigate(root / 'A')
        b = navigate(root / 'B')
        QtCore.QTimer.singleShot(200, lambda: complete(b, 'B-new'))
        QtCore.QTimer.singleShot(1500, lambda: complete(a, 'A-old'))
        pause(1600)
        assertRows(root / 'B', 'B-new')
        assert all(not row['accepted'] for row in logs if row['operation'] == 'directory-result' and row['path'].endswith('/A'))
        results['AT09'] = 'passed'
        a1, b, a2 = navigate(root / 'A'), navigate(root / 'B'), navigate(root / 'A')
        complete(a2, 'A-second')
        complete(b, 'B-old', 'old B error')
        complete(a1, 'A-first', 'old A error')
        assertRows(root / 'A', 'A-second')
        failed = navigate(root / 'A')
        complete(failed, 'must-not-display', 'current read denied')
        for model in models:
            assert model.states[str(root / 'A').replace('\\', '/')] == ('error', 'current read denied')
            assert model.rowCount(model.index(str(root / 'A'))) == 0
        recovered = navigate(root / 'A')
        complete(recovered, 'recovered')
        assertRows(root / 'A', 'recovered')
        results['AT10'] = 'passed'
        jobs = []
        for i in range(100):
            jobs.append(navigate(root / ('A' if i % 2 == 0 else 'B')))
            pause(50)
        start = len(logs)
        for i in range(99, -1, -1):
            complete(jobs[i], 'final' if i == 99 else 'stale-%d' % i)
        assertRows(root / 'B', 'final')
        accepted = [row for row in logs[start:] if row['operation'] == 'directory-result' and row['accepted']]
        assert len(accepted) == 2, accepted
        for row, model in zip(sorted(accepted, key=lambda r: r['model']), sorted(models, key=lambda m: m.objectName())):
            assert row['generation'] == model._generations[row['path']]
        late = navigate(root / 'A')
        widget.hide()
        complete(late, 'after-hide', 'late error')
        assert not any(row['accepted'] for row in logs[-2:])
        widget.show()
        # QObject破棄で受信先が切断されることも確認する。
        from qpeDirectoryModel import DirectoryModel
        disposed = DirectoryModel()
        disposed.jobFactory = ControlledScan
        disposed.activate([str(root)])
        late_job = pending[-1]
        disposed.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(disposed, QtCore.QEvent.DeferredDelete)
        pause(30)
        assert not shiboken.isValid(disposed)
        late_job.signals.ready.emit(late_job.path, late_job.generation, [], 'after destroy')
        results['AT12'] = 'passed'
    finally:
        for model, factory, sink in zip(models, old_factories, old_sinks):
            model.jobFactory = factory
            model.traceSink = sink
        widget.navigate(str(root))
        pause(150)
    results['log'] = logs
    return results
