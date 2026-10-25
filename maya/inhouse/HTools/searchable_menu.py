# -*- coding: utf-8 -*-
"""Maya Qt 用の検索可能メニューコンポーネント。"""
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

try:
    QACTION_CLASS = QtGui.QAction
except AttributeError:
    QACTION_CLASS = QtWidgets.QAction

# 項目の文字の後ろに置く空白。"\t" 以降はショートカットの欄として右端に描かれるので、
# 「?」の印を描く場所を確保できる(表示は空白なので見えない)。
HELP_SPACER = "\t  "


class HelpIconMixin(object):
    """ヘルプを登録した項目の右端に「?」を描き、そこを押すとヘルプを開くメニューの機能。

    項目には :func:`setActionHelp` でヘルプを開く関数を登録する。印の上で
    ボタンを離すとヘルプを開き、それ以外の場所では通常どおり項目を実行する。
    """

    HELP_ICON_SIZE = 14
    HELP_ICON_MARGIN = 6
    HELP_PROPERTY = "htoolsHelpCallback"

    def _init_help_icons(self):
        """印の上にマウスがあるかを追うための状態を用意します。"""
        self._help_hover_action = None
        self.setMouseTracking(True)

    @classmethod
    def setActionHelp(cls, action, callback):
        """項目にヘルプを開く関数を登録し、印を描く場所を空けます。

        Args:
            action: ヘルプを付けるQtアクション。
            callback: 引数なしで呼ぶとヘルプを開く関数。
        """
        if HELP_SPACER not in action.text():
            action.setText(action.text().split("\t")[0] + HELP_SPACER)
        action.setProperty(cls.HELP_PROPERTY, callback)

    @classmethod
    def actionHelp(cls, action):
        """項目に登録したヘルプの関数を返します(無ければ None)。

        Args:
            action: 調べるQtアクション。
        """
        if action is None:
            return None
        return action.property(cls.HELP_PROPERTY)

    def _help_icon_rect(self, action):
        """項目の右端の「?」の印の矩形を返します。

        Args:
            action: 印を描くQtアクション。
        """
        item = self.actionGeometry(action)
        size = self.HELP_ICON_SIZE
        return QtCore.QRect(
            item.right() - self.HELP_ICON_MARGIN - size,
            item.center().y() - size // 2,
            size,
            size,
        )

    def _help_action_at(self, position):
        """位置が「?」の印の上なら、その項目を返します。

        Args:
            position: メニュー内の座標。
        """
        action = self.actionAt(position)
        if action is None or not action.isVisible() or self.actionHelp(action) is None:
            return None
        if self._help_icon_rect(action).adjusted(-3, -3, 3, 3).contains(position):
            return action
        return None

    def paintEvent(self, event):
        """通常の描画の後に、ヘルプのある項目へ「?」の印を描きます。

        Args:
            event: Qtの描画イベント。
        """
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(self.HELP_ICON_SIZE - 4)
        painter.setFont(font)
        palette = self.palette()
        for action in self.actions():
            if not action.isVisible() or self.actionHelp(action) is None:
                continue
            rect = self._help_icon_rect(action)
            if not event.rect().intersects(rect):
                continue
            hovered = action is self._help_hover_action
            # 項目が選ばれている間は選択色の上に描くので、文字色を合わせる。
            if action is self.activeAction():
                color = palette.color(QtGui.QPalette.HighlightedText)
            else:
                color = palette.color(QtGui.QPalette.Text)
            pen = QtGui.QPen(color)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            if hovered:
                fill = QtGui.QColor(color)
                fill.setAlpha(70)
                painter.setBrush(fill)
            else:
                painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5))
            painter.drawText(rect, QtCore.Qt.AlignCenter, "?")
        painter.end()

    def mouseMoveEvent(self, event):
        """印の上にマウスがあるかを更新し、案内を出します。

        Args:
            event: Qtのマウスイベント。
        """
        super().mouseMoveEvent(event)
        position = event.pos()
        action = self._help_action_at(position)
        if action is not self._help_hover_action:
            self._help_hover_action = action
            self.update()
            if action is not None:
                # Qt6 は globalPosition()、Qt5 は globalPos()。
                if hasattr(event, "globalPosition"):
                    global_position = event.globalPosition().toPoint()
                else:
                    global_position = event.globalPos()
                QtWidgets.QToolTip.showText(global_position, "Open help", self)
            else:
                QtWidgets.QToolTip.hideText()

    def leaveEvent(self, event):
        """メニューから出たら印の強調を消します。

        Args:
            event: Qtのイベント。
        """
        super().leaveEvent(event)
        if self._help_hover_action is not None:
            self._help_hover_action = None
            self.update()

    def mouseReleaseEvent(self, event):
        """印の上で離したらヘルプを開き、項目は実行しません。

        Args:
            event: Qtのマウスイベント。
        """
        action = self._help_action_at(event.pos())
        if action is None or event.button() != QtCore.Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        callback = self.actionHelp(action)
        # 開いているメニューをすべて閉じてからヘルプを開く(ツールは実行しない)。
        popup = QtWidgets.QApplication.activePopupWidget()
        while popup is not None:
            popup.close()
            next_popup = QtWidgets.QApplication.activePopupWidget()
            if next_popup is popup:
                break
            popup = next_popup
        callback()


class ToolMenu(HelpIconMixin, QtWidgets.QMenu):
    """HToolsのカテゴリのサブメニュー。ツール名の右端の「?」からヘルプを開けます。"""

    def __init__(self, title="", parent=None):
        """ToolMenu を初期化します。

        Args:
            title (str): メニュータイトル。
            parent (QtWidgets.QWidget | None): 親ウィジェット。
        """
        super().__init__(title, parent)
        self._init_help_icons()


class SearchableMenu(HelpIconMixin, QtWidgets.QMenu):
    """検索/フィルタ機能を備えたメニュークラス。"""
    
    def __init__(self, title="", parent=None, enable_search=True, flat_results=False):
        """SearchableMenu を初期化します。

        Args:
            title (str): メニュータイトル。
            parent (QtWidgets.QWidget | None): 親ウィジェット。
            enable_search (bool): 検索 UI を有効化するか。
            flat_results (bool): 検索結果をフラット表示するか。
        """
        super().__init__(title, parent)
        self._search_field = None
        self._menu_items = {}  # Maps action text to QAction
        self._separators = []  # Track separators for visibility control
        self._submenu_actions = {}  # Track submenu actions
        self._enable_search = enable_search
        self._flat_results = flat_results
        self._item_metadata = {}  # Maps action to metadata (category, etc)
        self._original_actions = []  # Store original actions before search
        self._search_result_actions = []  # Store search result actions
        self._init_help_icons()

        if enable_search:
            self._init_search_widget()
            # Connect to menu shown event to auto-focus search field
            self.aboutToShow.connect(self._on_menu_shown)
    
    def _init_search_widget(self):
        """検索入力ウィジェットを生成してメニュー先頭に追加します。"""
        # Create a widget container for the search field
        search_container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(search_container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Create search field
        self._search_field = QtWidgets.QLineEdit()
        self._search_field.setPlaceholderText("Search...")
        self._search_field.setMaximumHeight(25)
        self._search_field.textChanged.connect(self._filter_items)
        
        layout.addWidget(self._search_field)
        
        # QWidgetAction として埋め込み、通常メニュー項目と共存させる。
        widget_action = QtWidgets.QWidgetAction(self)
        widget_action.setDefaultWidget(search_container)
        self.addAction(widget_action)
        
        # Add separator below search field
        self.addSeparator()
    
    def addAction(self, *args):
        """メニュー項目追跡のため addAction をオーバーライドします。

        Args:
            *args: 呼出し先またはUIシグナルから渡される位置引数。
        """
        action = super().addAction(*args)
        
        # Only track non-separator actions that aren't the search widget
        if action is not None and action.text():
            self._menu_items[action.text()] = action
        
        return action
    
    def addMenu(self, *args):
        """サブメニュー追跡のため addMenu をオーバーライドします。

        Args:
            *args: 呼出し先またはUIシグナルから渡される位置引数。
        """
        result = super().addMenu(*args)

        menu = None
        menu_action = None

        if isinstance(args[0], QtWidgets.QMenu):
            menu = args[0]
        elif isinstance(result, QtWidgets.QMenu):
            menu = result
        elif isinstance(result, QACTION_CLASS):
            menu_action = result
            menu = result.menu()

        if menu is not None and menu_action is None:
            menu_action = menu.menuAction()

        if menu_action is not None:
            self._submenu_actions[id(menu_action)] = menu_action

        return result
    
    def addSeparator(self):
        """区切り線追跡のため addSeparator をオーバーライドします。"""
        separator = super().addSeparator()
        self._separators.append(separator)
        return separator
    
    def _collect_flat_items(self):
        """メニュー/サブメニュー項目をフラットな一覧に収集します。"""
        items = []
        actions = self.actions()
        skip_count = 2 if self._enable_search else 0
        
        for action in actions[skip_count:]:
            # Skip search result actions to avoid duplicates
            if action in self._search_result_actions:
                continue
            
            if self._is_separator(action) or not action.text():
                continue
            
            if action.menu():
                # This is a submenu - collect its items with category
                submenu = action.menu()
                category_name = action.text()
                items.extend(self._collect_submenu_items(submenu, category_name))
            else:
                # Regular action
                items.append((action, None))
        
        return items
    
    def _collect_submenu_items(self, menu, category_name):
        """サブメニュー配下の項目を再帰的に収集します。

        Args:
            menu: 操作対象のQtメニュー。
            category_name: UIに表示するラベル。
        """
        items = []
        
        for action in menu.actions():
            if hasattr(action, 'isSeparator') and action.isSeparator():
                continue
            
            if action.menu():
                # Nested submenu - include category in name
                nested_category = f"{category_name} > {action.text()}"
                items.extend(self._collect_submenu_items(action.menu(), nested_category))
            elif action.text():
                items.append((action, category_name))
        
        return items
    
    def _show_flat_results(self, search_text):
        """検索一致項目をフラット一覧として表示します。

        Args:
            search_text: 一覧を絞り込む検索文字列。
        """
        actions = self.actions()
        skip_count = 2 if self._enable_search else 0
        
        # 元メニュー項目を一旦隠し、検索結果専用アクションを出す。
        for action in actions[skip_count:]:
            action.setVisible(False)
        
        # Collect matching items
        all_items = self._collect_flat_items()
        matching_items = []
        
        for action, category in all_items:
            if search_text.lower() in action.text().lower():
                matching_items.append((action, category))
        
        # Remove old search result actions
        for action in self._search_result_actions:
            self.removeAction(action)
            action.deleteLater()
        self._search_result_actions.clear()
        
        # Add search result actions
        if matching_items:
            for i, (action, category) in enumerate(matching_items):
                # 結果は元アクションを直接動かせるよう trigger を中継する。
                # "\t" 以降(ヘルプの印の場所を空ける空白)は名前に含めない。
                name = action.text().split("\t")[0]
                if category:
                    display_text = f"{name} ({category})"
                else:
                    display_text = name

                result_action = self.addAction(display_text)
                # Connect to the original action's trigger
                result_action.triggered.connect(action.triggered)
                help_callback = self.actionHelp(action)
                if help_callback is not None:
                    self.setActionHelp(result_action, help_callback)
                self._search_result_actions.append(result_action)
    
    def _filter_items(self, search_text):
        """検索文字列に応じて表示モードを切り替えて絞り込みます。

        Args:
            search_text: 一覧を絞り込む検索文字列。
        """
        search_text = search_text.lower().strip()
        
        if self._flat_results and search_text:
            # Show results as flat list
            self._show_flat_results(search_text)
        else:
            # Show results with hierarchy
            self._show_hierarchical_results(search_text)
    
    def _show_hierarchical_results(self, search_text):
        """階層構造を維持したまま検索結果を表示します。

        Args:
            search_text: 一覧を絞り込む検索文字列。
        """
        # Remove search result actions if any
        for action in self._search_result_actions:
            self.removeAction(action)
            action.deleteLater()
        self._search_result_actions.clear()
        
        # Get all actions (skip first two: search widget and its separator if search is enabled)
        actions = self.actions()
        skip_count = 2 if self._enable_search else 0
        
        if len(actions) < skip_count:
            return
        
        # Process actions starting after search field and separator
        for action in actions[skip_count:]:
            if self._is_separator(action):
                # Hide separators initially
                action.setVisible(False)
            elif action.menu():
                # This is a submenu action
                submenu = action.menu()
                has_visible_items = self._filter_submenu(submenu, search_text)
                
                # Show submenu only if it has visible items or empty search
                action.setVisible(has_visible_items or not search_text)
            elif action.text():
                # Regular action item - check if it matches search
                matches = search_text in action.text().lower()
                action.setVisible(matches)
            else:
                # Hide other actions if search is active
                action.setVisible(not search_text)
        
        # Show separators between visible items intelligently
        if search_text:
            self._update_separator_visibility(actions[skip_count:])
    
    def _filter_submenu(self, menu, search_text):
        """サブメニューを再帰的に絞り込み、表示可否を返します。

        Args:
            menu: 操作対象のQtメニュー。
            search_text: 一覧を絞り込む検索文字列。
        """
        has_visible = False
        actions = menu.actions()
        
        for action in actions:
            if action.menu():
                # Nested submenu - recurse
                has_visible_nested = self._filter_submenu(action.menu(), search_text)
                action.setVisible(has_visible_nested or not search_text)
                has_visible = has_visible or has_visible_nested
            elif hasattr(action, 'isSeparator') and action.isSeparator():
                # Separator - handle separately
                action.setVisible(False)
            elif action.text():
                # Regular action - check match
                matches = search_text in action.text().lower()
                action.setVisible(matches)
                has_visible = has_visible or matches
            else:
                action.setVisible(not search_text)
        
        return has_visible
    
    def _is_separator(self, action):
        """アクションが区切り線かどうかを返します。

        Args:
            action: 表示・追跡するQtアクション。
        """
        return action in self._separators
    
    def _update_separator_visibility(self, actions):
        """前後の可視項目に基づいて区切り線表示を更新します。

        Args:
            actions: 表示順に並べたQtアクション。
        """
        for i, action in enumerate(actions):
            if self._is_separator(action):
                # Check if there are visible items before and after
                has_visible_before = any(
                    a.isVisible() for a in actions[:i]
                    if not self._is_separator(a)
                )
                has_visible_after = any(
                    a.isVisible() for a in actions[i+1:]
                    if not self._is_separator(a)
                )
                
                # Show separator only if there are visible items on both sides
                action.setVisible(has_visible_before and has_visible_after)
    
    def clearSearch(self):
        """検索フィールドをクリアし、通常表示に戻します。"""
        if self._search_field:
            self._search_field.clear()
    
    def _on_menu_shown(self):
        """メニュー表示時に検索フィールドへ自動フォーカスします。"""
        if self._search_field:
            self._search_field.setFocus()
            self._search_field.selectAll()
    
    def get_visible_items(self):
        """現在可視なメニュー項目テキスト一覧を返します。"""
        visible = []
        skip_count = 2 if self._enable_search else 0
        
        for action in self.actions()[skip_count:]:
            if action.isVisible() and action.text():
                visible.append(action.text())
        return visible
