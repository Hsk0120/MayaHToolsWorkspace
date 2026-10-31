"""選んだキーの値を、スライダーの量に応じて目標へ近づける・押し出す・揺らす。

スライダーの量 amount は -1〜1 を基本とする(範囲外は行き過ぎ)。各モードの意味は次のとおり。

- ``blendToNeighbors``: 正は後ろのキー、負は前のキーへ近づける。
- ``blendToDefault``: アトリビュートの既定値へ近づける(負は反対へ押し出す)。
- ``blendToFrame``: 記録した左右の時刻の値へ近づける(負は左、正は右)。
- ``blendToMirror``: 反対側のコントロールの同じ時刻の値へ近づける。
- ``pushPull``: 前後のキーを結ぶ直線から離す(正)・近づける(負)。
- ``easeInOut``: 選んだ範囲の両端を保ち、間をイーズの曲線に沿わせる(正はイーズイン、負はイーズアウト)。
- ``noise``: 乱数で揺らす(量は揺れ幅)。

スライダーをドラッグする間は、開始時の値を基準に計算し直す(:class:`KeySession`)。
"""

import math
import random

from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys, mirror

#: モードの名前と、バーに出す短い表示名。
MODES = (
    ("blendToNeighbors", "Neighbors"),
    ("blendToDefault", "Default"),
    ("blendToFrame", "Frame"),
    ("blendToMirror", "Mirror"),
    ("pushPull", "Push"),
    ("easeInOut", "Ease"),
    ("noise", "Noise"),
)

#: blendToFrame で使う左右の時刻。None は未記録。
_frames = {"left": None, "right": None}


def setBlendFrame(side, frame=None):
    """blendToFrame の基準の時刻を記録する。

    Args:
        side (str): ``"left"`` または ``"right"``。
        frame (float | None): 時刻。Noneは現在時刻。

    Returns:
        float: 記録した時刻。
    """
    if side not in _frames:
        raise ValueError("side must be 'left' or 'right'")
    _frames[side] = Time.getCurrent() if frame is None else float(frame)
    return _frames[side]


def getBlendFrame(side):
    """blendToFrame の基準の時刻を返す。

    Args:
        side (str): ``"left"`` または ``"right"``。

    Returns:
        float | None: 記録した時刻。未記録ならNone。
    """
    return _frames[side]


class KeySession:
    """スライダーのドラッグの間、開始時の値を保ち、量を変えるたびに計算し直す。

    Args:
        mode (str): :data:`MODES` のモード名。
        seed (int): noise の乱数のシード(同じドラッグの間は同じ揺れ方にする)。
    """

    def __init__(self, mode, seed=0):
        if mode not in dict(MODES):
            raise ValueError("Unknown key transform mode: " + str(mode))
        self.mode = mode
        # 現在時刻にキーが無いアニメーションには、カーブの形を変えずにキーを足してから変える(aTools と同じ)。
        self.targets = keys.targets(create="animated")
        self.original = [(target, [keys.keyValue(target.curve, index) for index in target.indices])
                         for target in self.targets]
        rng = random.Random(seed)
        self.noise = [[rng.uniform(-1, 1) for _ in target.indices] for target in self.targets]
        self.goals = [self._goals(target) for target in self.targets]
        self.times = [[target.curve.getKeyInputs()[index] for index in target.indices] for target in self.targets]

    def apply(self, amount):
        """量に応じて、開始時の値から計算したキーの値を書く。

        Args:
            amount (float): スライダーの量(-1〜1、範囲外は行き過ぎ)。

        Returns:
            int: 値を書いたキーの数。
        """
        amount = float(amount)
        count = 0
        for (target, values), goals, noise, times in zip(self.original, self.goals, self.noise, self.times):
            for position, (index, value) in enumerate(zip(target.indices, values)):
                result = self._value(value, goals[position], amount, noise[position], position, values, times)
                if result is not None:
                    keys.setKeyValue(target.curve, index, result)
                    count += 1
        return count

    def _goals(self, target):
        """キーごとに、モードの目標の値を前もって求める。

        Args:
            target (Target): 対象。

        Returns:
            list: キーごとの目標。モードにより (前, 後ろ) の組や数値。求められなければNone。
        """
        curve, inputs, values = target.curve, target.curve.getKeyInputs(), target.curve.getKeyValues()
        chosen = set(target.indices)
        goals = []
        for index in target.indices:
            previous = index - 1
            while previous in chosen:
                previous -= 1
            following = index + 1
            while following in chosen:
                following += 1
            neighbors = (values[previous] if previous >= 0 else None,
                         values[following] if following < len(values) else None)
            if self.mode == "blendToNeighbors":
                goals.append(neighbors)
            elif self.mode == "pushPull":
                if None in neighbors:
                    goals.append(None)
                else:
                    span = inputs[following] - inputs[previous]
                    ratio = (inputs[index] - inputs[previous]) / span if span else 0.5
                    goals.append(neighbors[0] + (neighbors[1] - neighbors[0]) * ratio)
            elif self.mode == "blendToDefault":
                goals.append(keys.defaultValue(target.plug))
            elif self.mode == "blendToFrame":
                left, right = _frames["left"], _frames["right"]
                goals.append((None if left is None else curve.evaluate(left),
                              None if right is None else curve.evaluate(right)))
            elif self.mode == "blendToMirror":
                goals.append(mirror.mirroredValue(target.plug, inputs[index]))
            else:
                goals.append(None)
        return goals

    def _value(self, value, goal, amount, noise, position, values, times):
        """1つのキーの新しい値を求める。

        Args:
            value (float): 開始時の値。
            goal (object): :meth:`_goals` の目標。
            amount (float): 量。
            noise (float): -1〜1 の乱数。
            position (int): 選んだキーの中での位置。
            values (list[float]): 選んだキーの開始時の値。
            times (list[float]): 選んだキーの時刻。

        Returns:
            float | None: 新しい値。変えない場合はNone。
        """
        if self.mode in ("blendToNeighbors", "blendToFrame"):
            side = goal[1] if amount >= 0 else goal[0]
            return None if side is None else value + (side - value) * abs(amount)
        if self.mode in ("blendToDefault", "blendToMirror"):
            return None if goal is None else value + (goal - value) * amount
        if self.mode == "pushPull":
            return None if goal is None else value + (value - goal) * amount
        if self.mode == "noise":
            spread = max(values) - min(values) if len(values) > 1 else 0.0
            return value + noise * amount * (spread if spread > 1e-9 else 1.0)
        if self.mode == "easeInOut":
            if len(values) < 3 or position in (0, len(values) - 1):
                return None
            start, end = values[0], values[-1]
            # キーの間隔が不均等でも形が崩れないよう、番号ではなく時刻の比率を使う。
            span = times[-1] - times[0]
            t = (times[position] - times[0]) / span if span else position / float(len(values) - 1)
            # 正はゆっくり始まる(イーズイン)、負はゆっくり終わる(イーズアウト)3次の曲線へ寄せる。
            shaped = t ** 3 if amount >= 0 else 1 - (1 - t) ** 3
            target = start + (end - start) * shaped
            return value + (target - value) * min(abs(amount), 1.0)
        return None


@undoChunk("animBarKeyTransform")
def applyKeyTransform(mode, amount, seed=0):
    """1回でキーの変形を行う(スライダーを使わない操作やスクリプト用)。

    Args:
        mode (str): モード名。
        amount (float): 量。
        seed (int): noise の乱数のシード。

    Returns:
        int: 値を書いたキーの数。
    """
    return KeySession(mode, seed).apply(amount)


@undoChunk("animBarNudgeValue")
def nudgeValue(delta):
    """選んだキーの値へ、一定量を足す。

    Args:
        delta (float): 足す量(角度は度・距離はcm)。

    Returns:
        int: 値を書いたキーの数。
    """
    if not math.isfinite(delta):
        raise ValueError("delta must be finite")
    count = 0
    for target in keys.targets():
        for index in target.indices:
            keys.setKeyValue(target.curve, index, keys.keyValue(target.curve, index) + delta)
            count += 1
    return count
