#pragma once
#include <QMainWindow>
#include <functional>

namespace heditor {
using Execute = std::function<QString(const QString&)>;
using Configuration = std::function<QByteArray()>;
using OutputReader = std::function<QString()>;
QMainWindow* createEditor(QWidget* parent, Execute execute, Configuration configuration, OutputReader outputReader = {});
}
