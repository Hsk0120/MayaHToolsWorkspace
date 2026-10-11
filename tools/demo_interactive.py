"""検証デモを録画せず、タイムラインの操作で確認できるようにする補助。

各デモの evaluate(frame) を、時間が変わるたびに呼んでHUDと検査値を更新する。
scriptJob はデモのウィンドウに親子付けし、ウィンドウを閉じると自動で消える。
"""

from maya import cmds

# 尻尾回避デモのウィンドウと、デモが作るHUD名の接頭辞。
DEMO_WINDOWS = ("sweepCompareWindow", "sideKeepWindow", "coneSoftWindow", "rbfPoseWindow", "chainRbfWindow",
               "coneReaderDemoWindow", "coneRbfWindow")
DEMO_HUD_PREFIXES = ("sweepTop", "sweepBottom", "keepTop", "keepBottom", "coneTop", "coneBottom",
                     "rbfTop", "rbfBottom", "chainTop", "chainBottom", "coneRbfTop", "coneRbfBottom")


# ウィンドウ名 → HUDを元に戻す関数。uiDeleted の scriptJob は遅れて動くことがあるので、
# 次のデモを作る前にここから直接戻す。importlib.reload しても登録を引き継ぐ。
_restores = globals().get("_restores", {})


def restoreHuds():
    """退避中のHUDをすべて元に戻す。"""
    for window in list(_restores):
        _restores.pop(window)()


def closeDemoWindows():
    """開いているデモのウィンドウを閉じ、退避したHUDを元に戻す。"""
    restoreHuds()
    for window in DEMO_WINDOWS:
        if cmds.window(window, exists=True):
            cmds.deleteUI(window, window=True)


def setTime(frame):
    """0始まりのフレーム番号へ時間を合わせる。同じ時間なら設定しない。

    タイムライン操作から呼ばれた evaluate が時間を設定し直して、
    timeChanged が連鎖しないようにする。
    """
    if cmds.currentTime(query=True) != frame+1:
        cmds.currentTime(frame+1)


def attachInteractive(window, count, evaluate, states=()):
    """時間の変化でデモの evaluate を呼び、HUDを更新し続ける。

    Args:
        window (str): デモのウィンドウ。閉じると scriptJob も消える。
        count (int): フレーム数。範囲外の時間は端のフレームとして扱う。
        evaluate (callable): 0始まりのフレーム番号を受け取るデモの検査関数。
        states (iterable[tuple[dict, object]]): 前フレームとの差などの状態と、
            連続しないフレームへ移ったときに戻す値の組。
    """
    previous = [None]

    def update():
        """現在の時間に対応するフレームを評価する。"""
        frame = int(round(cmds.currentTime(query=True)))-1
        frame = max(0, min(count-1, frame))
        if previous[0] is None or frame != previous[0]+1:
            # スクラブで飛んだときは、前フレームとの差を大きな変化と誤表示しない。
            for state, value in states:
                for key in state:
                    state[key] = value
        previous[0] = frame
        evaluate(frame)

    cmds.scriptJob(event=["timeChanged", update], parent=window)
    cmds.currentTime(1)
    update()


def clearHuds(window):
    """既存のHUDを退避して非表示にし、デモのウィンドウを閉じたら元に戻す。

    HUDは区画(section)と段(block)の組が重なると作れないので、既存のものは
    使わない段へ移して隠す。ウィンドウを閉じたときにデモが作ったHUDを消し、
    退避したHUDの区画・段・表示状態を戻す。

    Args:
        window (str): デモのウィンドウ。
    """
    restoreHuds()
    # 以前の実行で残ったデモのHUDは、退避せずに消す。
    for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if hud.startswith(DEMO_HUD_PREFIXES):
            cmds.headsUpDisplay(hud, remove=True)
    saved = []
    for index, hud in enumerate(cmds.headsUpDisplay(listHeadsUpDisplays=True) or []):
        saved.append((hud, cmds.headsUpDisplay(hud, query=True, section=True),
                      cmds.headsUpDisplay(hud, query=True, block=True),
                      cmds.headsUpDisplay(hud, query=True, visible=True)))
        cmds.headsUpDisplay(hud, edit=True, visible=False, block=100+index)
    names = {item[0] for item in saved}
    done = [False]

    def restore():
        """デモのHUDを消し、退避したHUDを元の区画・段・表示へ戻す。一度だけ動く。"""
        if done[0]:
            return
        done[0] = True
        _restores.pop(window, None)
        for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
            if hud not in names:
                cmds.headsUpDisplay(hud, remove=True)
        for hud, section, block, visible in saved:
            if cmds.headsUpDisplay(hud, exists=True):
                cmds.headsUpDisplay(hud, edit=True, section=section, block=block, visible=visible)

    _restores[window] = restore
    cmds.scriptJob(uiDeleted=[window, restore], runOnce=True)
