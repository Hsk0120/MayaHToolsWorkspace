import inspect
from importlib import reload

try:
    from PySide6 import QtCore, QtWidgets, QtGui
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import maya.cmds as cmds

import HTools.rigging.lib_.controllerShapeManager as controllerShapeManager

reload(controllerShapeManager)


class ControllerShapeManagerUI(MayaQWidgetDockableMixin, QtWidgets.QDialog):
    """Controller Shape Manager UI using PySide6"""
    
    WINDOW_NAME = "ControllerShapeManagerWindow"
    SHAPE_BUTTON_MIN_WIDTH = 100
    PARAM_FIELD_WIDTH = 80
    FLOAT_STEP = 1.0
    FLOAT_SLIDER_SCALE = 100

    @staticmethod
    def _clamp_0_255(value):
        return max(0, min(int(value), 255))

    @classmethod
    def _blend_colors(cls, color_a, color_b, t):
        """Blend two QColor values.

        Args:
            color_a (QColor)
            color_b (QColor)
            t (float): 0..1 (0 -> a, 1 -> b)
        """
        t = max(0.0, min(float(t), 1.0))
        return QtGui.QColor(
            cls._clamp_0_255(color_a.red() * (1.0 - t) + color_b.red() * t),
            cls._clamp_0_255(color_a.green() * (1.0 - t) + color_b.green() * t),
            cls._clamp_0_255(color_a.blue() * (1.0 - t) + color_b.blue() * t),
        )

    @staticmethod
    def _qss_rgb(color):
        return f"{color.red()}, {color.green()}, {color.blue()}"

    @staticmethod
    def _qss_rgba(color, alpha_0_255):
        a = max(0, min(int(alpha_0_255), 255))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a})"

    @staticmethod
    def _relative_luminance(color):
        """Return relative luminance (0..1) for sRGB color."""
        def _to_linear(c):
            c = float(c) / 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r = _to_linear(color.red())
        g = _to_linear(color.green())
        b = _to_linear(color.blue())
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @classmethod
    def _choose_contrast_text(cls, background_color):
        """Pick white/black text for legibility on the given background."""
        # Simple threshold works well for UI chips/buttons
        return QtGui.QColor(255, 255, 255) if cls._relative_luminance(background_color) < 0.45 else QtGui.QColor(20, 20, 20)
    
    def __init__(self, parent=None):
        super(ControllerShapeManagerUI, self).__init__(parent)
        
        # 現在選択されているシェイプの情報
        self.current_shape = {
            "func_name": None,
            "section_key": None,
            "params": [],
            "label": None,
            "section_color": None,
        }
        
        # パラメータウィジェットを保持する辞書
        self.param_widgets = {}

        # UI更新中など、自動再生成を一時停止するためのフラグ
        self._suspend_auto_regenerate = False

        # 画面が縦に伸びすぎないようにする（Parametersはスクロールで対応）
        self._auto_expand_parameters = False

        # Shapes ボタンのグリッド情報（列数可変のため）
        # [{"grid": QGridLayout, "buttons": [QPushButton, ...]}, ...]
        self._shape_button_grids = []
        self._shape_viewports = []

        # 選択ボタンを視覚化するための排他グループ
        self._shape_button_group = QtWidgets.QButtonGroup(self)
        self._shape_button_group.setExclusive(True)
        
        self.setWindowTitle("Controller Shape Manager")
        self.setObjectName(self.WINDOW_NAME)
        # リサイズ時に窮屈になりやすいので、最低サイズは控えめにして
        # スプリッターとスクロールで可変にする。
        # 初期表示の横幅を狭める（固定ではなく、ユーザーがリサイズ可能）
        self.setMinimumSize(440, 360)
        self.resize(520, 420)

        self._apply_theme_styles()
        
        self.build_ui()

    def _apply_theme_styles(self):
        """Maya/Qt のパレットに追従して UI の色を整える。"""
        pal = self.palette()

        window = pal.color(QtGui.QPalette.Window)
        base = pal.color(QtGui.QPalette.Base)
        button = pal.color(QtGui.QPalette.Button)
        text = pal.color(QtGui.QPalette.WindowText)
        mid = pal.color(QtGui.QPalette.Mid)
        highlight = pal.color(QtGui.QPalette.Highlight)
        disabled_text = pal.color(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText)

        # 若干だけ境界を見やすく（テーマに馴染ませつつコントラスト確保）
        border = self._blend_colors(mid, text, 0.12)
        panel_border = self._blend_colors(border, window, 0.30)
        tab_bg = self._blend_colors(button, window, 0.15)
        tab_selected = self._blend_colors(window, text, 0.06)

        # ダイアログ全体のQSS
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgb({self._qss_rgb(window)});
            }}

            QGroupBox {{
                font-weight: bold;
                font-size: 12px;
                border: 1px solid {self._qss_rgba(panel_border, 255)};
                border-radius: 5px;
                margin-top: 12px;
                padding-top: 12px;
            }}
            QGroupBox:flat {{
                border: none;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 6px;
                color: rgb({self._qss_rgb(text)});
                font-size: 12px;
            }}
            QLabel {{
                color: rgb({self._qss_rgb(text)});
                font-size: 11px;
            }}

            /* ScrollArea: 背景の二重化を避ける */
            QScrollArea {{
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}

            /* Tabs: 視認性を上げつつ、テーマ色へ追従 */
            QTabWidget::pane {{
                border: 1px solid {self._qss_rgba(border, 255)};
                border-radius: 4px;
                top: -1px;
                background-color: rgb({self._qss_rgb(window)});
            }}
            QTabBar::tab {{
                background-color: rgb({self._qss_rgb(tab_bg)});
                color: rgb({self._qss_rgb(text)});
                padding: 6px 12px;
                border: 1px solid {self._qss_rgba(border, 255)};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: rgb({self._qss_rgb(tab_selected)});
                color: rgb({self._qss_rgb(text)});
                font-weight: bold;
            }}
            QTabBar::tab:!selected {{
                margin-top: 2px;
            }}

            /* スライダー/スピンボックスを少しだけ見やすく */
            QSlider::groove:horizontal {{
                height: 6px;
                border-radius: 3px;
                background: {self._qss_rgba(base, 140)};
            }}
            QSlider::sub-page:horizontal {{
                border-radius: 3px;
                background: {self._qss_rgba(highlight, 170)};
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
                background: rgb({self._qss_rgb(highlight)});
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: rgb({self._qss_rgb(base)});
                color: rgb({self._qss_rgb(text)});
                border: 1px solid {self._qss_rgba(border, 255)};
                border-radius: 4px;
                padding: 2px 6px;
            }}
        """)

        # ほかの箇所で参照するため保持
        self._theme = {
            "window": window,
            "base": base,
            "button": button,
            "text": text,
            "mid": mid,
            "border": border,
            "highlight": highlight,
            "disabled_text": disabled_text,
        }

    def _on_shape_button_clicked(self, section_key, func_name, params, label, section_color):
        self.update_parameter_area(section_key, func_name, params, label, section_color)
        self.generate_shape()

    def _on_global_scale_changed(self, value):
        if getattr(self, "_suspend_auto_regenerate", False):
            return
        if not self.current_shape["func_name"]:
            return
        if not (cmds.ls(selection=True) or []):
            return
        self.generate_shape()

    def _on_parameters_changed(self, *args, **kwargs):
        if getattr(self, "_suspend_auto_regenerate", False):
            return
        if not self.current_shape["func_name"]:
            return
        if not (cmds.ls(selection=True) or []):
            return
        self.generate_shape()

    def _ensure_parameters_visible(self):
        """Parameters が表示しきれない場合はウィンドウ自体を縦に広げる。"""
        if not getattr(self, "_auto_expand_parameters", False):
            return
        # レイアウト反映後に計算できるように遅延実行
        def _do_resize():
            try:
                self.param_display_widget.adjustSize()
                self.parameter_group.adjustSize()
                self.adjustSize()

                desired_height = self.sizeHint().height()
                screen = self.screen() or QtWidgets.QApplication.primaryScreen()
                if screen:
                    available = screen.availableGeometry()
                    # タイトルバー等の余白分を少し残す
                    max_height = max(200, available.height() - 40)
                else:
                    max_height = desired_height

                new_height = min(desired_height, max_height)
                if new_height > self.height():
                    self.resize(self.width(), new_height)
            except Exception:
                pass

        QtCore.QTimer.singleShot(0, _do_resize)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Resize and watched in self._shape_viewports:
            self._reflow_shape_buttons()
        return super().eventFilter(watched, event)

    def _calculate_shape_columns(self, viewport_width):
        # ボタン最小幅 + グリッド間隔から列数を推定
        # ここはUI都合の値なので、極端に小さくしない。
        min_button_width = self.SHAPE_BUTTON_MIN_WIDTH
        spacing = 8
        if viewport_width <= 0:
            return 4
        columns = max(1, int((viewport_width + spacing) / (min_button_width + spacing)))
        return min(columns, 10)

    def _reflow_shape_buttons(self):
        for grid_info in self._shape_button_grids:
            grid_layout = grid_info["grid"]
            buttons = grid_info["buttons"]

            viewport_width = 0
            scroll = grid_info.get("scroll")
            if scroll:
                viewport_width = scroll.viewport().width()

            margins = grid_layout.contentsMargins()
            effective_width = max(0, viewport_width - (margins.left() + margins.right()))
            columns = self._calculate_shape_columns(effective_width)
            if columns < 1:
                columns = 1

            # 既存の配置を外して再配置（ウィジェットは破棄しない）
            while grid_layout.count():
                item = grid_layout.takeAt(0)
                if item.widget():
                    grid_layout.removeWidget(item.widget())

            for idx, button in enumerate(buttons):
                grid_layout.addWidget(button, idx // columns, idx % columns)
    
    @staticmethod
    def _is_float_value(value):
        return isinstance(value, float)
    
    @staticmethod
    def _get_shape_sections():
        """クラス定義から SHAPE_SECTIONS を動的に生成

        Returns:
            [(section_key, [(func_name, params_list), ...]), ...] の形式のリスト
        """
        # library から shape classes を取得
        section_classes_dict = controllerShapeManager.get_shape_classes()
        section_classes = list(section_classes_dict.items())

        result = []
        for section_key, section_class in section_classes:
            shapes = []

            # クラスのすべての静的メソッドを取得
            for method_name, method in inspect.getmembers(section_class, predicate=inspect.isfunction):
                if method_name.startswith('_'):  # プライベートメソッドをスキップ
                    continue

                sig = inspect.signature(method)
                params = []

                for param_name, param in sig.parameters.items():
                    if param_name == 'name':  # 'name' パラメータをスキップ
                        continue

                    # デフォルト値を取得
                    default = param.default if param.default != inspect.Parameter.empty else 1.0

                    # 最小値・最大値を決定
                    # NOTE: デフォルト値が 0 のパラメータ（角度など）は 0..360 を想定する
                    if isinstance(default, int):
                        if int(default) == 0:
                            min_val = 0
                            max_val = 180
                        else:
                            min_val = 1
                            # 基本の上限は 10 にする（ただしデフォルト値がそれ以上なら破綻しないように上げる）
                            max_val = max(10, int(default))
                    else:
                        if float(default) == 0.0:
                            min_val = 0.0
                            max_val = 180.0
                        else:
                            min_val = 0.0 if default < 1.0 else 1.0
                            # 基本の上限は 10.0 にする（ただしデフォルト値がそれ以上なら破綻しないように上げる）
                            max_val = max(10.0, float(default))

                    params.append((param_name, default, param_name, min_val, max_val))

                shapes.append((method_name, params))

            result.append((section_key, shapes))

        return result
    
    def _build_section_color_palette(self):
        """Maya/Qt テーマに馴染むセクション色を生成（過度に派手にならないトーン）。"""
        theme = getattr(self, "_theme", None) or {}
        window = theme.get("window", QtGui.QColor(60, 60, 60))

        # Maya は通常ダークテーマだが、ライト系でも破綻しないように
        window_v = window.value()  # HSV V (0..255)
        is_dark = window_v < 128

        # セクションの「色味」は維持しつつ、テーマに合わせて彩度/明度を決める
        # Hues: blue, indigo, green, red, amber, magenta
        hues = [205, 240, 150, 5, 40, 300]

        if is_dark:
            # もう少し「濃く」：彩度を上げ、背景への寄せを弱める
            base_v = max(120, min(210, window_v + 85))
            base_s = 170
            blend_t = 0.10
        else:
            base_v = max(85, min(155, window_v - 85))
            base_s = 155
            blend_t = 0.22

        palette = []
        for hue in hues:
            button_col = QtGui.QColor.fromHsv(hue, base_s, base_v)
            header_col = QtGui.QColor.fromHsv(hue, min(255, base_s + 18), max(0, base_v - 18))

            # 背景へ少し寄せて「浮きすぎ」を抑える
            button_col = self._blend_colors(button_col, window, blend_t)
            header_col = self._blend_colors(header_col, window, blend_t * 0.75)

            palette.append({"header": header_col, "button": button_col})

        return palette

    def _get_section_style(self, section_key, section_index=0):
        """セクション情報をテーマ色に合わせて生成"""
        if not hasattr(self, "_section_color_palette") or self._section_color_palette is None:
            self._section_color_palette = self._build_section_color_palette()

        color_scheme = self._section_color_palette[section_index % len(self._section_color_palette)]
        return {
            "title": section_key.capitalize(),
            "header": color_scheme["header"],
            "button": color_scheme["button"],
        }
    
    def build_ui(self):
        """UIを構築"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # All Shapes（グループの中にタブ）
        shapes_group = QtWidgets.QGroupBox("All Shapes")
        # Shapes は内容ぶんだけ確保し、余った縦スペースは Parameters に回す
        shapes_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        shapes_layout = QtWidgets.QVBoxLayout(shapes_group)
        shapes_layout.setContentsMargins(8, 12, 8, 8)
        shapes_layout.setSpacing(8)

        # Shapes：セクションごとにタブで分割
        self.shape_tab_widget = QtWidgets.QTabWidget()
        self.shape_tab_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.shape_tab_widget.setDocumentMode(False)
        shapes_layout.addWidget(self.shape_tab_widget, 1)

        for section_index, (section_key, shapes) in enumerate(self._get_shape_sections()):
            style = self._get_section_style(section_key, section_index)

            # タブ内はスクロール可能（ボタンが多い場合用）
            section_scroll = QtWidgets.QScrollArea()
            section_scroll.setWidgetResizable(True)
            section_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            section_scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            section_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

            section_widget = QtWidgets.QWidget()
            grid_layout = QtWidgets.QGridLayout(section_widget)
            grid_layout.setSpacing(8)
            grid_layout.setContentsMargins(8, 12, 8, 12)
            grid_layout.setAlignment(QtCore.Qt.AlignTop)

            section_buttons = []
            for idx, (func_name, params) in enumerate(shapes):
                button = QtWidgets.QPushButton(func_name)
                button.setMinimumHeight(36)
                button.setMinimumWidth(self.SHAPE_BUTTON_MIN_WIDTH)
                button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
                button.setCheckable(True)
                self._shape_button_group.addButton(button)
                base_col = style["button"]
                hover_col = base_col.lighter(115)
                pressed_col = base_col.darker(112)
                checked_col = base_col.darker(128)
                focus_col = getattr(self, "_theme", {}).get("highlight", QtGui.QColor(90, 140, 200))
                text_col = self._choose_contrast_text(base_col)
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: rgb({self._qss_rgb(base_col)});
                        color: rgb({self._qss_rgb(text_col)});
                        border: 1px solid rgba(0, 0, 0, 0);
                        border-radius: 4px;
                        padding: 8px;
                        font-size: 12px;
                        font-weight: 500;
                    }}
                    QPushButton:hover {{
                        background-color: rgb({self._qss_rgb(hover_col)});
                        border: 1px solid {self._qss_rgba(focus_col, 110)};
                    }}
                    QPushButton:pressed {{
                        background-color: rgb({self._qss_rgb(pressed_col)});
                        border: 1px solid {self._qss_rgba(focus_col, 140)};
                    }}
                    QPushButton:checked {{
                        background-color: rgb({self._qss_rgb(checked_col)});
                        border: 1px solid {self._qss_rgba(focus_col, 200)};
                    }}
                    QPushButton:checked:hover {{
                        background-color: rgb({self._qss_rgb(checked_col.lighter(106))});
                        border: 1px solid {self._qss_rgba(focus_col, 220)};
                    }}
                    QPushButton:focus {{
                        border: 1px solid {self._qss_rgba(focus_col, 180)};
                    }}
                    QPushButton:disabled {{
                        background-color: {self._qss_rgba(base_col, 140)};
                        color: {self._qss_rgba(QtGui.QColor(255, 255, 255), 160)};
                    }}
                """)
                button.clicked.connect(
                    lambda checked=False, sk=section_key, fn=func_name, p=params,
                           lb=func_name, sc=style['header']:
                    self._on_shape_button_clicked(sk, fn, p, lb, sc)
                )
                section_buttons.append(button)

            # 初期配置（後でviewport幅に合わせて組み直す）
            for idx, button in enumerate(section_buttons):
                grid_layout.addWidget(button, idx // 4, idx % 4)

            self._shape_button_grids.append({"grid": grid_layout, "buttons": section_buttons, "scroll": section_scroll})
            self._shape_viewports.append(section_scroll.viewport())
            section_scroll.viewport().installEventFilter(self)

            section_scroll.setWidget(section_widget)
            self.shape_tab_widget.addTab(section_scroll, style["title"])

        self.shape_tab_widget.currentChanged.connect(lambda _idx: QtCore.QTimer.singleShot(0, self._reflow_shape_buttons))
        # stretch=0: Shapes 側が縦に伸びすぎないようにする
        main_layout.addWidget(shapes_group, 0)

        # 下側（Parameters + Generate）
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)
        # stretch=1: Parameters 側を優先して縦スペースを使う
        main_layout.addWidget(bottom_widget, 1)
        
        # パラメータエリア
        self.parameter_group = QtWidgets.QGroupBox("Parameters")
        self.parameter_layout = QtWidgets.QVBoxLayout()
        self.parameter_layout.setSpacing(10)
        self.parameter_layout.setContentsMargins(8, 12, 8, 8)

        self.param_display_widget = QtWidgets.QWidget()
        self.param_display_layout = QtWidgets.QVBoxLayout(self.param_display_widget)
        self.param_display_layout.setContentsMargins(0, 0, 0, 0)
        self.param_display_layout.setSpacing(8)
        
        default_label = QtWidgets.QLabel("Select a shape button above")
        default_label.setAlignment(QtCore.Qt.AlignCenter)
        default_label.setMinimumHeight(40)
        disabled_text = getattr(self, "_theme", {}).get("disabled_text", QtGui.QColor(153, 153, 153))
        default_label.setStyleSheet(
            f"font-weight: bold; font-size: 12px; color: rgb({self._qss_rgb(disabled_text)});"
        )
        self.param_display_layout.addWidget(default_label)

        # Parameters はスクロールで表示（ウィンドウ全体をコンパクトに保つ）
        self.param_scroll_area = QtWidgets.QScrollArea()
        self.param_scroll_area.setWidgetResizable(True)
        self.param_scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.param_scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.param_scroll_area.setWidget(self.param_display_widget)
        self.parameter_layout.addWidget(self.param_scroll_area, 1)
        self.parameter_group.setLayout(self.parameter_layout)
        bottom_layout.addWidget(self.parameter_group, 1)

        # Global Scale（Parameters とは別グループ）
        global_scale_group = QtWidgets.QGroupBox("Global Scale")
        global_scale_group.setFlat(True)
        global_scale_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        global_scale_layout = QtWidgets.QHBoxLayout()
        global_scale_layout.setContentsMargins(8, 12, 8, 8)
        global_scale_layout.setSpacing(8)

        scale_label = QtWidgets.QLabel("Scale:")
        scale_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        global_scale_layout.addWidget(scale_label)

        self.global_scale_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.global_scale_slider.setMinimum(10)  # 0.1 * 100
        self.global_scale_slider.setMaximum(500)  # 5.0 * 100
        self.global_scale_slider.setValue(100)  # 1.0 * 100
        self.global_scale_slider.setSingleStep(int(self.FLOAT_STEP * self.FLOAT_SLIDER_SCALE))
        self.global_scale_slider.setPageStep(int(self.FLOAT_STEP * self.FLOAT_SLIDER_SCALE))
        self.global_scale_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.global_scale_slider.setTickInterval(50)

        self.global_scale_field = QtWidgets.QDoubleSpinBox()
        self.global_scale_field.setMinimum(0.0)
        self.global_scale_field.setMaximum(5.0)
        self.global_scale_field.setValue(1.0)
        self.global_scale_field.setSingleStep(self.FLOAT_STEP)
        self.global_scale_field.setDecimals(1)
        self.global_scale_field.setFixedWidth(90)

        # スライダーとフィールドを連動
        self.global_scale_slider.valueChanged.connect(
            lambda v: self.global_scale_field.setValue(v / 100.0)
        )
        self.global_scale_field.valueChanged.connect(
            lambda v: self.global_scale_slider.setValue(int(v * 100))
        )

        # Global Scale 変更で自動再生成
        self.global_scale_field.valueChanged.connect(self._on_global_scale_changed)

        global_scale_layout.addWidget(self.global_scale_slider, 1)
        global_scale_layout.addWidget(self.global_scale_field)
        global_scale_group.setLayout(global_scale_layout)
        bottom_layout.addWidget(global_scale_group, 0)
        
        # Generate ボタン
        # Shape生成は「Shapeボタン選択時」および「Parameters/Global Scale変更時」に自動で行う

        QtCore.QTimer.singleShot(0, self._reflow_shape_buttons)
        # 初期状態でボタン2行程度が見える最小高さを確保（以降はウィンドウリサイズで可変）
        QtCore.QTimer.singleShot(0, lambda: self._apply_shapes_min_height(shapes_group, rows=2))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_shape_buttons()

    def _apply_shapes_min_height(self, shapes_group, rows=2):
        """Shapesエリアの最小高さをボタン指定行数ぶん確保する（高さは可変）。"""
        try:
            tab_bar_h = self.shape_tab_widget.tabBar().sizeHint().height()
            button_h = 36
            grid_spacing = 8
            grid_margins_tb = 12 + 12
            rows_h = rows * button_h + max(0, rows - 1) * grid_spacing

            # グループボックス内余白とタイトル分を少し余裕見込み
            group_extra = 26
            desired = tab_bar_h + grid_margins_tb + rows_h + group_extra

            shapes_group.setMinimumHeight(desired)
        except Exception:
            pass
    
    def clear_param_display(self):
        """パラメータ表示エリアをクリア"""
        while self.param_display_layout.count():
            item = self.param_display_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.param_widgets.clear()
    
    def build_param_row(self, param_name, default_value, description, min_val, max_val):
        """パラメータ行を構築"""
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QGridLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setHorizontalSpacing(8)
        row_layout.setVerticalSpacing(0)
        
        # ラベル
        label = QtWidgets.QLabel(f"{description}:")
        # Global Scale と同様に左寄せ（右寄せ + 固定幅だとガタついて見えやすい）
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        label.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        row_layout.addWidget(label, 0, 0)
        
        if self._is_float_value(default_value):
            # Float スライダー
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setMinimum(int(min_val * self.FLOAT_SLIDER_SCALE))
            slider.setMaximum(int(max_val * self.FLOAT_SLIDER_SCALE))
            slider.setValue(int(default_value * self.FLOAT_SLIDER_SCALE))
            slider.setSingleStep(int(self.FLOAT_STEP * self.FLOAT_SLIDER_SCALE))
            slider.setPageStep(int(self.FLOAT_STEP * self.FLOAT_SLIDER_SCALE))
            
            # Float フィールド
            field = QtWidgets.QDoubleSpinBox()
            field.setMinimum(min_val)
            field.setMaximum(max_val)
            field.setValue(default_value)
            field.setSingleStep(self.FLOAT_STEP)
            field.setDecimals(1)
            field.setFixedWidth(self.PARAM_FIELD_WIDTH)
            
            # 連動
            slider.valueChanged.connect(lambda v: field.setValue(v / float(self.FLOAT_SLIDER_SCALE)))
            field.valueChanged.connect(lambda v: slider.setValue(int(v * self.FLOAT_SLIDER_SCALE)))
            
        else:
            # Int スライダー
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setMinimum(int(min_val))
            slider.setMaximum(int(max_val))
            slider.setValue(default_value)
            
            # Int フィールド
            field = QtWidgets.QSpinBox()
            field.setMinimum(int(min_val))
            field.setMaximum(int(max_val))
            field.setValue(default_value)
            field.setFixedWidth(self.PARAM_FIELD_WIDTH)
            
            # 連動
            slider.valueChanged.connect(field.setValue)
            field.valueChanged.connect(slider.setValue)
        
        row_layout.addWidget(slider, 0, 1)
        row_layout.addWidget(field, 0, 2)

        row_layout.setColumnStretch(1, 1)
        row_layout.setColumnStretch(0, 0)
        row_layout.setColumnStretch(2, 0)
        
        # ウィジェットを保存
        self.param_widgets[param_name] = {
            "slider": slider,
            "field": field,
            "default": default_value,
            "is_float": self._is_float_value(default_value)
        }

        # Parameters変更で自動再生成
        field.valueChanged.connect(self._on_parameters_changed)
        
        return row_widget
    
    def reset_to_defaults(self):
        """全パラメータをデフォルト値にリセット"""
        self._suspend_auto_regenerate = True
        try:
            for _param_name, widget_info in self.param_widgets.items():
                default = widget_info["default"]
                widget_info["field"].setValue(default)
        finally:
            self._suspend_auto_regenerate = False

        if self.current_shape["func_name"] and (cmds.ls(selection=True) or []):
            self.generate_shape()
    
    def update_parameter_area(self, section_key, func_name, params, label, section_color):
        """パラメータエリアを更新
        
        Args:
            section_key: セクション名
            func_name: 関数名
            params: パラメータリスト [(param_name, default_value, description, min_value, max_value), ...]
            label: シェイプの表示名
            section_color: セクションの色 QColor
        """
        self.current_shape["func_name"] = func_name
        self.current_shape["section_key"] = section_key
        self.current_shape["params"] = params
        self.current_shape["label"] = label
        self.current_shape["section_color"] = section_color

        self._suspend_auto_regenerate = True
        try:
            # 既存のパラメータエリアをクリア
            self.clear_param_display()
            
            # ヘッダー（Selected + Reset All）
            header_widget = QtWidgets.QWidget()
            header_layout = QtWidgets.QGridLayout(header_widget)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setHorizontalSpacing(8)
            header_layout.setVerticalSpacing(0)
            
            selected_label = QtWidgets.QLabel(f"Selected: {label}")
            # セクション色が強すぎないように、背景色と少しブレンドして馴染ませる
            window_col = getattr(self, "_theme", {}).get("window", QtGui.QColor(60, 60, 60))
            # もう少し濃く見せるため、背景へのブレンド量を少し下げる
            label_bg = self._blend_colors(section_color, window_col, 0.10)
            selected_label.setStyleSheet(f"""
                QLabel {{
                    background-color: rgb({self._qss_rgb(label_bg)});
                    color: white;
                    padding: 8px 12px;
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 4px;
                    border: 1px solid rgba(255, 255, 255, 35);
                }}
            """)
            
            reset_button = QtWidgets.QPushButton("Reset All")
            reset_button.setFixedHeight(30)
            reset_button.setFixedWidth(90)
            reset_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            btn_col = getattr(self, "_theme", {}).get("button", QtGui.QColor(90, 90, 90))
            btn_hover = btn_col.lighter(112)
            btn_pressed = btn_col.darker(110)
            border_col = getattr(self, "_theme", {}).get("border", QtGui.QColor(120, 120, 120))
            reset_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgb({self._qss_rgb(btn_col)});
                    color: white;
                    border-radius: 4px;
                    border: 1px solid {self._qss_rgba(border_col, 255)};
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: rgb({self._qss_rgb(btn_hover)});
                }}
                QPushButton:pressed {{
                    background-color: rgb({self._qss_rgb(btn_pressed)});
                }}
            """)
            reset_button.clicked.connect(self.reset_to_defaults)

            header_layout.addWidget(selected_label, 0, 0)
            header_layout.addWidget(reset_button, 0, 1)
            header_layout.setColumnStretch(0, 1)
            self.param_display_layout.addWidget(header_widget)
            
            # 各パラメータのUIを作成
            for param_name, default_value, description, min_val, max_val in params:
                param_row = self.build_param_row(param_name, default_value, description, min_val, max_val)
                self.param_display_layout.addWidget(param_row)
            
            self.param_display_layout.addStretch()
        finally:
            self._suspend_auto_regenerate = False

        # Parameters が表示しきれない場合はウィンドウを拡張
        self._ensure_parameters_visible()
    
    def generate_shape(self, checked=False):
        """現在選択されているシェイプを生成"""
        if not self.current_shape["func_name"]:
            cmds.warning("No shape selected")
            return
        
        reload(controllerShapeManager)
        
        # グローバルスケールを取得
        global_scale = self.global_scale_field.value()
        
        # パラメータ値を収集
        kwargs = {}
        for param_name, default_value, description, min_val, max_val in self.current_shape["params"]:
            widget_info = self.param_widgets.get(param_name)
            if not widget_info:
                continue
            
            value = widget_info["field"].value()
            
            if widget_info["is_float"]:
                # グローバルスケールを適用
                kwargs[param_name] = value * global_scale
            else:
                # 整数パラメータ（sidesなど）にはスケールを適用しない
                kwargs[param_name] = value
        
        # library から shape classes を取得して実行
        section_classes = controllerShapeManager.get_shape_classes()
        section_key = self.current_shape["section_key"]
        section_class = section_classes[section_key]
        func = getattr(section_class, self.current_shape["func_name"])
        result = func(**kwargs)

        created_transform = None
        if isinstance(result, (list, tuple)):
            created_transform = result[0] if result else None
        elif isinstance(result, str):
            created_transform = result

        if created_transform and cmds.objExists(created_transform):
            try:
                cmds.select(created_transform, replace=True)
            except Exception:
                pass


def show_controller_shape_manager_ui():
    """Controller Shape Manager UI を表示"""
    # 既存のウィンドウがあれば削除
    if cmds.window(ControllerShapeManagerUI.WINDOW_NAME, exists=True):
        cmds.deleteUI(ControllerShapeManagerUI.WINDOW_NAME)
    
    # 既存の workspaceControl があれば削除
    workspace_control_name = ControllerShapeManagerUI.WINDOW_NAME + "WorkspaceControl"
    if cmds.workspaceControl(workspace_control_name, exists=True):
        cmds.deleteUI(workspace_control_name)
    
    # ウィンドウを作成して表示
    window = ControllerShapeManagerUI()
    window.show(dockable=True)
    return window


# 互換性のため旧関数名も維持
def controllerShapeManagerUI():
    """Controller Shape Manager UI を表示（互換性維持用）"""
    return show_controller_shape_manager_ui()


if __name__ == "__main__":
    show_controller_shape_manager_ui()
