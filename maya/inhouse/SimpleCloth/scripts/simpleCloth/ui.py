"""Maya標準UIで布の作成・マップ・物理設定・出力を編集する。"""

from maya import cmds
from maya.api import OpenMaya as om

from . import api, node


WINDOW = "SimpleClothWindow"
_window = None


class ClothWindow:
    """UIのコントロール名だけを保持し、値の正本はシーンに置く。"""

    def __init__(self):
        """既存ウィンドウを置き換えてシーン内のSolver一覧を作る。"""
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        self.solver = None
        self.window = cmds.window(WINDOW, title="Simple Cloth 0.1 — XPBD Mesh Cloth", widthHeight=(580, 850))
        cmds.scrollLayout(childResizable=True)
        self.column = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        self.refresh()
        cmds.showWindow(self.window)

    def _call(self, function, *args):
        """ユーザー操作の失敗をMayaへ通知し、UIコールバックを終了する。"""
        try:
            return function(*args)
        except (ValueError, TypeError, RuntimeError, OSError) as error:
            cmds.warning(f"Simple Cloth: {error}")
            return None

    def _section(self, label, collapsed=False):
        """折りたたみ可能な編集グループを作る。"""
        cmds.setParent(self.column)
        cmds.frameLayout(label=label, collapsable=True, collapse=collapsed, marginWidth=8, marginHeight=6)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)

    def _attr(self, name, label):
        """属性への接続をMaya標準コントロールに任せ、Undoと値同期を保つ。"""
        if name in ("stretchCompliance", "bendCompliance"):
            plug = self.solver + "." + name
            field = cmds.textFieldGrp(label=label, text=f"{cmds.getAttr(plug):.8g}",
                                       annotation="0以上。指数表記 (例: 1e-6) も使用できます")

            def update(*_):
                """小さい係数を丸めず表示する。UI削除時にscriptJobも終了する。"""
                cmds.textFieldGrp(field, edit=True, text=f"{cmds.getAttr(plug):.8g}")

            def change(*_):
                """検証済みの数値だけを書込み、入力失敗時は表示を元へ戻す。"""
                try:
                    value = float(cmds.textFieldGrp(field, query=True, text=True))
                    api._number(value, label, 0)
                    with api._transaction("Simple Cloth: " + label):
                        cmds.setAttr(plug, value)
                finally:
                    update()

            cmds.textFieldGrp(field, edit=True, changeCommand=lambda *_: self._call(change))
            cmds.scriptJob(attributeChange=[plug, update], parent=field)
        else:
            cmds.attrControlGrp(attribute=self.solver + "." + name, label=label)

    def refresh(self, selected=None):
        """現在の設定ノードに合わせて画面を再構築する。"""
        for child in cmds.columnLayout(self.column, query=True, childArray=True) or []:
            cmds.deleteUI(child)
        cmds.setParent(self.column)
        cmds.text(label="メッシュ → 固定頂点 / ペイント → 再生 → ベイク", align="left", height=26)
        cmds.button(label="選択メッシュから作成  /  Create Cloth", height=32, command=lambda *_: self._call(self._create))
        solvers = cmds.ls(type=node.SimpleClothNode.TYPE_NAME) if cmds.pluginInfo(str(api.PLUGIN), query=True, loaded=True) else []
        self.solver = selected or self.solver
        if self.solver not in solvers:
            self.solver = solvers[0] if solvers else None
        self.menu = cmds.optionMenu(label="Solver", changeCommand=lambda value: self.refresh(value))
        for item in solvers:
            cmds.menuItem(label=item)
        if self.solver:
            cmds.optionMenu(self.menu, edit=True, value=self.solver)
        cmds.button(label="シーンから一覧を更新", command=lambda *_: self.refresh())
        if not self.solver:
            cmds.text(label="低分割のメッシュを選択してCreate Clothを押してください。\n入力のスキン・キーを保ち、別メッシュへ出力します。", align="left", height=48)
            return
        self._section("1  Mesh / Max Distance Map")
        for attribute, label in (("sourceMesh", "入力を選択"), ("outputMeshObject", "出力を選択")):
            cmds.button(label=label, command=lambda *_, attr=attribute: self._call(self._select, attr))
        self._attr("maxDistance", "Max Distance (cm)")
        cmds.text(label="Map 0 = 入力に固定 / 1 = Max Distance全長まで移動", align="left")
        self.weight = cmds.floatSliderGrp(label="選択頂点のMap値", field=True, minValue=0, maxValue=1, value=0)
        cmds.button(label="選択頂点へMap値を設定", command=lambda *_: self._call(self._set_selected))
        cmds.button(label="Max Distanceをペイント", command=lambda *_: self._call(api.paintMap, self.solver))
        cmds.button(label="全頂点を解放 (Map = 1)", command=lambda *_: self._call(api.setMap, self.solver, [1.0] * len(api.getMap(self.solver))))
        self._section("2  Stretch / Bend / Animation")
        for attr, label in (("stretchCompliance", "Stretch Compliance"), ("bendCompliance", "Bend Compliance"),
                            ("particleMass", "Particle Mass (kg)"), ("damping", "Damping (1/s)"),
                            ("animDrive", "Anim Drive (1/s)"), ("blend", "Simulation Blend")):
            self._attr(attr, label)
        cmds.text(label="Compliance: 小さいほど硬い / 曲げは対向頂点の距離で近似", align="left")
        self._section("3  Forces / Backstop", collapsed=True)
        for attr, label in (("gravity", "Gravity (cm/s2)"), ("wind", "Wind Acceleration (cm/s2)"),
                            ("backstopRadius", "Backstop Radius (cm)"), ("backstopDistance", "Backstop Distance (cm)")):
            self._attr(attr, label)
        self._section("4  Collisions", collapsed=True)
        for attr, label in (("collisionThickness", "Collision Thickness (cm)"), ("friction", "Friction"),
                            ("selfCollision", "Particle Self Collision"), ("selfCollisionThickness", "Self Thickness (cm)")):
            self._attr(attr, label)
        self.kind = cmds.optionMenu(label="Collider")
        for kind in ("sphere", "capsule", "plane"):
            cmds.menuItem(label=kind)
        self.attach = cmds.checkBox(label="選択Transform / Jointに追従", value=False)
        cmds.button(label="コライダーを追加", command=lambda *_: self._call(self._add_collider))
        cmds.button(label="選択コライダーを削除", command=lambda *_: self._call(self._remove_collider))
        cmds.text(label="球/カプセルはclothRadius・clothHeightで寸法変更 (cm)", align="left")
        self._section("5  Solver / Diagnostics", collapsed=True)
        for attr, label in (("startFrame", "Start Frame"), ("solverRate", "Solver Rate (Hz)"),
                            ("iterations", "Iterations"), ("maxSteps", "Max Steps"),
                            ("stretchError", "Max Stretch Error (ratio)"), ("residualPenetration", "Residual Penetration (cm)"),
                            ("maxDistanceError", "Max Distance Error (cm)")):
            self._attr(attr, label)
        cmds.button(label="リセットして開始フレームへ", command=lambda *_: self._call(api.reset, self.solver))
        self._section("6  Preset / Bake / Remove", collapsed=True)
        cmds.button(label="プリセット保存 (係数 + Map)", command=lambda *_: self._call(self._preset, True))
        cmds.button(label="プリセット読込 (同一トポロジー)", command=lambda *_: self._call(self._preset, False))
        self.range = cmds.intFieldGrp(label="Bake Range", numberOfFields=2,
                                      value1=int(cmds.playbackOptions(query=True, minTime=True)),
                                      value2=int(cmds.playbackOptions(query=True, maxTime=True)))
        cmds.button(label="別メッシュへベイク (Blend Shape)", command=lambda *_: self._call(self._bake))
        cmds.button(label="セットアップを削除 (入力・ベイクは保持)", command=lambda *_: self._call(self._remove))

    def _create(self):
        """選択した入力メッシュから新しいSolverを作る。"""
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        if len(selected) != 1:
            raise ValueError("入力メッシュを1個選択してください")
        self.refresh(api.create(selected[0]))

    def _select(self, attribute):
        """入力または出力メッシュを選択する。"""
        cmds.select(api.getConnection(self.solver, attribute), replace=True)

    def _set_selected(self):
        """入力または出力に属する頂点だけを受理してマップを更新する。"""
        selection = om.MGlobal.getActiveSelectionList()
        allowed = [api._mesh(api.getConnection(self.solver, attr)).node() for attr in ("sourceMesh", "outputMeshObject")]
        indices = []
        for index in range(selection.length()):
            path, component = selection.getComponent(index)
            if path.node() not in allowed or component.isNull() or component.apiType() != om.MFn.kMeshVertComponent:
                raise ValueError("このSolverの入力または出力メッシュの頂点を選択してください")
            indices.extend(om.MFnSingleIndexedComponent(component).getElements())
        api.setVertexWeights(self.solver, indices, cmds.floatSliderGrp(self.weight, query=True, value=True))

    def _add_collider(self):
        """必要なら選択Transformへ追従するコライダーを作成する。"""
        attach = None
        if cmds.checkBox(self.attach, query=True, value=True):
            selected = cmds.ls(selection=True, long=True, type="transform") or []
            if len(selected) != 1:
                raise ValueError("追従先Transform / Jointを1個選択してください")
            attach = selected[0]
        guide = api.addCollider(self.solver, cmds.optionMenu(self.kind, query=True, value=True), attachTo=attach)
        cmds.select(guide, replace=True)

    def _remove_collider(self):
        """選択した専用ガイドを登録解除して削除する。"""
        selected = cmds.ls(selection=True) or []
        if len(selected) != 1:
            raise ValueError("コライダーを1個選択してください")
        api.removeCollider(self.solver, selected[0])

    def _preset(self, save):
        """ユーザーが選択したJSONファイルへ設定を保存・読込する。"""
        paths = cmds.fileDialog2(fileMode=0 if save else 1, fileFilter="JSON (*.json)")
        if paths:
            (api.savePreset if save else api.loadPreset)(self.solver, paths[0])

    def _bake(self):
        """指定範囲をベイクして結果メッシュを選択する。"""
        start = cmds.intFieldGrp(self.range, query=True, value1=True)
        end = cmds.intFieldGrp(self.range, query=True, value2=True)
        cmds.select(api.bake(self.solver, start, end), replace=True)

    def _remove(self):
        """選択Solverのセットアップを削除して画面を更新する。"""
        api.remove(self.solver)
        self.solver = None
        self.refresh()


def show():
    """Simple Clothの設定ウィンドウを表示して参照を保持する。"""
    global _window
    _window = ClothWindow()
    return _window.window
