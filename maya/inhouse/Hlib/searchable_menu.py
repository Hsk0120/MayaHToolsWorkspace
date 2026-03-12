# -*- coding: utf-8 -*-
"""Searchable Menu component for Maya Qt.

Provides a menu with a search/filter field for quick navigation.
"""
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

try:
    QACTION_CLASS = QtGui.QAction
except AttributeError:
    QACTION_CLASS = QtWidgets.QAction


class SearchableMenu(QtWidgets.QMenu):
    """A menu with built-in search/filter functionality.
    
    This menu includes a search field at the top that allows users to
    filter menu items in real-time as they type. Matches are displayed
    as a flat list with category information.
    """
    
    def __init__(self, title="", parent=None, enable_search=True, flat_results=False):
        """Initialize the SearchableMenu.
        
        Args:
            title (str): The menu title.
            parent (QtWidgets.QWidget, optional): Parent widget.
            enable_search (bool): Whether to enable search widget (default True).
            flat_results (bool): Whether to show results as flat list (default False).
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
        
        if enable_search:
            self._init_search_widget()
            # Connect to menu shown event to auto-focus search field
            self.aboutToShow.connect(self._on_menu_shown)
    
    def _init_search_widget(self):
        """Initialize and add the search widget to the menu."""
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
        
        # Add widget action to menu
        widget_action = QtWidgets.QWidgetAction(self)
        widget_action.setDefaultWidget(search_container)
        self.addAction(widget_action)
        
        # Add separator below search field
        self.addSeparator()
    
    def addAction(self, *args):
        """Override addAction to track menu items.
        
        Args:
            Can be called with (text), (icon, text), (text, callable),
            or (icon, text, callable) signatures.
        """
        action = super().addAction(*args)
        
        # Only track non-separator actions that aren't the search widget
        if action is not None and action.text():
            self._menu_items[action.text()] = action
        
        return action
    
    def addMenu(self, *args):
        """Override addMenu to track submenu actions.
        
        Args:
            Can be called with (menu), (title), or (icon, title).
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
        """Override addSeparator to track separators."""
        separator = super().addSeparator()
        self._separators.append(separator)
        return separator
    
    def _collect_flat_items(self):
        """Collect all items from menu and submenus as a flat list.
        
        Returns:
            list: List of tuples (action, category_name)
        """
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
        """Recursively collect items from a submenu.
        
        Args:
            menu (QtWidgets.QMenu): The submenu to collect items from.
            category_name (str): The category/parent menu name.
            
        Returns:
            list: List of tuples (action, category_name)
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
        """Show search results as a flat list.
        
        Args:
            search_text (str): The search/filter text.
        """
        actions = self.actions()
        skip_count = 2 if self._enable_search else 0
        
        # Hide all original menu items
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
                # Create new action with category prefix
                if category:
                    display_text = f"{action.text()} ({category})"
                else:
                    display_text = action.text()
                
                result_action = self.addAction(display_text)
                # Connect to the original action's trigger
                result_action.triggered.connect(action.triggered)
                self._search_result_actions.append(result_action)
    
    def _filter_items(self, search_text):
        """Filter menu items based on search text.
        
        Args:
            search_text (str): The search/filter text.
        """
        search_text = search_text.lower().strip()
        
        if self._flat_results and search_text:
            # Show results as flat list
            self._show_flat_results(search_text)
        else:
            # Show results with hierarchy
            self._show_hierarchical_results(search_text)
    
    def _show_hierarchical_results(self, search_text):
        """Show search results maintaining menu hierarchy.
        
        Args:
            search_text (str): The search/filter text.
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
        """Recursively filter a submenu and its items.
        
        Args:
            menu (QtWidgets.QMenu): The submenu to filter.
            search_text (str): The search/filter text.
            
        Returns:
            bool: True if submenu has any visible items.
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
        """Check if an action is a separator.
        
        Args:
            action (QtWidgets.QAction): The action to check.
            
        Returns:
            bool: True if the action is a separator.
        """
        return action in self._separators
    
    def _update_separator_visibility(self, actions):
        """Update separator visibility based on adjacent items.
        
        Separators should only be visible if they have visible items
        on both sides.
        
        Args:
            actions (list): List of actions to process.
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
        """Clear the search field and show all items."""
        if self._search_field:
            self._search_field.clear()
    
    def _on_menu_shown(self):
        """Handle menu shown event - auto-focus search field."""
        if self._search_field:
            self._search_field.setFocus()
            self._search_field.selectAll()
    
    def get_visible_items(self):
        """Get list of currently visible menu items.
        
        Returns:
            list: List of visible action texts.
        """
        visible = []
        skip_count = 2 if self._enable_search else 0
        
        for action in self.actions()[skip_count:]:
            if action.isVisible() and action.text():
                visible.append(action.text())
        return visible

