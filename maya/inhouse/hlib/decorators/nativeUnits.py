"""内部単位での一時処理を提供する。"""
from contextlib import contextmanager
import maya.api.OpenMaya as om2


@contextmanager
def nativeUnits():
    """ブロック内だけ内部単位(距離=cm、角度=radian)を強制する。

    行列やベクトルの演算など、シーンの表示単位に依存しない計算をしたい場合に
    使う。ブロックを抜ける際(例外時を含む)に開始時点の UI 単位へ復元する。
    ``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の
    往復が無く、時間単位には影響しない。表示単位の変更はシーンデータ自体を
    変更しないため、この切り替え自体は Maya の Undo キューに乗らない
    （計算中の単位変換用の一時状態であり、操作そのもののロールバックは行わない）。

    Yields:
        None: ブロック内では距離=センチメートル、角度=ラジアンとして扱ってよい。
    """
    previous_linear = om2.MDistance.uiUnit()
    previous_angle = om2.MAngle.uiUnit()
    try:
        om2.MDistance.setUIUnit(om2.MDistance.kCentimeters)
        om2.MAngle.setUIUnit(om2.MAngle.kRadians)
        yield
    finally:
        om2.MDistance.setUIUnit(previous_linear)
        om2.MAngle.setUIUnit(previous_angle)


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('native_units',):
    globals().pop(_obsolete_name, None)
