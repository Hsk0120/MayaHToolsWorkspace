"""Mayaの表示色指定とパレットのスナップショットを扱う。"""

import math
import maya.cmds as cmds



class Color:
    """色番号・RGB・無効状態を保持する可変の値。シーンは編集しない。

    RGBの最近傍はRGB空間の二乗距離で求め、同距離なら小さい番号を選ぶ。
    0番はDrawing Overridesの既定色指定なので、RGBからの検索対象は1～31。
    GUIではパレットを生成時に取得し、バッチでは標準パレットを使用する。
    プロパティ操作ではMayaへ問い合わせない。
    """

    # GUIのないMayaではcolorIndexがNoneを返すため、標準の表示色を使用する。
    _DEFAULT_PALETTE = (
        (0.4699999988079071, 0.4699999988079071, 0.4699999988079071),
        (0.0, 0.0, 0.0),
        (0.25, 0.25, 0.25),
        (0.6000000238418579, 0.6000000238418579, 0.6000000238418579),
        (0.6079999804496765, 0.0, 0.15700000524520874),
        (0.0, 0.01600000075995922, 0.37599998712539673),
        (0.0, 0.0, 1.0),
        (0.0, 0.2750000059604645, 0.09799999743700027),
        (0.14900000393390656, 0.0, 0.2630000114440918),
        (0.7839999794960022, 0.0, 0.7839999794960022),
        (0.5410000085830688, 0.28200000524520874, 0.20000000298023224),
        (0.24699999392032623, 0.13699999451637268, 0.12200000137090683),
        (0.6000000238418579, 0.14900000393390656, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.2549999952316284, 0.6000000238418579),
        (1.0, 1.0, 1.0),
        (1.0, 1.0, 0.0),
        (0.3919999897480011, 0.8629999756813049, 1.0),
        (0.2630000114440918, 1.0, 0.6389999985694885),
        (1.0, 0.6899999976158142, 0.6899999976158142),
        (0.8939999938011169, 0.675000011920929, 0.4749999940395355),
        (1.0, 1.0, 0.3880000114440918),
        (0.0, 0.6000000238418579, 0.32899999618530273),
        (0.8549000024795532, 0.5686299800872803, 0.4274500012397766),
        (0.8784300088882446, 0.784309983253479, 0.30588001012802124),
        (0.6352900266647339, 0.8117600083351135, 0.2784300148487091),
        (0.2313700020313263, 0.7568600177764893, 0.5803899765014648),
        (0.2549000084400177, 0.8196099996566772, 0.7254899740219116),
        (0.22744999825954437, 0.6156899929046631, 0.8078399896621704),
        (0.6117600202560425, 0.41960999369621277, 0.8078399896621704),
        (0.8078399896621704, 0.34902000427246094, 0.6549000144004822),
    )

    __hash__ = None

    def __init__(self, *, index=None, rgb=None):
        """一方の形式から色を作る。両方未指定（None）なら色番号0。

        Args:
            index (int | None): 0～31の色番号。RGBも未指定なら0を使用。
            rgb (Iterable[float] | None): 0～1の有限なRGB三要素。
        Raises:
            ValueError: 両形式を指定、または値が不正な場合。
            RuntimeError: Mayaのパレットを取得できない場合。
        """
        if index is None and rgb is None:
            index = 0
        if index is not None and rgb is not None:
            raise ValueError("Specify either index or rgb")
        if index is not None:
            index = self._validate_index(index)
        if rgb is not None:
            rgb = self._validate_rgb(rgb)
        self._palette, self._palette_source = self._read_palette()
        self._mode, self._index, self._rgb = "disabled", None, None
        if index is not None:
            self.index = index
        elif rgb is not None:
            self.rgb = rgb

    @staticmethod
    def _validate_index(value):
        """0～31の整数を検証する。boolや範囲外はValueError。"""
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 31:
            raise ValueError("Color index must be an integer from 0 to 31")
        return value

    @staticmethod
    def _validate_rgb(value):
        """有限なRGB三要素へ変換する。不正値はValueError。"""
        try:
            if isinstance(value, (str, bytes)):
                raise ValueError("RGB must be three numbers")
            values = tuple(float(v) for v in value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("RGB must be three numbers") from exc
        if len(values) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
            raise ValueError("RGB values must be finite and between 0 and 1")
        return values

    @classmethod
    def _read_palette(cls):
        """現在のMayaパレットを読み取る。設定・保存はしない。"""
        if cmds.about(batch=True):
            return cls._DEFAULT_PALETTE, "default"
        try:
            palette = tuple(cls._validate_rgb(cmds.colorIndex(i, query=True)) for i in range(32))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Cannot read Maya color palette") from exc
        return palette, "maya"

    @staticmethod
    def _nearest(rgb, palette):
        """RGBから通常色1～31の最近傍番号を求める。"""
        return min(range(1, 32), key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, palette[i])))

    @property
    def paletteSource(self):
        """str: GUIから取得したmaya、またはバッチ用標準値のdefault。"""
        return self._palette_source

    @property
    def mode(self):
        """str: 最後に指定した形式index/rgb、またはdisabled。"""
        return self._mode

    @property
    def index(self):
        """int | None: 色番号。RGB指定時は近似番号、無効時はNone。"""
        return self._index

    @index.setter
    def index(self, value):
        """番号を設定し、保持パレットのRGBへ同期する。

        Args:
            value (int): 保持パレットの色番号。
        """
        index = self._validate_index(value)
        self._index, self._rgb, self._mode = index, self._palette[index], "index"

    @property
    def rgb(self):
        """tuple[float, float, float] | None: 保持RGB。無効時はNone。"""
        return self._rgb

    @rgb.setter
    def rgb(self, value):
        """指定RGBを保持して近似番号を更新する。RGB自体は丸めない。

        Args:
            value (Iterable[float]): 0〜1 の RGB 3 成分。
        """
        rgb = self._validate_rgb(value)
        self._index, self._rgb, self._mode = self._nearest(rgb, self._palette), rgb, "rgb"

    @classmethod
    def disabled(cls):
        """Color: 無効状態を作成する。"""
        result = cls()
        result._mode, result._index, result._rgb = "disabled", None, None
        return result

    def refreshPalette(self):
        """Mayaのパレットを再取得し、指定形式を保って対応値を再計算する。

        Returns:
            Color: 自身。番号指定はRGB、RGB指定は近似番号を更新する。
        Raises:
            RuntimeError: パレット取得失敗。保持値は変更しない。
        """
        palette, source = self._read_palette()
        index, rgb = self._index, self._rgb
        if self.mode == "index":
            rgb = palette[index]
        elif self.mode == "rgb":
            index = self._nearest(rgb, palette)
        self._palette, self._index, self._rgb = palette, index, rgb
        self._palette_source = source
        return self

    def copy(self):
        """Color: Mayaに照会せず、同じ保持値を持つ独立したコピーを返す。"""
        result = object.__new__(type(self))
        result._palette, result._index, result._rgb, result._mode = self._palette, self.index, self.rgb, self.mode
        result._palette_source = self.paletteSource
        return result

    @classmethod
    def coerce(cls, value):
        """Color・番号・RGB・Noneを独立したColorへ正規化する。

        Args:
            value (Color | int | Iterable[float] | None): Noneは無効状態。
        Returns:
            Color: 正規化した値。入力Colorはコピーする。
        """
        if isinstance(value, cls):
            return value.copy()
        if value is None:
            return cls.disabled()
        if isinstance(value, int):
            return cls(index=value)
        return cls(rgb=value)

    def __eq__(self, other):
        """形式と指定値を比較する。画面上の見た目や近似一致は比較しない。"""
        if not isinstance(other, Color):
            return NotImplemented
        return self.mode == other.mode and (
            self.index == other.index if self.mode == "index" else self.rgb == other.rgb)

    def __repr__(self):
        """str: 指定形式と値を表示する。"""
        if self.mode == "disabled":
            return "Color.disabled()"
        return f"Color({self.mode}={getattr(self, self.mode)!r})"

# 再読み込み前の旧コレクション参照を残さない。
globals().pop("Colors", None)
