"""ワークスペース内のC++プラグインが、Mayaの「信頼済みプラグインの場所」に登録済みか確認する(読み取り専用)。

Mayaは初回ロード時に、信頼されていない場所のプラグインで警告ダイアログを出し、GUI(と、
commandPort経由の送信実行)が止まる。事前に未登録の場所を確認しておくことで、作業中に突然止まるのを防ぐ。

信頼済みの場所の変更は、Maya自身がスクリプトからの変更を拒否する仕組み(SafeMode)のため、
このツールは登録を行わない。登録は Preferences > Security > Plug-ins の
「My trusted plugin locations」で「Add」するか、ロード時の警告ダイアログで
「Apply to all plugins in this location」にチェックして「Allow」する(どちらも1回だけでよい)。
"""

import os
from pathlib import Path

import maya.cmds as cmds

TRUSTED_OPTION_VAR = "SafeModeAllowedlistPaths"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
# 対象は自作リポジトリ(inhouse配下)のみ。external配下の第三者プラグインは判断をユーザーに委ねる。
SCAN_ROOT = WORKSPACE_ROOT / "maya" / "inhouse"


def _normalize(path):
    """str: 比較用の正規化(スラッシュ統一・大文字小文字無視)。"""
    return os.path.normpath(str(path)).replace("\\", "/").rstrip("/").lower()


def workspace_plugin_locations(plug_in_path=None, root=SCAN_ROOT):
    """list[str]: root 配下にあり、.mll を含む MAYA_PLUG_IN_PATH のフォルダ(Mayaの表記に合わせたスラッシュ区切り)。"""
    if plug_in_path is None:
        plug_in_path = os.environ.get("MAYA_PLUG_IN_PATH", "")
    root_key = _normalize(root)
    found = []
    for entry in plug_in_path.split(os.pathsep):
        if not entry:
            continue
        path = Path(entry)
        key = _normalize(path)
        if path.is_dir() and (key == root_key or key.startswith(root_key + "/")) and any(path.glob("*.mll")):
            text = str(path).replace("\\", "/")
            if text not in found:
                found.append(text)
    return found


def trusted_locations(option_var=TRUSTED_OPTION_VAR):
    """list[str]: 現在登録済みの信頼済みプラグインの場所。"""
    if not cmds.optionVar(exists=option_var):
        return []
    value = cmds.optionVar(query=option_var)
    return list(value) if isinstance(value, (list, tuple)) else [value]


def untrusted(locations, option_var=TRUSTED_OPTION_VAR):
    """list[str]: locations のうち、まだ登録されていないもの。"""
    registered = {_normalize(p) for p in trusted_locations(option_var)}
    return [p for p in locations if _normalize(p) not in registered]


def run():
    """未登録の場所を確認して表示する。GUIでは Preferences を開くボタンも出す。"""
    pending = untrusted(workspace_plugin_locations())
    if not pending:
        print("# ワークスペース内のプラグインの場所は、全て信頼済みに登録されています。")
        return []
    message = ("次のプラグインの場所は、まだ信頼済みに登録されていません。\n"
               "初回ロード時に警告ダイアログが出て、Mayaが止まります。\n\n"
               + "\n".join(pending)
               + "\n\nPreferences > Security > Plug-ins の「My trusted plugin locations」へ追加するか、\n"
               "警告ダイアログで「Apply to all plugins in this location」にチェックして Allow してください。")
    print("# " + message.replace("\n", "\n# "))
    if not cmds.about(batch=True):
        answer = cmds.confirmDialog(title="信頼済みプラグインの場所", message=message,
                                    button=["Preferencesを開く", "閉じる"], defaultButton="閉じる",
                                    cancelButton="閉じる", dismissString="閉じる")
        if answer == "Preferencesを開く":
            import maya.mel as mel
            mel.eval("PreferencesWindow")
    return pending


if __name__ == "__main__":
    run()
