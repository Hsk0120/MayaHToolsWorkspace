"""主な操作を Maya の runTimeCommand として登録し、Hotkey Editor から割り当てられるようにする。

登録するのはコマンドの名前と処理だけで、キーの割り当ては行わない(利用者の設定を書き換えない)。
"""

import maya.cmds as cmds

#: runTimeCommand のカテゴリ名。
CATEGORY = "Custom Scripts.Skin Weight Kit"

#: (コマンド名, 説明, 実行する Python)。
COMMANDS = (
    ("SkinWeightKitTogglePanel", "Show or hide the Skin Weight Kit panel",
     "import skinWeightKit; skinWeightKit.toggle()"),
    ("SkinWeightKitValueMenu", "Show the weight value menu at the mouse cursor",
     "from skinWeightKit.ui import popup; popup.showValueMenu()"),
    ("SkinWeightKitHammer", "Hammer the selected vertices",
     "from skinWeightKit.core import target, weights; weights.hammer(target.require())"),
    ("SkinWeightKitCopyWeights", "Copy the weights of the selected vertex",
     "from skinWeightKit.core import target, weights; weights.copy(target.require())"),
    ("SkinWeightKitPasteWeights", "Paste the copied weights onto the selected vertices",
     "from skinWeightKit.core import target, weights; weights.paste(target.require())"),
    ("SkinWeightKitGrowSelection", "Grow the vertex selection",
     "from skinWeightKit.core import selectionTools, target; selectionTools.grow(target.require())"),
    ("SkinWeightKitShrinkSelection", "Shrink the vertex selection",
     "from skinWeightKit.core import selectionTools, target; selectionTools.shrink(target.require())"),
    ("SkinWeightKitSelectLoop", "Select the edge loops of the selected edges",
     "from skinWeightKit.core import selectionTools; selectionTools.selectLoop()"),
    ("SkinWeightKitSelectRing", "Select the edge rings of the selected edges",
     "from skinWeightKit.core import selectionTools; selectionTools.selectRing()"),
    ("SkinWeightKitHoldWeights", "Remember the weights of the selected skinned mesh",
     "from skinWeightKit.core import hold, target; hold.hold(target.require())"),
    ("SkinWeightKitFetchWeights", "Restore the weights remembered by Hold",
     "from skinWeightKit.core import hold, target; hold.fetch(target.require())"),
    ("SkinWeightKitSmoothBrush", "Paint with the Skin Weight Kit smooth brush",
     "from skinWeightKit.ui import commands; commands.brush('smooth')"),
    ("SkinWeightKitSharpenBrush", "Paint with the Skin Weight Kit sharpen brush",
     "from skinWeightKit.ui import commands; commands.brush('sharpen')"),
)


def brush(mode):
    """ブラシのツールにする(パネルが開いていればその設定を使い、無ければ Uniform のスムーズの既定値を使う)。

    Args:
        mode (str): ブラシの種類(``"smooth"``・``"sharpen"`` 等)。

    Returns:
        str: ペイントのコンテキストの名前。
    """
    # 画面の部品は、ホットキーから呼ばれたときだけ必要なので呼出し時に読み込む。
    from . import paint, panel
    owner = panel._panel["widget"]
    if owner is not None:
        owner.brush_mode = mode
        return paint.start(owner._paint_settings)
    return paint.start(lambda: {"mode": mode, "method": "uniform", "radius": 0.0, "keepMax": False})


def register():
    """runTimeCommand を登録する(登録済みなら処理を置き換える)。

    Returns:
        list[str]: 登録したコマンド名。
    """
    # mlib には runTimeCommand の入口が無い(汎用UIは本体に入れない方針)ため、Mayaのコマンドを使う。
    names = []
    for name, annotation, code in COMMANDS:
        if cmds.runTimeCommand(name, exists=True):
            cmds.runTimeCommand(name, edit=True, command=code, annotation=annotation, commandLanguage="python")
        else:
            cmds.runTimeCommand(name, category=CATEGORY, command=code, annotation=annotation,
                                commandLanguage="python", default=False)
        names.append(name)
    return names
