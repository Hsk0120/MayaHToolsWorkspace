"""主な操作を Maya の runTimeCommand として登録し、Hotkey Editor から割り当てられるようにする。

登録するのはコマンドの名前と処理だけで、キーの割り当ては行わない(利用者の設定を書き換えない)。
"""

import maya.cmds as cmds

#: runTimeCommand のカテゴリ名。
CATEGORY = "Custom Scripts.Anim Bar"

#: (コマンド名, 説明, 実行する Python)。
COMMANDS = (
    ("AnimBarTween50", "Tween halfway between the previous and next keys",
     "from animBar.core import tween; tween.tween(0.5)"),
    ("AnimBarTweenPrevious", "Copy the previous key", "from animBar.core import tween; tween.copyNeighborKey(-1)"),
    ("AnimBarTweenNext", "Copy the next key", "from animBar.core import tween; tween.copyNeighborKey(1)"),
    ("AnimBarNudgeLeft", "Move keys one frame earlier", "from animBar.core import timing; timing.nudgeKeys(-1)"),
    ("AnimBarNudgeRight", "Move keys one frame later", "from animBar.core import timing; timing.nudgeKeys(1)"),
    ("AnimBarInsertFrame", "Insert a frame after the current time",
     "from animBar.core import timing; timing.insertFrames(1)"),
    ("AnimBarRemoveFrame", "Remove a frame after the current time",
     "from animBar.core import timing; timing.insertFrames(-1)"),
    ("AnimBarResetValues", "Reset the selected channels to their defaults",
     "from animBar.core import timing; timing.resetValues()"),
    ("AnimBarMirrorPose", "Mirror the selected pose to the opposite side",
     "from animBar.core import mirror; mirror.mirrorPose(mode='mirror')"),
    ("AnimBarFlipPose", "Swap the poses of both sides", "from animBar.core import mirror; mirror.mirrorPose(mode='flip')"),
    ("AnimBarJumpPreviousKey", "Jump to the previous key", "from animBar.core import timeline; timeline.jumpToKey(-1)"),
    ("AnimBarJumpNextKey", "Jump to the next key", "from animBar.core import timeline; timeline.jumpToKey(1)"),
    ("AnimBarFrameKeys", "Set the playback range to the selected keys",
     "from animBar.core import timeline; timeline.frameSelectedKeys()"),
    ("AnimBarToggleBar", "Show or hide the Anim Bar", "import animBar; animBar.toggle()"),
)


def register():
    """runTimeCommand を登録する(登録済みなら処理を置き換える)。

    Returns:
        list[str]: 登録したコマンド名。
    """
    # mlib には runTimeCommand の入口が無いため、Mayaのコマンドを使う。
    names = []
    for name, annotation, code in COMMANDS:
        if cmds.runTimeCommand(name, exists=True):
            cmds.runTimeCommand(name, edit=True, command=code, annotation=annotation, commandLanguage="python")
        else:
            cmds.runTimeCommand(name, category=CATEGORY, command=code, annotation=annotation,
                                commandLanguage="python", default=False)
        names.append(name)
    return names
