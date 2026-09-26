"""Maya標準のドッキングホスト。編集画面はC++製ウィジェットを使用する。"""
from maya import cmds, OpenMayaUI
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance, getCppPointer, isValid
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance, getCppPointer, isValid

CONTROL = 'heditDockWorkspaceControl'
# 保存済みの旧ドックがある場合はその配置を再利用する。画面名はheditに更新する。
if (cmds.workspaceControl('HEditorDockWorkspaceControl', exists=True)
        and not cmds.workspaceControl(CONTROL, exists=True)):
    CONTROL = 'HEditorDockWorkspaceControl'
_host = globals().get('_host')
_opening = False


class heditDock(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """フローティングとMayaレイアウトへのドッキングを扱うホスト。"""
    def __init__(self):
        super(heditDock, self).__init__()
        self.setObjectName('heditDock')
        self.setWindowTitle('hedit - Python / MEL')
        self.resize(1050, 740)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        editor = wrapInstance(int(cmds.hedit()), QtWidgets.QMainWindow)
        editor.setWindowFlags(QtCore.Qt.Widget)
        layout.addWidget(editor)

    @property
    def editor(self):
        # Qt5ではMaya側のreparentで既存のPythonラッパーが無効化される。
        # Mayaコマンドが保持する生存中のQPointerから改めてラップする。
        return wrapInstance(int(cmds.hedit()), QtWidgets.QMainWindow)


def show(floating=None, restore=False):
    """一つのホストを再利用し、明示起動では閉じてから開き直す。

    Args:
        floating (bool | None): 指定時だけ浮動状態を変更する。
        restore (bool): Maya復元からの呼出。閉じ直す処理を行わない。

    Returns:
        QWidget: 未保存コードと配置を保持する唯一のホスト。
    """
    global _host, _opening
    if _opening:
        return _host
    _opening = True
    try:
        # Pythonのreloadや参照消失後も、Mayaが所有するホストを回収する。
        hosts = [widget for widget in QtWidgets.QApplication.allWidgets()
                 if isValid(widget) and widget.objectName() == 'heditDock']
        if _host is None or not isValid(_host):
            _host = next((widget for widget in hosts
                          if widget.findChild(QtWidgets.QMainWindow, 'hedit') is not None),
                         hosts[0] if hosts else None)
        for widget in hosts:
            if widget is not _host:
                widget.hide()
        if _host is not None and not restore:
            # 本体のcloseEventでタブを保存する。取消時は現在の画面をそのまま残す。
            # workspaceControlは破棄せず、Mayaのドッキング配置を維持する。
            if not _host.editor.close():
                return _host
            _host.hide()
        return _show(floating=floating, restore=restore)
    finally:
        _opening = False


def _show(floating=None, restore=False):
    """既存ホストを再利用する。通常の閉じる操作ではタブを保持する。"""
    global _host
    # 本体生成は内部reporterなどのMaya UIを作るため、生成前に復元先を確定する。
    # getCurrentParentを生成後に読むと、非表示reporter側へ誤挿入され得る。
    restore_parent = None
    if restore:
        restore_parent = OpenMayaUI.MQtUtil.findControl(CONTROL) or OpenMayaUI.MQtUtil.getCurrentParent()
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.workspaceControl(CONTROL, edit=True, label='hedit - Python / MEL')
    if _host is None or not isValid(_host):
        _host = heditDock()
        # 閉じたworkspaceControlのuiScriptは本体生成を遅延する。
        # 明示的なshowで初めて生成した場合、既存のMayaレイアウトへ挿入する。
        if not restore and cmds.workspaceControl(CONTROL, exists=True):
            parent = OpenMayaUI.MQtUtil.findControl(CONTROL)
            OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
    if restore:
        parent = restore_parent
        if not parent:
            raise RuntimeError('hedit workspaceControl was not found')
        OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
        _host.setVisible(True)
        _host.editor.show()
        return _host
    if cmds.workspaceControl(CONTROL, exists=True):
        if floating is not None:
            cmds.workspaceControl(CONTROL, edit=True, floating=floating)
        # 旧版で別レイアウトへ入ったホストも、明示的な再表示時に修復する。
        parent = OpenMayaUI.MQtUtil.findControl(CONTROL)
        control = wrapInstance(int(parent), QtWidgets.QWidget)
        if not control.isAncestorOf(_host):
            OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(getCppPointer(_host)[0]), int(parent))
        # Qt5ではuiScript直後の浮動ドックにrestoreを掛けるとネイティブ
        # ウィンドウ再生成で落ちる場合がある。保持中のコントロールを表示する。
        cmds.workspaceControl(CONTROL, edit=True, visible=True)
        _host.setVisible(True)
        _host.editor.show()
    else:
        _host.show(dockable=True, floating=True if floating is None else floating,
                   area='bottom', retain=True, width=1050, height=740, plugins=['hedit'],
                   uiScript='import hedit; hedit.restore()')
    return _host


def release():
    """プラグイン解除時に空のドックを残さない。タブの保存はC++側で行う。"""
    global _host
    if cmds.workspaceControl(CONTROL, exists=True):
        # deleteUI中のcloseCommandから配置を照会すると、Qt5では破棄中の
        # workspaceControlへ再入してクラッシュする。状態はuninstallで保存済み。
        cmds.workspaceControl(CONTROL, edit=True, closeCommand='')
        cmds.deleteUI(CONTROL)
    elif _host is not None and isValid(_host):
        _host.deleteLater()
    _host = None
