"""ガイドの確認とリグ仕上げの選択操作。"""

import mlib
from maya import cmds
from mlib import getNode
from mlib.decorator import undoTransaction

from . import guideGeometry


def _selected():
    return [item.getName(full=True) for item in mlib.ls(selection=True, long=True, flatten=True)]


@undoTransaction("mlrigSmoothRenderShapes")
def setSmooth(nodes, level):
    """選択メッシュのスムーズ表示を変更し、初回の設定を形状ごとに保持する。"""
    if cmds.autoKeyframe(query=True, state=True):
        raise ValueError("自動キーをオフにしてください")
    for node in nodes:
        mesh = guideGeometry._mesh(node).getName(full=True)
        tag = mesh + ".mlrigSmoothPreviewBackup"
        if level is None:
            if cmds.objExists(tag):
                old = cmds.getAttr(tag)
                cmds.setAttr(mesh + ".smoothLevel", old // 4)
                cmds.setAttr(mesh + ".displaySmoothMesh", old % 4)
                cmds.deleteAttr(tag)
        else:
            if not cmds.objExists(tag):
                previous = 4 * cmds.getAttr(mesh + ".smoothLevel") + cmds.getAttr(mesh + ".displaySmoothMesh")
                cmds.addAttr(mesh, longName="mlrigSmoothPreviewBackup", attributeType="long")
                cmds.setAttr(tag, previous)
            cmds.setAttr(mesh + ".smoothLevel", level)
            cmds.setAttr(mesh + ".displaySmoothMesh", 2 if level else 0)


@undoTransaction("mlrigPlaceFootPivot")
def placePivot(guide, marker):
    """指定した足ガイドの回転・スケールピボットをマーカー位置に合わせる。"""
    if not cmds.objectType(guide, isAType="transform"):
        raise ValueError("足ガイドと支点を順に選択してください")
    cmds.xform(guide, worldSpace=True, pivots=list(guideGeometry._point(marker)), preserve=True)
    if not cmds.objExists(guide + ".mlrigFootPivot"):
        cmds.addAttr(guide, longName="mlrigFootPivot", attributeType="bool", hidden=True)
    cmds.setAttr(guide + ".mlrigFootPivot", True)


def faceView():
    """選択した顔カメラを専用パネルで開き、元ビューのカメラを保持する。"""
    selection = _selected()
    if len(selection) != 1:
        raise ValueError("顔用カメラを選択してください")
    camera = selection[0]
    if cmds.nodeType(camera) != "camera" and not cmds.listRelatives(camera, shapes=True, type="camera"):
        raise ValueError("カメラを選択してください")
    win = "mlrigFaceCamera"
    if cmds.window(win, exists=True):
        # 再表示も通常のウィンドウを閉じる際と同じクリーンアップを通す。
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            from PySide2.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if widget.objectName() == win:
                widget.close()
                break
        if cmds.window(win, exists=True):
            cmds.deleteUI(win, window=True)

    proxy = []

    def cleanup(*_):
        """プロキシの現在のDAGパスを解決し、このビューが所有するカメラだけを除去する。"""
        if proxy and proxy[0].isValid():
            path = proxy[0].getName(full=True)
            if cmds.modelPanel(panel, exists=True):
                cmds.modelPanel(panel, edit=True, camera="persp")
            mlib.delete(path)
        proxy[:] = []

    cmds.window(win, title="顔カメラ", widthHeight=(640, 480), closeCommand=cleanup)
    layout = cmds.formLayout()
    panel = cmds.modelPanel(menuBarVisible=False, camera=camera)

    def reframe(*_):
        selected = _selected()
        if not selected:
            raise ValueError("フレームに収める顔部品を選択してください")
        if not proxy or not proxy[0].isValid():
            transform = cmds.listRelatives(camera, parent=True, fullPath=True)[0] if cmds.nodeType(camera) == "camera" else camera
            source = camera if cmds.nodeType(camera) == "camera" else cmds.listRelatives(transform, shapes=True, type="camera", fullPath=True)[0]
            copy, shape = cmds.camera(name="faceViewCamera#")
            proxy[:] = [getNode(copy)]
            try:
                # 参照カメラの子階層・ドライバーは複製せず、評価済みの姿勢と光学設定を使う。
                for node in (copy, shape):
                    getNode(node).mfn().setDoNotWrite(True)
                cmds.xform(copy, worldSpace=True, matrix=cmds.xform(transform, query=True, worldSpace=True, matrix=True))
                for attr in ("focalLength", "cameraScale", "horizontalFilmAperture", "verticalFilmAperture", "filmFit",
                             "horizontalFilmOffset", "verticalFilmOffset", "overscan", "nearClipPlane", "farClipPlane",
                             "orthographic", "orthographicWidth", "centerOfInterest"):
                    cmds.setAttr(shape + "." + attr, cmds.getAttr(source + "." + attr))
                cmds.modelPanel(panel, edit=True, camera=copy)
            except (RuntimeError, TypeError, AttributeError):
                cleanup()
                raise
            finally:
                mlib.select(selected, replace=True)
        cmds.viewFit(proxy[0].getName(full=True), all=False)
    button = cmds.button(label="選択した顔部品をフレームに収める", command=reframe, parent=layout)
    control = cmds.modelPanel(panel, query=True, control=True)
    cmds.formLayout(layout, edit=True, attachForm=[(control, edge, 0) for edge in ("left", "right", "top")] +
                    [(button, edge, 0) for edge in ("left", "right", "bottom")], attachControl=[(control, "bottom", 2, button)])
    cmds.scriptJob(uiDeleted=[win, cleanup], runOnce=True)
    cmds.showWindow(win)
    return panel


def show():
    """選択順と設定を明示してガイド・形状の操作を実行する。"""
    win = "mlrigGuideGeometry"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)
    cmds.window(win, title="ガイドと形状の編集")
    cmds.columnLayout(adjustableColumn=True)
    operation = cmds.optionMenu(label="位置の計算法")
    for value in ("individual", "average", "sum", "surfaceCentroid", "boundsMin", "boundsMax", "boundsCenter"):
        cmds.menuItem(label=value)
    cmds.button(label="選択位置にマーカーを配置", command=lambda *_: guideGeometry.markers(_selected(), cmds.optionMenu(operation, query=True, value=True)))
    plugs = cmds.textFieldGrp(label="線の入力（任意・カンマ区切り）")
    def line(*_):
        text = cmds.textFieldGrp(plugs, query=True, text=True).strip()
        return guideGeometry.line([p.strip() for p in text.split(",")] if text else _selected())
    cmds.button(label="選択した制御を線で結ぶ", command=line)
    pairs = cmds.intFieldGrp(label="X方向の点対数", value1=1)
    parent = cmds.textFieldGrp(label="基準面の親（任意）")
    cmds.button(label="X・Z点対から基準面を作成", command=lambda *_: guideGeometry.meanPlane(_selected(), cmds.intFieldGrp(pairs, query=True, value1=True),
                cmds.textFieldGrp(parent, query=True, text=True).strip() or None))
    scale = cmds.floatFieldGrp(label="RBF半径（cm）", value1=1.0)
    kernel = cmds.optionMenu(label="カーネル")
    for value in ("gaussian", "exponential", "linear", "multiquadratic", "inverseQuadratic", "inverseMultiquadratic", "cubic", "thinPlate"):
        cmds.menuItem(label=value)
    metric = cmds.optionMenu(label="距離尺度")
    for value in ("euclidean", "manhattan", "chebyshev", "angular"):
        cmds.menuItem(label=value)
    def transfer(*_):
        nodes = _selected()
        if len(nodes) != 3:
            raise ValueError("基準、変形後、転送先の順に3メッシュを選択してください")
        guideGeometry.transfer(*nodes, scale=cmds.floatFieldGrp(scale, query=True, value1=True),
                               kernelName=cmds.optionMenu(kernel, query=True, value=True), metric=cmds.optionMenu(metric, query=True, value=True))
    cmds.button(label="基準と変形後の差を選択形状の複製へ転送", command=transfer)
    level = cmds.intSliderGrp(label="スムーズ表示レベル", field=True, minValue=0, maxValue=4, value=2)
    cmds.button(label="選択メッシュの表示レベルを変更", command=lambda *_: setSmooth(_selected(), cmds.intSliderGrp(level, query=True, value=True)))
    cmds.button(label="元の表示レベルに復帰", command=lambda *_: setSmooth(_selected(), None))
    cmds.button(label="足ガイドの支点を選択位置に合わせる", command=lambda *_: placePivot(*_selected()))
    cmds.button(label="選択カメラで顔ビューを開く", command=lambda *_: faceView())
    cmds.showWindow(win)
