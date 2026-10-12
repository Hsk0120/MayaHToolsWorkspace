"""専用MayaでQPEの終了時オブジェクト破棄を切り分ける。"""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maya/inhouse/QuickPathExplorer/python'))
from qpe_ui_maya import pause


def main(output_dir, finished):
    """ユーザーのMayaへ接続せず、終了直前の後始末方法を比較する。"""
    import qpeHost
    from qpeQt import QtWidgets, QtCore
    from maya import cmds
    out=Path(output_dir)
    os.environ['QPE_SETTINGS_FILE']=str(out/'settings.json')
    widget=qpeHost.show(str(out))
    pause(800)
    mode=os.environ.get('QPE_SHUTDOWN_MODE', 'normal')
    if mode == 'close':
        widget.close()
    elif mode == 'delete':
        widget.close()
        cmds.deleteUI(qpeHost.CONTROL)
    elif mode == 'content':
        widget.close()
        widget.deleteLater()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    elif mode == 'active':
        source=out/'source.txt'
        source.write_text('Disposable shutdown test', encoding='utf8')
        destination=out/'destination'
        destination.mkdir()
        organizer=widget.organizer
        organizer.queuePaused=True
        organizer.transfer('copy', [str(source)], str(destination), 'rename')
        organizer.queue[-1][-1]['paused'].set()
        organizer.queuePaused=False
        organizer.nextJob()
        pause(100)
        assert organizer.task is not None and not (destination/source.name).exists()
    pause(500)
    result=dict(status='passed', mode=mode)
    (out/'result.json').write_text(json.dumps(result), encoding='utf8')
    finished(result)
