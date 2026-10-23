"""専用Mayaでドック縮小と狭い領域の操作到達性を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
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
        for side in ('right','bottom'):
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=(side,False))
            pause(900)
            control=qpeDock._control_widget(qpeHost.CONTROL)
            if side=='bottom':
                slider=qpeDock._control_widget('TimeSlider')
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
