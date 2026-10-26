"""専用Mayaでドック縮小と狭い領域の操作到達性を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpeQt import QtCore, QtGui, QtWidgets, shiboken
from qpe_ui_maya import pause


def main(output_dir, finished):
    """左右・下ドックの縮小と再拡大を実際の分割領域で確認する。"""
    from maya import cmds
    import qpeHost
    import qpeDock
    out=Path(output_dir)
    os.environ['QPE_SETTINGS_FILE']=str(out/'settings.json')
    result=dict(status='error', checks=[], sizes=[])
    try:
        e=qpeHost.show(str(out)); pause(500)
        area=e._dockViewport
        # 同じタブ内の別エディターから戻った後も、記憶したサイズに固定されない。
        peer = 'qpeResizeTestPeer'
        cmds.workspaceControl(peer, label='Resize test peer', floating=True, loadImmediately=True)
        cmds.setParent(peer)
        cmds.columnLayout()
        cmds.text(label='Peer editor')
        cmds.workspaceControl(peer, edit=True, dockToMainWindow=('bottom', False))
        pause(700)
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, tabToControl=(peer, -1))
        pause(700)
        tab = area.parentWidget()
        while tab is not None and not isinstance(tab, QtWidgets.QTabWidget):
            tab = tab.parentWidget()
        assert tab is not None
        result['tabs'] = [(tab.tabText(i), tab.widget(i).objectName()) for i in range(tab.count())]
        qpe_index = next(i for i in range(tab.count()) if tab.widget(i).isAncestorOf(e))
        peer_index = next(i for i in range(tab.count()) if i != qpe_index)
        tab.setCurrentIndex(peer_index); pause(500)
        original_policy = tab.sizePolicy()
        tab.setCurrentIndex(qpe_index); pause(500)
        splitter, item = qpeDock._dock_splitter(area.parentWidget())
        index = splitter.indexOf(item)
        sizes = splitter.sizes()
        other = next(i for i in range(len(sizes)) if i != index and sizes[i] > 100)
        sizes[other] += sizes[index] - 240
        sizes[index] = 240
        splitter.setSizes(sizes); pause(500)
        assert item.height() <= 260, item.height()
        tab.setCurrentIndex(peer_index); pause(500)
        assert tab.sizePolicy() == original_policy
        tab.setCurrentIndex(qpe_index); pause(500)
        result['checks'].append('tabbed dock shrinks and restores sibling size policy')
        # 縦バーが出る末尾列でも名前と階層矢印が重ならない。
        folder = out / 'folders'
        folder.mkdir(exist_ok=True)
        for number in range(25):
            (folder / ('Week_%02d_長いフォルダー名' % number)).mkdir(exist_ok=True)
        e.navigate(str(folder)); pause(1200)
        e.columns.fitColumns(); pause(300)
        views = [v for v in e.columns.findChildren(QtWidgets.QListView)
                 if v.isVisible() and v.rootIndex() == e.columns.currentIndex()]
        assert views
        view = views[-1]
        for row in range(view.model().rowCount(view.rootIndex())):
            name = str(view.model().index(row, 0, view.rootIndex()).data())
            required = view.fontMetrics().horizontalAdvance(name) + max(12, view.fontMetrics().height()) + view.iconSize().width() + 12
            assert view.viewport().width() >= required, (view.viewport().width(), required)
        result['checks'].append('last column reserves full names, arrows and vertical scrollbar')
        area.grab().save(str(out / 'tabbed.png'))
        cmds.deleteUI(peer)
        pause(500)
        for side in ('right','bottom'):
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=(side,False))
            # 配置補正はMaya Code Editorと同じく明示的な表示・復元時に行う。
            qpeHost.show()
            pause(900)
            control=qpeDock._control_widget(qpeHost.CONTROL)
            if side=='bottom':
                slider=qpeDock._control_widget('TimeSlider')
                result['bottomRestore'] = {
                    'currentWatcher': qpeDock._watcher.isCurrent(),
                    'pending': qpeDock._watcher.restoreTimer.isActive(),
                }
                # 再ドックで置換され得るcontrolは、遅延処理の後に再取得する。
                control = qpeDock._control_widget(qpeHost.CONTROL)
                slider = qpeDock._control_widget('TimeSlider')
                result['bottomRestore']['controlValid'] = shiboken.isValid(control)
                result['bottomRestore']['sliderValid'] = shiboken.isValid(slider)
                assert control.mapToGlobal(QtCore.QPoint()).y()<slider.mapToGlobal(QtCore.QPoint()).y()
            splitter,item=qpeDock._dock_splitter(control)
            index=splitter.indexOf(item)
            sizes=splitter.sizes(); total=sum(sizes)
            assert len(sizes)>1
            other=next(i for i in range(len(sizes)) if i!=index and sizes[i]>100)
            for target in (600,280,520,250):
                sizes=splitter.sizes(); delta=sizes[index]-target
                sizes[index]=target;sizes[other]+=delta
                splitter.setSizes(sizes);pause(350)
                actual=control.width() if side=='right' else control.height()
                result['sizes'].append(dict(side=side,target=target,actual=actual))
                if target<=280: assert actual<400,(side,actual,area.minimumSizeHint())
            sizes=splitter.sizes(); delta=sizes[index]-520
            sizes[index]=520; sizes[other]+=delta; splitter.setSizes(sizes); pause(250)
            handle=splitter.handle(index if index else 1)
            before=control.width() if side=='right' else control.height()
            center=handle.rect().center()
            offset=QtCore.QPoint(60,0) if side=='right' else QtCore.QPoint(0,60)
            if index==0: offset=-offset
            for kind,point,button,buttons in (
                    (QtCore.QEvent.MouseButtonPress,center,QtCore.Qt.LeftButton,QtCore.Qt.LeftButton),
                    (QtCore.QEvent.MouseMove,center+offset,QtCore.Qt.NoButton,QtCore.Qt.LeftButton),
                    (QtCore.QEvent.MouseButtonRelease,center+offset,QtCore.Qt.LeftButton,QtCore.Qt.NoButton)):
                event=QtGui.QMouseEvent(kind,QtCore.QPointF(point),QtCore.QPointF(handle.mapToGlobal(point)),button,buttons,QtCore.Qt.NoModifier)
                QtWidgets.QApplication.sendEvent(handle,event)
            pause(350)
            after=control.width() if side=='right' else control.height()
            assert after<before,(side,before,after)
            result['sizes'].append(dict(side=side,dragBefore=before,dragAfter=after))
            area.horizontalScrollBar().setValue(area.horizontalScrollBar().maximum())
            area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
            pause(200)
            assert area.widget() is e and e.newSceneButton.isEnabled()
            result['checks'].append(side+' dock shrinks below previous content minimum and expands repeatedly')
            area.grab().save(str(out/(side+'.png')))
        cmds.workspaceControl(qpeHost.CONTROL,edit=True,floating=True)
        pause(400)
        e.window().resize(420,260);pause(400)
        assert area.width()<652 and area.height()<444
        result['checks'].append('floating window also shrinks without inaccessible clipped controls')
        result['status']='passed'
    except Exception:
        result['error']=traceback.format_exc()
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    finished(result)
