"""Maya上部のmlrig実行メニュー。"""

from maya import cmds, mel

from functools import partial
import mlib


class Menu:
    """仮の作成・編集メニューを同一セッションで一つだけ管理する。"""

    NAME = "mlrigMainMenu"

    @classmethod
    def install(cls):
        """GUIのメインメニューバーへ登録する。既存なら再利用する。

        Returns:
            str | None: メニュー名。バッチではNone。
        """
        if mlib.Environment.isBatch():
            return None
        if cmds.menu(cls.NAME, exists=True):
            return cls.NAME
        parent = mel.eval("$mlrigMainWindow = $gMainWindow")
        cmds.menu(cls.NAME, label="mlrig", parent=parent, tearOff=True)
        cmds.menuItem(
            label="レイヤーエディタを開く", parent=cls.NAME, command=partial(cls.run, "editor")
        )
        create = cmds.menuItem(label="サンプル作成", parent=cls.NAME, subMenu=True, tearOff=True)
        cmds.menuItem(label="公開チャンネルを編集", parent=cls.NAME, command=partial(cls.run, "publishedChannels"))
        cmds.menuItem(label="外部ポートを接続", parent=cls.NAME, command=partial(cls.run, "externalPorts"))
        cmds.menuItem(label="選択からユニットを探索", parent=cls.NAME, command=partial(cls.run, "unitInspector"))
        cmds.menuItem(label="回転合成の入力を確認", parent=cls.NAME, command=partial(cls.run, "rotationInspector"))
        cmds.menuItem(label="ローカル追従への変換を診断", parent=cls.NAME, command=partial(cls.run, "localFollow"))
        cmds.menuItem(label="ガイドの接地位置を調整", parent=cls.NAME, command=partial(cls.run, "guideGround"))
        cmds.menuItem(label="コントローラーのプロキシを作成", parent=cls.NAME, command=partial(cls.run, "controlProxy"))
        cmds.menuItem(label="プロキシの元コントローラーを選択", parent=cls.NAME, command=partial(cls.run, "proxySource"))
        cmds.menuItem(label="輪郭ピッカーを開く", parent=cls.NAME, command=partial(cls.run, "outlinePicker"))
        cmds.menuItem(label="補正に使うカメラを切り替え", parent=cls.NAME, command=partial(cls.run, "switchCorrectionCamera"))
        cmds.menuItem(label="視線の可動域を設定", parent=cls.NAME, command=partial(cls.run, "eyeLimit"))
        cmds.menuItem(label="チェーンのワールドロールを計測", parent=cls.NAME, command=partial(cls.run, "worldRoll"))
        cmds.menuItem(label="補正ターゲットの管理", parent=cls.NAME, command=partial(cls.run, "correctionTargets"))
        cmds.menuItem(label="サブリグの枝を複製", parent=cls.NAME, command=partial(cls.run, "branchUnit"))
        from .animalGuides import ITEMS

        animals = cmds.menuItem(label="非人型のガイドとFK骨", parent=cls.NAME, subMenu=True)
        for key, label in ITEMS:
            cmds.menuItem(label=label, parent=animals, command=partial(cls.run, "animal:" + key))
        cmds.menuItem(label="ガイドから骨を作成・更新", parent=animals, command=partial(cls.run, "animal:build"))
        cmds.menuItem(label="構築工程の拡張", parent=animals, command=partial(cls.run, "buildStages"))
        from .influenceModes import MODES

        influences = cmds.menuItem(label="補助骨の追従方式", parent=cls.NAME, subMenu=True)
        for key,label in MODES:
            cmds.menuItem(label=label,parent=influences,command=partial(cls.run,"influenceMode:"+key))
        layers = cmds.menuItem(label="骨格・制御レイヤーを編集", parent=cls.NAME, subMenu=True)
        for key, label in (("base","ベース骨を抽出"), ("bind","バインド骨を抽出"), ("control","制御を抽出"), ("merge","選択役割を統合")):
            cmds.menuItem(label=label, parent=layers, command=partial(cls.run, "editLayer:" + key))
        cmds.menuItem(label="局所変形の範囲", parent=cls.NAME, command=partial(cls.run, "localFalloff"))
        cmds.menuItem(label="IKの作成・差し替え診断", parent=cls.NAME, command=partial(cls.run, "ikComparison"))
        cmds.menuItem(label="4点追従ガイドを作成", parent=cls.NAME, command=partial(cls.run, "fourPoint"))
        cmds.menuItem(label="4点追従を現在姿勢で解除", parent=cls.NAME, command=partial(cls.run, "releaseFourPoint"))
        cmds.menuItem(label="ねじり・曲げの順で補助骨を作成", parent=cls.NAME, command=partial(cls.run, "twistBefore"))
        cmds.menuItem(label="曲げ・ねじりの順で補助骨を作成", parent=cls.NAME, command=partial(cls.run, "twistAfter"))
        cmds.menuItem(label="カーブでクラスターを駆動", parent=cls.NAME, command=partial(cls.run, "curveCluster"))
        cmds.menuItem(label="顔ユニットの変位測定", parent=cls.NAME, command=partial(cls.run, "faceProbe"))
        cmds.menuItem(label="片眼の設計骨を再構築", parent=cls.NAME, command=partial(cls.run, "eyeAssembly"))
        cmds.menuItem(label="選択した方向のコーンを追加", parent=cls.NAME, command=partial(cls.run, "addDirectionCone"))
        cmds.menuItem(label="選択した方向コーンを削除", parent=cls.NAME, command=partial(cls.run, "removeDirectionCone"))
        cmds.menuItem(label="スキン面の補正値を読む", parent=cls.NAME, command=partial(cls.run, "surface:sample"))
        cmds.menuItem(label="UV面追従ガイドを作成", parent=cls.NAME, command=partial(cls.run, "uvGuide"))
        cmds.menuItem(label="面追従を現在姿勢で再バインド", parent=cls.NAME, command=partial(cls.run, "uvRebind"))
        cmds.menuItem(label="スキン列から面追従クラスターを作成", parent=cls.NAME, command=partial(cls.run, "surfaceClusters"))
        cmds.menuItem(label="バインド方式を事前比較", parent=cls.NAME, command=partial(cls.run, "bindComparison"))
        cmds.menuItem(label="参照面と評価面の差分を接続", parent=cls.NAME, command=partial(cls.run, "surfaceDifference"))
        cmds.menuItem(label="2本のガイドでメッシュと小物を駆動", parent=cls.NAME, command=partial(cls.run, "guideRibbon"))
        cmds.menuItem(label="2D補正コントローラーを作成", parent=cls.NAME, command=partial(cls.run, "directionPad"))
        cmds.menuItem(label="カーブから平行な2列を作成", parent=cls.NAME, command=partial(cls.run, "parallelStrands"))
        cmds.menuItem(label="キャラクターの部位対応を確認", parent=cls.NAME, command=partial(cls.run, "characterMap"))
        cmds.menuItem(label="旧リグのワールド軌跡を転写", parent=cls.NAME, command=partial(cls.run, "worldMotion"))
        cmds.menuItem(label="旧出力と置換候補を比較", parent=cls.NAME, command=partial(cls.run, "migrationCompare"))
        cmds.menuItem(label="表示の配線と検査", parent=cls.NAME, command=partial(cls.run, "visibilitySwitch"))
        cmds.menuItem(label="選択順に仮想FKを作成", parent=cls.NAME, command=partial(cls.run, "virtualFk"))
        cmds.menuItem(label="評価後のカーブ長を保持", parent=cls.NAME, command=partial(cls.run, "keepCurveLength"))
        cmds.menuItem(label="折れ線に5点チェーンを作成", parent=cls.NAME, command=partial(cls.run, "polylineChain"))
        cmds.menuItem(label="子の姿勢を保って親骨のX軸を合わせる", parent=cls.NAME, command=partial(cls.run, "orientPair"))
        cmds.menuItem(label="選択面のウェイトで小物を追従", parent=cls.NAME, command=partial(cls.run, "surface:attach"))
        passive = cmds.menuItem(label="受動接続", parent=cls.NAME, subMenu=True)
        for op, label in (("create", "専用バッファに接続"), ("suppress", "現在姿勢で抑制"), ("resume", "追従を再開"), ("inspect", "接続状態を確認")):
            cmds.menuItem(label=label, parent=passive, command=partial(cls.run, "passive:" + op))
        poses = cmds.menuItem(label="選択骨の設計基準ポーズ", parent=cls.NAME, subMenu=True)
        for action, label in (("save", "現在値を記録"), ("restore", "基準値に復帰"), ("delete", "記録を削除")):
            cmds.menuItem(label=label, parent=poses, command=partial(cls.run, "basePose:" + action))
        representations = cmds.menuItem(label="形状の役割を切り替え", parent=cls.NAME, subMenu=True)
        wheels = cmds.menuItem(label="車輪のベース骨", parent=cls.NAME, subMenu=True)
        cmds.menuItem(label="選択車輪に骨を追加", parent=wheels, command=partial(cls.run, "wheelBone"))
        cmds.menuItem(label="選択車輪の未使用骨を削除", parent=wheels, command=partial(cls.run, "removeWheelBone"))
        for action, label in (("register", "選択した3形状を登録"), ("block", "ブロックを表示"), ("bind", "バインドを表示"), ("render", "レンダーを表示")):
            cmds.menuItem(label=label, parent=representations, command=partial(cls.run, "geometry:" + action))
        for kind, label in (
            ("limb", "腕・脚 FK / IK"),
            ("demo", "メッシュ付き腕・脚"),
            ("finger", "指 Curl / Spread"),
            ("aim", "首・視線 Aim"),
            ("spine", "背骨 Spline IK"),
            ("tail", "尻尾 Spline IK"),
            ("skirt", "スカート 4方向"),
        ):
            cmds.menuItem(label=label, parent=create, command=partial(cls.run, kind))
        from .setupSamples import SetupSamples

        setups = cmds.menuItem(label="Setup Samples", parent=cls.NAME, subMenu=True, tearOff=True)
        for kind, label in SetupSamples.ITEMS:
            cmds.menuItem(label=label, parent=setups, command=partial(cls.run, "setup:" + kind))
        cmds.menuItem(divider=True, parent=cls.NAME)
        cmds.menuItem(
            label="選択スカートのポーズ補正を編集",
            parent=cls.NAME,
            command=partial(cls.run, "pose"),
        )
        cmds.menuItem(
            label="選択骨へ局所Tweakを追加", parent=cls.NAME, command=partial(cls.run, "tweak")
        )
        cmds.menuItem(label="プレビューリグの接続経路", parent=cls.NAME, command=partial(cls.run, "previewRoutes"))
        cmds.menuItem(label="部位別ブロックを生成", parent=cls.NAME, command=partial(cls.run, "blockGeometry"))
        cmds.menuItem(label="補正ターゲットの所属と共有", parent=cls.NAME, command=partial(cls.run, "correctionOwnership"))
        cmds.menuItem(label="面追従クラスタの再バインド", parent=cls.NAME, command=partial(cls.run, "clusterRebind"))
        cmds.menuItem(label="サブリグ部品の保存・読込", parent=cls.NAME, command=partial(cls.run, "branchLibrary"))
        cmds.menuItem(label="ガイドと形状の編集", parent=cls.NAME, command=partial(cls.run, "guideEdit"))
        cmds.menuItem(label="スキン分布の補正先", parent=cls.NAME, command=partial(cls.run, "skinDriverTargets"))
        return cls.NAME

    @staticmethod
    def selected_rig():
        """選択ノードの祖先からモジュールを解決する。

        Returns:
            tuple: モジュールと元の選択ノード名。

        Raises:
            ValueError: 選択がモジュールに所属しない場合。
        """
        from .moduleRegistry import ModuleRegistry

        selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)] or []
        if not selected:
            raise ValueError("mlrigのモジュールまたは配下のノードを選択してください")
        for root in ModuleRegistry.roots():
            rig = ModuleRegistry.get(root)
            path = rig.root.getName(full=True)
            if selected[0] == path or selected[0].startswith(path + "|"):
                return rig, selected[0]
        raise ValueError("選択ノードはmlrigモジュールに所属していません")

    @classmethod
    def run(cls, action, *unused):
        """メニューを実行し、構築したモジュールをレイヤーUIへ表示する。

        Args:
            action (str): メニュー操作ID。``"setup:<種類>"`` はセットアップのサンプルを作り、
                動かす対象を選択する(レイヤーエディタは開かない)。
            *unused: Maya UIコールバックの引数。

        Returns:
            object | None: 作成結果。失敗時はMayaへ警告を表示。
        """
        from . import show_layer_editor, build_spline, build_skirt
        from .sampleBuilder import SampleBuilder

        try:
            if action == "previewRoutes":
                from .previewRoutes import show
                return show()
            if action == "blockGeometry":
                from .blockGeometry import show
                return show()
            if action == "correctionOwnership":
                from .correctionTargets import showOwnership
                return showOwnership()
            if action == "clusterRebind":
                from .surfaceClusters import showRebind
                return showRebind()
            if action == "branchLibrary":
                from .branchUnit import showLibrary
                return showLibrary()
            if action == "guideEdit":
                from .guideEdit import show
                return show()
            if action == "skinDriverTargets":
                from .skinDriverTargets import show
                return show()
            if action == "uvRebind":
                from .surfaceGuide import showRebind

                return showRebind()
            if action == "migrationCompare":
                from .migrationCompare import show

                return show()
            if action.startswith("influenceMode:"):
                from .influenceModes import create

                return create([item.getName(full=True) for item in mlib.ls(selection=True,long=True)],action.split(":")[1])
            if action == "buildStages":
                from .buildStages import show

                return show()
            if action == "ikComparison":
                from .ikComparison import show

                return show()
            if action.startswith("animal:"):
                from . import animalGuides

                kind = action.split(":")[1]
                if kind == "build":
                    nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                    if len(nodes) != 1:
                        raise ValueError("プリセットのルートを選択してください")
                    return animalGuides.build(nodes[0])
                return animalGuides.create(kind)
            if action == "eyeAssembly":
                from .eyeAssembly import show

                return show()
            if action.startswith("editLayer:"):
                from . import layerExtract

                key = action.split(":")[1]
                nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                return layerExtract.merge(nodes) if key == "merge" else layerExtract.extract(nodes, key)
            if action in ("twistBefore", "twistAfter"):
                from .twistInfluence import create

                joints = mlib.ls(selection=True, long=True, type="joint").getNames(full=True)
                if len(joints) != 1:
                    raise ValueError("親のあるジョイントを1個選択してください")
                return create(joints[0], action == "twistBefore")
            if action in ("fourPoint", "releaseFourPoint"):
                from . import fourPointGuide

                nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if action == "releaseFourPoint" and len(nodes) == 1:
                    return fourPointGuide.release(nodes[0])
                if action == "fourPoint" and len(nodes) in (4, 5):
                    return fourPointGuide.create(nodes[:4], nodes[4] if len(nodes) == 5 else None)
                raise ValueError("作成は4点と任意の親、解除はガイド1つを選択してください")
            if action == "guideRibbon":
                from .guideRibbon import bind

                nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if len(nodes) < 3:
                    raise ValueError("カーブ2本、メッシュ、必要な小物の順に選択してください")
                return bind(*nodes[:3], nodes[3:])
            if action == "surfaceDifference":
                from .bindComparison import bindSurfaceDifference

                nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if len(nodes) != 3:
                    raise ValueError("参照面、評価面、宛先を順に選択してください")
                return bindSurfaceDifference(*nodes)
            if action in ("addDirectionCone", "removeDirectionCone"):
                from . import directionCones

                nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if action == "removeDirectionCone":
                    return directionCones.remove(nodes)
                if len(nodes) != 2:
                    raise ValueError("ドライバーと方向を指定するトランスフォームを順に選択してください")
                return directionCones.add(*nodes)
            if action == "correctionTargets":
                from .correctionTargets import show

                return show()
            if action == "branchUnit":
                from .branchUnit import show

                return show()
            if action == "localFalloff":
                from .localFalloff import show

                return show()
            if action == "curveCluster":
                from .curveCluster import show

                return show()
            if action == "faceProbe":
                from .faceProbe import show

                return show()
            if action in ("keepCurveLength", "polylineChain"):
                from . import curveLengthTools

                selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if len(selected) != 1:
                    raise ValueError("カーブを1本選択してください")
                return curveLengthTools.keepLength(selected[0]) if action == "keepCurveLength" else curveLengthTools.polylineChain(selected[0])
            if action == "virtualFk":
                from .virtualFk import create

                return create(mlib.ls(selection=True, long=True, transforms=True).getNames(full=True))
            if action == "surfaceClusters":
                from .surfaceClusters import show

                return show()
            if action == "visibilitySwitch":
                from .visibilitySwitch import show

                return show()
            if action == "worldMotion":
                from .worldMotion import show

                return show()
            if action == "characterMap":
                from .characterMap import show

                return show()
            if action == "parallelStrands":
                from .parallelStrands import show

                return show()
            if action == "orientPair":
                from .setups.jointHierarchy import JointHierarchy

                joints = mlib.ls(selection=True, long=True, type="joint").getNames(full=True)
                if len(joints) != 1:
                    raise ValueError("親骨を1つ選択してください")
                return JointHierarchy.orientPair(joints[0])
            if action == "directionPad":
                from .directionPad import create

                return create()
            if action == "uvGuide":
                from .surfaceGuide import show

                return show()
            if action == "bindComparison":
                from .bindComparison import show

                return show()
            if action.startswith("surface:"):
                from .skinSurface import run

                return run(action.split(":", 1)[1])
            if action.startswith("passive:"):
                from .passiveFollow import run

                return run(action.split(":", 1)[1])
            if action == "worldRoll":
                from .worldRoll import show

                return show()
            if action == "eyeLimit":
                from .setups.asymmetricSwingLimit import AsymmetricSwingLimit

                return AsymmetricSwingLimit.createEyeOutput()
            if action == "switchCorrectionCamera":
                from .setups.cameraAngleReader import CameraAngleReader

                selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                if len(selected) != 2:
                    raise ValueError("補正のコンテナ、カメラの順に選択してください")
                CameraAngleReader(selected[0]).setCamera(selected[1])
                return selected[1]
            if action in ("wheelBone", "removeWheelBone"):
                from .wheelSkeleton import edit

                return edit(remove=action == "removeWheelBone")
            if action.startswith("geometry:"):
                from . import geometryRoles

                selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
                role = action.split(":", 1)[1]
                if role == "register":
                    return geometryRoles.register(selected)
                if len(selected) != 1:
                    raise ValueError("登録した形状グループを1つ選択してください")
                return geometryRoles.switch(selected[0], role)
            if action.startswith("basePose:"):
                from .basePose import apply

                return apply(action.split(":", 1)[1])
            if action == "outlinePicker":
                from .outlinePicker import show

                return show()
            if action in ("controlProxy", "proxySource"):
                from . import controlProxy

                return controlProxy.run(action)
            if action == "localFollow":
                from .followInspection import show

                return show()
            if action == "guideGround":
                from .guideGround import show

                return show()
            if action == "rotationInspector":
                from .rotationInspector import show

                return show()
            if action == "unitInspector":
                from .moduleRegistry import ModuleRegistry

                return ModuleRegistry.showInspector()
            if action == "externalPorts":
                from .publishedChannels import showExternalPorts

                return showExternalPorts()
            if action == "publishedChannels":
                from .publishedChannels import showEditor

                return showEditor()
            if action.startswith("setup:"):
                from .setupSamples import SetupSamples

                sample = SetupSamples.build(action.split(":", 1)[1])
                mlib.select(sample.target, replace=True)
                return sample
            if action == "editor":
                return show_layer_editor()
            if action == "pose":
                from .skirtRig import SkirtRig

                rig, _ = cls.selected_rig()
                if not isinstance(rig, SkirtRig):
                    raise ValueError("スカートモジュールを選択してください")
                from .poseEditor import PoseEditor

                editor = show_layer_editor()
                editor._pose_editor = PoseEditor(rig, parent=editor)
                editor._pose_editor.show()
                return editor._pose_editor
            if action == "tweak":
                from .tweakLayer import TweakLayer

                rig, joint = cls.selected_rig()
                layer = TweakLayer(rig)
                return layer.add(SampleBuilder.next_id(set(layer.groups()), "tweak"), joint)
            name = SampleBuilder.next_id(set([item.getName() for item in mlib.ls()]), action)
            if action in ("limb", "demo"):
                rig = SampleBuilder.module(name, demo=action == "demo")
            elif action in ("spine", "tail"):
                rig = build_spline(name, axis="y" if action == "spine" else "z")
            elif action == "skirt":
                rig = build_skirt(name)
            elif action == "finger":
                from .fingerRig import FingerRig

                rig = FingerRig.create(name)
            elif action == "aim":
                from .aimRig import AimRig

                rig = AimRig.create(name)
            else:
                raise ValueError("Unknown menu action")

            mlib.select(rig.root, replace=True)
            editor = show_layer_editor()
            editor.refresh()
            from .layerEditor import QtCore

            for row in editor.rows():
                data = row.data(0, QtCore.Qt.UserRole)
                if data["root"] == rig.root.getUuid() and data["role"] == "module":
                    editor.tree.setCurrentItem(row)
                    break
            return rig
        except Exception as error:
            mlib.logger.warning("mlrig: " + str(error))
            return None

    @classmethod
    def remove(cls):
        """自身のメニューだけを削除する。"""
        if not mlib.Environment.isBatch() and cmds.menu(cls.NAME, exists=True):
            cmds.deleteUI(cls.NAME, menu=True)
