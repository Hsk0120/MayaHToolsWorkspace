"""PySide6(Maya 2025以降)と PySide2(Maya 2024以前)を同じ名前で使えるようにする。"""

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

__all__ = ["QtCore", "QtGui", "QtWidgets", "wrapInstance"]
