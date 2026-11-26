"""AnimBarのキー編集設定をユーザー設定へ保存する。"""

import json
import math

import maya.cmds as cmds

from . import keyTransform


_OPTION = "animBarKeyEditPresets"


def presets():
    """登録名とキー編集設定を取得する。"""
    if not cmds.optionVar(exists=_OPTION):
        return {}
    return json.loads(cmds.optionVar(query=_OPTION))


def save(name, mode, amount, seed=0):
    """編集モード・量・ノイズシードを保存する。"""
    if not name.strip() or mode not in dict(keyTransform.MODES) or not math.isfinite(amount):
        raise ValueError("Enter a preset name, an existing mode and a finite amount.")
    if not isinstance(seed, int):
        raise TypeError("Seed must be an integer.")
    data = presets()
    data[name] = dict(mode=mode, amount=amount, seed=seed)
    cmds.optionVar(stringValue=(_OPTION, json.dumps(data)))


def apply(name):
    """現在選択中のキーへ登録済みの編集を実行する。"""
    return keyTransform.applyKeyTransform(**presets()[name])


def remove(name):
    """登録を解除する。"""
    data = presets()
    del data[name]
    cmds.optionVar(stringValue=(_OPTION, json.dumps(data)))
