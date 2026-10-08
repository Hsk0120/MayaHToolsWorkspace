"""呼び出し側が指定した評価処理を計測する。Mayaの評価設定は変更しない。"""

import statistics
import time


def measure(operation, samples=30, warmup=3):
    """操作の所要時間を秒単位で返す。

    Args:
        operation (callable): 入力更新と評価を含む操作。各回で呼ぶ。
        samples (int): 記録する回数。
        warmup (int): 記録前の実行回数。
    Returns:
        dict: samples、median_seconds、min_seconds、max_seconds。
    Note:
        同じ値を読むだけではキャッシュの速度になる。必要なdirty化は
        呼び出し側で行う。処理の副作用や時間位置も呼び出し側が管理する。
    """
    if not callable(operation):
        raise TypeError('operation must be callable')
    if type(samples) is not int or samples <= 0 or type(warmup) is not int or warmup < 0:
        raise ValueError('Invalid sample count')
    for _ in range(warmup):
        operation()
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        operation()
        values.append(time.perf_counter() - start)
    return {'samples': samples, 'median_seconds': statistics.median(values),
            'min_seconds': min(values), 'max_seconds': max(values)}
