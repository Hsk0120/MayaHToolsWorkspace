# -*- coding: utf-8 -*-
"""User setup for HTools menu in Maya."""
import maya.utils as maya_utils
import importlib
import inspect
import os
import sys
from datetime import datetime
from pathlib import Path
import maya.OpenMayaUI as omui
import runpy
import maya.cmds as cmds
import maya.mel as mel

try:
    from PySide6 import QtWidgets, QtGui
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtWidgets, QtGui
    import shiboken2 as shiboken

try:
    QACTION_CLASS = QtGui.QAction
except AttributeError:
    QACTION_CLASS = QtWidgets.QAction


INHOUSE_TRACE_FILE_NAME = "usersetup_trace.log"
INHOUSE_TRACE_SCRIPT_NAME = "inhouse"


def _inhouse_get_trace_file_path():
    maya_app_dir = os.environ.get("MAYA_APP_DIR")
    if not maya_app_dir:
        maya_app_dir = str(Path.home() / "Documents" / "maya")
    return str(Path(maya_app_dir) / INHOUSE_TRACE_FILE_NAME)


def _inhouse_get_trace_session():
    session = os.environ.get("MAYA_USERSETUP_TRACE_SESSION")
    if session:
        return session
    session = f"pid{os.getpid()}"
    os.environ["MAYA_USERSETUP_TRACE_SESSION"] = session
    return session


def _inhouse_trace_event(phase, detail=""):
    if os.environ.get("MAYA_USERSETUP_TRACE") != "1":
        return

    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    message = (
        f"[userSetupTrace] {timestamp} | {_inhouse_get_trace_session()} | "
        f"{INHOUSE_TRACE_SCRIPT_NAME} | {phase} | {detail}"
    )
    print(message)
    try:
        with open(_inhouse_get_trace_file_path(), "a", encoding="utf-8") as stream:
            stream.write(message + "\n")
    except Exception:
        pass


def _inhouse_get_maya_main_window():
    """Get Maya main window as a QWidget.
    
    Returns:
        QtWidgets.QWidget: Maya main window widget.
    """
    main_window_ptr = omui.MQtUtil.mainWindow()
    return shiboken.wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


def _inhouse_is_already_initialized():
    return os.environ.get("MAYA_INHOUSE_USERSETUP_INITIALIZED") == "1"


def _inhouse_mark_initialized():
    os.environ["MAYA_INHOUSE_USERSETUP_INITIALIZED"] = "1"


def _inhouse_execute_module(module_name):
    """Execute a Python module as __main__.

    Args:
        module_name (str): Full module name to execute.
    """
    def callback(*_):
        runpy.run_module(module_name, run_name='__main__')
    return callback


def _inhouse_get_searchable_menu_class():
    current_file = Path(inspect.getfile(inspect.currentframe()))
    htools_dir = current_file.parent
    htools_dir_path = str(htools_dir)
    if htools_dir_path not in sys.path:
        sys.path.insert(0, htools_dir_path)

    module = importlib.import_module("searchable_menu")
    return module.SearchableMenu


def _inhouse_ensure_hotbox_menu_proxy(menu_name, menu_label):
    """Hotbox(MEL)照会用の不可視プロキシ menu を保証する。"""
    try:
        if cmds.menu(menu_name, exists=True):
            try:
                cmds.menu(
                    menu_name,
                    edit=True,
                    label=menu_label,
                    visible=False,
                )
            except Exception:
                pass
            _inhouse_trace_event("menu_proxy_ok", f"reuse:{menu_name}")
            return

        main_window = mel.eval("$tmp=$gMainWindow")
        cmds.menu(
            menu_name,
            parent=main_window,
            label=menu_label,
            tearOff=False,
            visible=False,
        )
        _inhouse_trace_event("menu_proxy_ok", f"create:{menu_name}")
    except Exception as error:
        _inhouse_trace_event("menu_proxy_fail", f"{menu_name}:{error}")


def _inhouse_move_menu_before_help(menu_name):
    maya_window = _inhouse_get_maya_main_window()
    menu_bar = maya_window.findChild(QtWidgets.QMenuBar)
    if menu_bar is None:
        return

    target_action = None
    help_action = None
    for action in menu_bar.actions():
        label = action.text().strip()
        if label == menu_name:
            target_action = action
        if label == "Help":
            help_action = action

    if target_action is None:
        return

    target_qaction = (
        target_action.menuAction()
        if isinstance(target_action, QtWidgets.QMenu)
        else target_action
    )
    help_qaction = (
        help_action.menuAction()
        if isinstance(help_action, QtWidgets.QMenu)
        else help_action
    )

    if help_qaction is not None and target_qaction is not help_qaction:
        menu_bar.removeAction(target_qaction)
        menu_bar.insertAction(help_qaction, target_qaction)

    target_qaction.setVisible(True)
    target_qaction.setEnabled(True)


def _inhouse_add_htools_menu_items(main_menu):
    """Add menu items to the specified menu.

    Args:
        main_menu: Main Qt menu object.
    """
    current_file = Path(inspect.getfile(inspect.currentframe()))
    HTools_dir = current_file.parent

    # Get list of folders in HTools directory
    folders = [
        d.name
        for d in HTools_dir.iterdir()
        if d.is_dir() and not d.name.startswith("__")
    ]
    print("folders:", folders)
    
    # Sort folders alphabetically
    folders.sort()

    for folder in folders:
        submenu_result = main_menu.addMenu(folder)
        submenu = submenu_result
        if isinstance(submenu_result, QACTION_CLASS):
            submenu = submenu_result.menu()
        elif isinstance(submenu_result, QtWidgets.QMenu):
            submenu = submenu_result
        if not hasattr(submenu, "addAction"):
            continue
        if hasattr(submenu, "setTearOffEnabled"):
            submenu.setTearOffEnabled(True)
        
        # Get Python files in folder
        py_files = []
        for file in Path(HTools_dir / folder).iterdir():
            print("file:", file)
            if "__init__.py" in file.name:
                continue
            if ".py" in file.name:
                py_files.append(file.stem)
        
        # Sort files alphabetically
        py_files.sort()
        
        # Add menu items
        for tool in py_files:
            module_name = f"HTools.{folder}.{tool}"
            action = submenu.addAction(tool)
            action.triggered.connect(_inhouse_execute_module(module_name))


def _inhouse_install_htools_menu():
    """Install HTools menu in Maya."""
    print("Installing HTools menu...")
    main_menu_name = "HTools"

    _inhouse_trace_event("menu_create_start", main_menu_name)
    try:
        _inhouse_ensure_hotbox_menu_proxy(main_menu_name, "HToolsProxy")

        maya_window = _inhouse_get_maya_main_window()
        menu_bar = maya_window.findChild(QtWidgets.QMenuBar)
        if menu_bar is None:
            raise RuntimeError("Could not find Maya menu bar")

        for action in menu_bar.actions():
            if action.text().strip() == main_menu_name:
                menu = None
                if isinstance(action, QACTION_CLASS):
                    menu = action.menu()
                elif isinstance(action, QtWidgets.QMenu):
                    menu = action
                remove_action = (
                    action.menuAction()
                    if isinstance(action, QtWidgets.QMenu)
                    else action
                )
                menu_bar.removeAction(remove_action)
                if menu is not None:
                    menu.deleteLater()
                if hasattr(action, "deleteLater"):
                    action.deleteLater()

        searchable_menu_class = _inhouse_get_searchable_menu_class()
        main_menu = searchable_menu_class(
            main_menu_name,
            menu_bar,
            enable_search=True,
            flat_results=True,
        )
        main_menu.setObjectName(main_menu_name)
        main_menu.setTearOffEnabled(True)

        help_menu_action = None
        for action in menu_bar.actions():
            if action.text().strip() == "Help":
                help_menu_action = action
                break

        if help_menu_action is not None:
            menu_bar.insertMenu(help_menu_action, main_menu)
        else:
            menu_bar.addMenu(main_menu)

        _inhouse_move_menu_before_help(main_menu_name)
        cmds.evalDeferred(
            lambda: _inhouse_move_menu_before_help(main_menu_name),
            lowestPriority=True,
        )

        _inhouse_add_htools_menu_items(main_menu)

        menu_exists = any(
            action.text().strip() == main_menu_name for action in menu_bar.actions()
        )
        if not menu_exists:
            raise RuntimeError(f"Failed to create menu: {main_menu_name}")

        _inhouse_trace_event("menu_create_ok", main_menu_name)
    except Exception as error:
        _inhouse_trace_event("menu_create_fail", f"{main_menu_name}:{error}")
        try:
            maya_window = _inhouse_get_maya_main_window()
            menu_bar = maya_window.findChild(QtWidgets.QMenuBar)
            if menu_bar is not None:
                for action in menu_bar.actions():
                    if action.text().strip() == main_menu_name:
                        menu = None
                        if isinstance(action, QACTION_CLASS):
                            menu = action.menu()
                        elif isinstance(action, QtWidgets.QMenu):
                            menu = action
                        remove_action = (
                            action.menuAction()
                            if isinstance(action, QtWidgets.QMenu)
                            else action
                        )
                        menu_bar.removeAction(remove_action)
                        if menu is not None:
                            menu.deleteLater()
                        if hasattr(action, "deleteLater"):
                            action.deleteLater()
                        _inhouse_trace_event("menu_cleanup_done", main_menu_name)
                        break
        except Exception as cleanup_error:
            _inhouse_trace_event(
                "menu_cleanup_fail",
                f"{main_menu_name}:{cleanup_error}",
            )
        cmds.warning(f"[userSetup] Failed to install {main_menu_name}: {error}")


def _inhouse_open_command_ports():
    print("[userSetup] commandPort initialization start")
    port_settings = (
        (":7001", "mel"),
        (":7002", "python"),
    )

    for port_name, source_type in port_settings:
        try:
            is_open = cmds.commandPort(port_name, q=True)
        except Exception:
            is_open = False

        if is_open:
            print(f"[userSetup] commandPort {port_name} ({source_type}) already open")
            continue

        try:
            cmds.commandPort(name=port_name, sourceType=source_type, echoOutput=False)
            print(f"[userSetup] commandPort {port_name} ({source_type}) opened")
        except Exception as error:
            cmds.warning(f"Failed to open commandPort {port_name} ({source_type}): {error}")

    print("[userSetup] commandPort initialization done")


def _inhouse_install_htools_menu_deferred():
    _inhouse_trace_event("deferred_start", "_inhouse_install_htools_menu")
    try:
        _inhouse_install_htools_menu()
    except Exception as error:
        _inhouse_trace_event(
            "deferred_fail",
            f"_inhouse_install_htools_menu:{error}",
        )
        cmds.warning(f"[userSetup] deferred install failed: {error}")
    finally:
        _inhouse_trace_event("deferred_end", "_inhouse_install_htools_menu")


def _inhouse_open_command_ports_deferred():
    _inhouse_trace_event("deferred_start", "_inhouse_open_command_ports")
    try:
        _inhouse_open_command_ports()
    finally:
        _inhouse_trace_event("deferred_end", "_inhouse_open_command_ports")


def _inhouse_install_optional_external_tools():
    """Initialize optional external tools without hard dependency."""
    _inhouse_trace_event("optional_tools_start", "jlr_sort_attributes")
    try:
        jlr_sort_attributes = importlib.import_module("jlr_sort_attributes")

        cmds.evalDeferred(
            lambda: jlr_sort_attributes.create_menu_commands(),
            lowestPriority=True,
        )
        _inhouse_trace_event("optional_tools_ok", "jlr_sort_attributes")
    except Exception as error:
        _inhouse_trace_event("optional_tools_skip", f"jlr_sort_attributes:{error}")


def _inhouse_eval_deferred_low_priority(callback, trace_detail):
    _inhouse_trace_event("register", f"evalDeferred(lowestPriority):{trace_detail}")
    try:
        cmds.evalDeferred(callback, lowestPriority=True)
    except Exception:
        _inhouse_trace_event("register", f"executeDeferred(fallback):{trace_detail}")
        maya_utils.executeDeferred(callback)

if _inhouse_is_already_initialized():
    _inhouse_trace_event("skip", "already_initialized")
    print("[userSetup] already initialized in this Maya session")
elif cmds.about(batch=True):
    _inhouse_trace_event("skip", "batch_mode")
    print("[userSetup] skip in batch mode")
else:
    _inhouse_trace_event("register", "mark_initialized")
    _inhouse_mark_initialized()
    _inhouse_eval_deferred_low_priority(
        _inhouse_install_htools_menu_deferred,
        "_inhouse_install_htools_menu",
    )
    _inhouse_trace_event("register", "executeDeferred:_inhouse_open_command_ports")
    maya_utils.executeDeferred(_inhouse_open_command_ports_deferred)
    _inhouse_trace_event("register", "executeDeferred:_inhouse_install_optional_external_tools")
    maya_utils.executeDeferred(_inhouse_install_optional_external_tools)