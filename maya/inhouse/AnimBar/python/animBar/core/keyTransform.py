"""選んだキーの値を、スライダーの量に応じて目標へ近づける・押し出す・揺らす。

スライダーの量 amount は -1〜1 を基本とする(範囲外は行き過ぎ)。各モードの意味は次のとおり。

- ``blendToNeighbors``: 正は後ろのキー、負は前のキーへ近づける。
- ``blendToDefault``: アトリビュートの既定値へ近づける(負は反対へ押し出す)。
- ``blendToFrame``: 記録した左右の時刻の値へ近づける(負は左、正は右)。
- ``blendToMirror``: 反対側のコントロールの同じ時刻の値へ近づける。
- ``pushPull``: 前後のキーを結ぶ直線から離す(正)・近づける(負)。
- ``easeInOut``: 選んだ範囲の両端を保ち、間をイーズの曲線に沿わせる(正はイーズイン、負はイーズアウト)。
- ``noise``: 乱数で揺らす(量は揺れ幅)。
- ``scaleFromLeft``・``scaleFromRight``: 選んだキーの前(後ろ)の選んでいないキーの値を中心に、値の幅を
  ``1 + 量`` 倍にする(前後のキーが無ければ、選んだ最初・最後のキーの値を中心にする)。
- ``scaleFromAverage``: 選んだキーの値の平均を中心に、値の幅を ``1 + 量`` 倍にする。
- ``scaleFromDefault``: アトリビュートの既定値を中心に、値の幅を ``1 + 量`` 倍にする。

中心はカーブごとに決める。

スライダーをドラッグする間は、開始時の値を基準に計算し直す(:class:`KeySession`)。
"""

import math
import random
from collections import namedtuple

import maya.api.OpenMaya as om2

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
    ("scaleFromLeft", "Scale L"),
    ("scaleFromRight", "Scale R"),
    ("scaleFromAverage", "Scale Avg"),
    ("scaleFromDefault", "Scale Def"),
)

#: 値の幅を変える(中心から拡大・縮小する)モード。
SCALE_MODES = ("scaleFromLeft", "scaleFromRight", "scaleFromAverage", "scaleFromDefault")

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
        if self.mode in SCALE_MODES:
            pivot = self._pivot(target, values, chosen)
            return [pivot] * len(target.indices)
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

    def _pivot(self, target, values, chosen):
        """値の幅を変えるモードの中心を、カーブごとに求める。

        Args:
            target (Target): 対象。
            values (list[float]): カーブの全キーの値。
            chosen (set[int]): 選んだキーの番号。

        Returns:
            float: 中心の値。
        """
        indices = target.indices
        if self.mode == "scaleFromLeft":
            previous = min(indices) - 1
            while previous in chosen:
                previous -= 1
            return values[previous] if previous >= 0 else values[min(indices)]
        if self.mode == "scaleFromRight":
            following = max(indices) + 1
            while following in chosen:
                following += 1
            return values[following] if following < len(values) else values[max(indices)]
        if self.mode == "scaleFromAverage":
            return sum(values[index] for index in indices) / float(len(indices))
        return keys.defaultValue(target.plug)

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
        if self.mode in SCALE_MODES:
            return goal + (value - goal) * (1.0 + amount)
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


NoiseEdit = namedtuple("NoiseEdit", "curve index time before after unit")


def previewNoise(seed, amplitudes):
    """既存キーの位置と単位別の振幅から、書き込み前の変更一覧を作る。

    Args:
        seed (int): 乱数シード。
        amplitudes (dict): deg・cm・frame・unitlessごとの最大変化量。省略した種類は対象外。

    Returns:
        list[NoiseEdit]: カーブ名、キー番号の順に並べた変更内容。
    """
    for amplitude in amplitudes.values():
        if not math.isfinite(amplitude) or amplitude < 0:
            raise ValueError("Amplitude must be finite and non-negative")
    units = {"A": "deg", "L": "cm", "T": "frame", "U": "unitless"}
    rng = random.Random(seed)
    rows = []
    for target in sorted(keys.targets(), key=lambda item: item.curve.getName()):
        curve = target.curve
        unit = units[curve.getType()[-1]]
        if not amplitudes.get(unit):
            continue
        times, values = curve.getKeyInputs(), curve.getKeyValues()
        for index in sorted(target.indices):
            delta = rng.uniform(-1, 1) * amplitudes[unit]
            after = values[index] + delta
            if not math.isfinite(after):
                raise ValueError("Noise result must be finite")
            rows.append(NoiseEdit(curve, index, times[index], values[index], after, unit))
    return rows


@undoChunk("animBarApplyNoisePreview")
def applyNoisePreview(rows):
    """プレビュー時と時刻・値が一致することを確認し、まとめて適用する。"""
    snapshots = {}
    for row in rows:
        if row.curve not in snapshots:
            snapshots[row.curve] = row.curve.getKeyInputs(), row.curve.getKeyValues()
        times, values = snapshots[row.curve]
        if row.index >= len(times) or times[row.index] != row.time or values[row.index] != row.before:
            raise ValueError("Target keys changed after preview")
    for row in rows:
        keys.setKeyValue(row.curve, row.index, row.after)
    return len(rows)


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


@undoChunk("animBarClampDifference")
def clampDifference(limit):
    """選択キーの値を、直前キーとの差が指定量以内に収まるように調整する。

    Args:
        limit (float): 隣接キー間で許容する値の差の絶対値。

    Returns:
        int: 値が変わったキー数。
    """
    if not math.isfinite(limit) or limit < 0:
        raise ValueError("limit must be finite and nonnegative")
    changes = []
    for target in keys.targets():
        values = list(target.curve.getKeyValues())
        for index in sorted(target.indices):
            if not index:
                continue
            previous = values[index - 1]
            adjusted = max(previous - limit, min(previous + limit, values[index]))
            if adjusted != values[index]:
                changes.append((target.curve, index, adjusted))
                values[index] = adjusted
    for curve, index, value in changes:
        keys.setKeyValue(curve, index, value)
    return len(changes)


@undoChunk("animBarPowerValues")
def powerValues(exponent):
    """対象キーの絶対値を累乗し、元の符号を付けて書き戻す。

    Args:
        exponent (float): 有限の指数。0の負乗は指定できない。

    Returns:
        int: 値が変わったキー数。
    """
    if not math.isfinite(exponent):
        raise ValueError("Exponent must be finite")
    changes = []
    for target in keys.targets():
        values = target.curve.getKeyValues()
        for index in target.indices:
            value = values[index]
            if value == 0 and exponent < 0:
                raise ValueError("Cannot raise a zero key value to a negative power")
            try:
                magnitude = math.pow(abs(value), exponent)
            except OverflowError as error:
                raise ValueError("Powered key value exceeds the finite range") from error
            result = -magnitude if value < 0 else magnitude
            if not math.isfinite(result):
                raise ValueError("Powered key value must be finite")
            if result != value:
                changes.append((target.curve, index, result))
    for curve, index, value in changes:
        keys.setKeyValue(curve, index, value)
    return len(changes)


@undoChunk("animBarPowerTimes")
def powerTimes(exponent):
    """選択キーのフレーム番号を符号付きで累乗し、最寄りのMaya tickへ丸める。

    Args:
        exponent (float): 有限の指数。

    Returns:
        int: 時刻が変わったキー数。

    Raises:
        ValueError: 時刻を表せない場合や、キーが重なるか順序が変わる場合。
    """
    if not math.isfinite(exponent):
        raise ValueError("Exponent must be finite")
    ticks_per_frame = om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds) * om2.MTime.ticksPerSecond()
    moves = []
    for target in keys.targets():
        if not target.curve.isTimeInput():
            raise ValueError("Power key times requires time-input curves")
        frames = target.curve.getKeyInputs()
        ticks = [round(frame * ticks_per_frame) for frame in frames]
        destinations = ticks.copy()
        for index in target.indices:
            frame = frames[index]
            if frame == 0 and exponent < 0:
                raise ValueError("Cannot raise frame zero to a negative power")
            try:
                powered = math.copysign(math.pow(abs(frame), exponent), frame)
                destination = round(powered * ticks_per_frame)
            except (ValueError, OverflowError) as error:
                raise ValueError("Powered key time exceeds the supported range") from error
            if abs(destination) >= 2 ** 53:
                raise ValueError("Powered key time exceeds exact tick precision")
            destinations[index] = destination
        if any(left >= right for left, right in zip(destinations, destinations[1:])):
            raise ValueError("Powered key times would overlap or cross another key")
        # 左へは先頭から、右へは末尾から移して、移動途中も隣のキーを越えないようにする。
        offsets = [end - start for start, end in zip(ticks, destinations)]
        moves.extend((target.curve, i, d) for i, d in enumerate(offsets) if d < 0)
        moves.extend((target.curve, i, offsets[i]) for i in reversed(range(len(offsets))) if offsets[i] > 0)
    for curve, index, delta in moves:
        curve.moveKey(index=index, timeOffset=delta / ticks_per_frame)
    return len(moves)


@undoChunk("animBarSmoothKeys")
def smoothKeys():
    """各カーブの両端を固定し、選択キーを直前・直後の元のキーを結ぶ直線へ半分近づける。

    飛び飛びの選択でも、選択外の隣接キーを補間に使う。選択外の値は保持する。
    """
    changes = []
    for target in keys.targets():
        values = target.curve.getKeyValues()
        times = target.curve.getKeyInputs()
        for index in target.indices:
            if 0 < index < len(values) - 1:
                fraction = (times[index] - times[index - 1]) / (times[index + 1] - times[index - 1])
                interpolated = values[index - 1] + fraction * (values[index + 1] - values[index - 1])
                value = (values[index] + interpolated) * 0.5
                if value != values[index]:
                    changes.append((target.curve, index, value))
    for curve, index, value in changes:
        keys.setKeyValue(curve, index, value)
    return len(changes)
