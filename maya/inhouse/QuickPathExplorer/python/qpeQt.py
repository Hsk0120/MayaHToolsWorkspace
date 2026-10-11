"""MayaのQt6/Qt5に合うPythonバインディングだけを選択する。"""
try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg, QtTest
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets, QtSvg, QtTest
    import shiboken2 as shiboken

QAction = getattr(QtGui, 'QAction', None) or QtWidgets.QAction
