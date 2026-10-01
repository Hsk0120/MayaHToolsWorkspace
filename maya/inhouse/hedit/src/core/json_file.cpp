/** @file json_file.cpp
 * @brief 状態ファイルの読み書きの実装。
 */
#include "core/json_file.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>

namespace hedit {

bool readJsonFile(const QString& path, QJsonObject* object, QString* error) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        if (error && file.exists()) {
            *error = file.errorString();
        }
        return false;
    }
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        if (error) {
            *error = parseError.error != QJsonParseError::NoError ? parseError.errorString() : QString("not an object");
        }
        return false;
    }
    *object = document.object();
    return true;
}

bool writeJsonFile(const QString& path, const QJsonObject& object, QString* error) {
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) {
        if (error) {
            *error = "cannot create the folder";
        }
        return false;
    }
    const QByteArray bytes = QJsonDocument(object).toJson();
    QSaveFile file(path);
    const bool written = file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
    if (!written && error) {
        *error = file.errorString();
    }
    return written;
}

bool updateJsonFile(const QString& path, const QString& key, const QJsonValue& value, QString* error) {
    // 読み直してから1項目だけ変える(別のMayaが変えた他の項目を消さないため)。
    // 読めない(壊れた)ファイルは、空から作り直す。
    QJsonObject object;
    readJsonFile(path, &object);
    if (value.isUndefined()) {
        object.remove(key);
    } else {
        object.insert(key, value);
    }
    return writeJsonFile(path, object, error);
}

}  // namespace hedit
