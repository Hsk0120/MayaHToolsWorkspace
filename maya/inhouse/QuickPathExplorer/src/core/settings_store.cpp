/** @file settings_store.cpp @brief QSaveFileとQLockFileによる設定更新。 */
#include "settings_store.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonArray>
#include <QLockFile>
#include <QSaveFile>
#include <QStandardPaths>
#include <QThread>
#include <QKeySequence>
#include <QSet>
#include <cmath>
#include <stdexcept>
namespace qpe {
namespace {
/** @brief 環境非依存の移植対象キー。 @return キー一覧。 */
QStringList portableKeys() { return {"preferences", "commandKeys", "readPresets", "mayaAppearance", "standaloneAppearance", "standaloneTheme", "nativeReadOptions", "nativeReadPresets", "nativeMayaAppearance", "nativeAppearance"}; }
/** @brief 明示選択時だけ含めるコンピューター固有設定。 @return キー一覧。 */
QStringList localKeys() { return {"favorites", "savedSearches", "fileLabels", "folderViews", "previewExecutable", "everythingExecutable", "tabSets", "nativeTabSets", "fileLocksmith", "fileLocksmithExecutable", "ffmpegExecutable", "pathHistory"}; }
/** @brief JSON整数を暗黙変換せず検証する。 @param value 入力。 @param low 最小。 @param high 最大。 @return 範囲内整数か。 */
bool integerIn(const QJsonValue& value, double low, double high) { return value.isDouble() && std::floor(value.toDouble()) == value.toDouble() && value.toDouble() >= low && value.toDouble() <= high; }
/** @brief 必須でない整数フィールドを検証する。 @param object 入力。 @param key キー。 @param low 最小。 @param high 最大。 */
void checkInteger(const QJsonObject& object, const QString& key, double low, double high) { if (object.contains(key) && !integerIn(object[key], low, high)) throw std::invalid_argument(("Invalid setting: " + key).toStdString()); }
/** @brief 文字列配列以外を拒否する。 @param value 入力。 */
void checkStrings(const QJsonValue& value) { if (!value.isArray()) throw std::invalid_argument("Expected a string array"); for (const auto& item : value.toArray()) if (!item.isString()) throw std::invalid_argument("Expected a string array"); }
}
void validateCommandKeys(const QJsonObject& keys) {
    const QSet<QString> reserved{"Ctrl+C", "Ctrl+X", "Ctrl+V", "Ctrl+Z", "Ctrl+Y", "Ctrl+F", "Ctrl+T", "Ctrl+W", "Ctrl+Tab", "Ctrl+Shift+Tab", "Ctrl+Shift+T", "Ctrl+L", "Ctrl++", "Ctrl+=", "Ctrl+-", "Ctrl+0", "Ctrl+Shift+N", "Alt+Left", "Alt+Right", "Alt+Up"};
    QSet<QString> used;
    for (auto it = keys.begin(); it != keys.end(); ++it) {
        if (!it.value().isString()) throw std::invalid_argument("Invalid shortcut value");
        if (it.value().toString().isEmpty()) continue;
        const auto sequence = QKeySequence::fromString(it.value().toString(), QKeySequence::PortableText);
        const auto value = sequence.toString(QKeySequence::PortableText);
        if (sequence.isEmpty() || sequence.count() != 1 || value.endsWith('+') && value != "Ctrl++" || (!value.startsWith("Ctrl+") && !value.startsWith("Alt+")) || reserved.contains(value) || used.contains(value))
            throw std::invalid_argument("Use unique Ctrl/Alt shortcuts; standard file-operation keys are reserved");
        used.insert(value);
    }
}
void exportPreferences(const QString& path, bool includeLocal) {
    const auto current = readSettings(); QJsonObject values;
    for (const auto& key : portableKeys() + (includeLocal ? localKeys() : QStringList{})) if (current.contains(key) && key != "previewExecutable") values[key] = current[key];
    saveJson(path, {{"format", "qpe.preferences"}, {"version", 1}, {"settings", values}});
}
void importPreferences(const QString& path) {
    if (!QFileInfo(path).isFile() || QFileInfo(path).size() > 8 * 1024 * 1024) throw std::invalid_argument("Settings file is missing or exceeds 8 MiB");
    const auto document = loadJson(path);
    if (document["format"].toString() != "qpe.preferences" || !integerIn(document["version"], 1, 1) || !document["settings"].isObject()) throw std::invalid_argument("Unsupported settings format / version");
    auto values = document["settings"].toObject();
    const auto allowed = portableKeys() + localKeys();
    for (auto it = values.begin(); it != values.end(); ++it) {
        if (!allowed.contains(it.key())) throw std::invalid_argument(("Unknown setting: " + it.key()).toStdString());
        if (QStringList{"favorites", "pathHistory"}.contains(it.key())) checkStrings(it.value());
        else if (it.key().endsWith("Executable") || QStringList{"standaloneTheme", "fileLocksmith"}.contains(it.key())) { if (!it.value().isString()) throw std::invalid_argument("Expected string setting"); }
        else if (!it.value().isObject()) throw std::invalid_argument(("Expected object setting: " + it.key()).toStdString());
    }
    const auto searches = values["savedSearches"].toObject();
    for (auto it = searches.begin(); it != searches.end(); ++it) {
        if (!it.value().isObject()) throw std::invalid_argument("Invalid saved search"); const auto item = it.value().toObject();
        for (const auto& key : {"root", "query", "extensions", "content", "exclude", "tags", "tagMode", "kind"}) if (item.contains(key) && !item[key].isString()) throw std::invalid_argument("Invalid saved search field");
        for (const auto& key : {"days", "minimum", "maximum"}) checkInteger(item, key, 0, 9007199254740991.0);
    }
    const auto preferences = values["preferences"].toObject(); checkInteger(preferences, "undoDays", 1, 3650); checkInteger(preferences, "undoMiB", 1, 1048576);
    validateCommandKeys(values["commandKeys"].toObject());
    const auto views = values["folderViews"].toObject();
    for (auto it = views.begin(); it != views.end(); ++it) {
        if (!it.value().isObject()) throw std::invalid_argument("Invalid folder display settings"); const auto item = it.value().toObject();
        checkInteger(item, "mode", 0, 2); checkInteger(item, "group", 0, 4); checkInteger(item, "sort", 0, 8);
        for (const auto& key : {"hidden", "widths"}) if (item.contains(key)) {
            if (!item[key].isArray()) throw std::invalid_argument("Invalid column settings");
            for (const auto& number : item[key].toArray()) if (!integerIn(number, QString(key) == "hidden" ? 1 : 0, QString(key) == "hidden" ? 8 : 10000)) throw std::invalid_argument("Invalid column dimensions");
        }
    }
    const auto labels = values["fileLabels"].toObject();
    for (auto it = labels.begin(); it != labels.end(); ++it) {
        if (!it.value().isObject()) throw std::invalid_argument("Invalid file label"); const auto item = it.value().toObject();
        if (item.contains("tags")) checkStrings(item["tags"]); checkInteger(item, "rating", 0, 5);
    }
    for (const auto& key : {"nativeMayaAppearance", "nativeAppearance"}) {
        const auto appearance = values[key].toObject(); checkInteger(appearance, "textSize", 10, 24);
        if (appearance.contains("theme") && !QStringList{"system", "dark", "light"}.contains(appearance["theme"].toString())) throw std::invalid_argument("Invalid theme");
    }
    // 関連付けアプリを使う現在の仕様では、旧版の独自ビューアーパスを復活させない。
    values.remove("previewExecutable"); writeSettings(values);
}
QJsonValue remapPaths(const QJsonValue& value, const QString& from, const QString& to) {
    if (value.isString()) { const auto normalized = QDir::fromNativeSeparators(value.toString()); const auto before = QDir::fromNativeSeparators(from);
        if (normalized.compare(before, Qt::CaseInsensitive) == 0 || normalized.startsWith(before + '/', Qt::CaseInsensitive)) return QDir::fromNativeSeparators(to) + normalized.mid(before.size());
    } else if (value.isArray()) { QJsonArray result; for (const auto& item : value.toArray()) result.append(remapPaths(item, from, to)); return result; }
    else if (value.isObject()) { QJsonObject result; const auto object = value.toObject(); for (auto it = object.begin(); it != object.end(); ++it) result[remapPaths(it.key(), from, to).toString()] = remapPaths(it.value(), from, to); return result; }
    return value;
}
QString settingsPath() {
    const auto overridePath = qEnvironmentVariable("QPE_SETTINGS_FILE");
    return overridePath.isEmpty() ? QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)
        + "/QuickPathExplorer/settings.json" : overridePath;
}
QJsonObject loadJson(const QString& path) {
    QFile file(path);
    if (!file.exists()) return {};
    if (!file.open(QIODevice::ReadOnly)) throw std::runtime_error((path + ": " + file.errorString()).toStdString());
    QJsonParseError error;
    const auto doc = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject())
        throw std::runtime_error(("Invalid JSON (original retained): " + path).toStdString());
    return doc.object();
}
QJsonObject readSettings() { return loadJson(settingsPath()); }
QJsonObject readOptionsFromSettings(const QJsonObject& state) {
    auto result = state["readOptions"].toObject();
    result["fbx"] = state["fbxOpenOptions"].toObject();
    const auto native = state["nativeReadOptions"].toObject();
    for (auto it = native.begin(); it != native.end(); ++it) result[it.key()] = it.value();
    return result;
}
QJsonObject readPresetsFromSettings(const QJsonObject& state, const QString& action) {
    QJsonObject result;
    const auto legacy = state["readPresets"].toObject();
    for (auto it = legacy.begin(); it != legacy.end(); ++it) {
        const QJsonValue value = it.value().toObject().value(action);
        if (value.isObject()) result[it.key()] = value;
    }
    const QJsonValue native = state["nativeReadPresets"].toObject().value(action);
    // 操作別の保存が始まった後は、削除した旧名を次の起動で復活させない。
    return native.isObject() ? native.toObject() : result;
}
void saveJson(const QString& path, const QJsonObject& value) {
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) throw std::runtime_error("Could not create settings directory");
    const auto data = QJsonDocument(value).toJson();
    QString error;
    // Windowsの読取側が短時間共有削除を許可していない場合だけ、同じ原子的置換を再試行する。
    // 既存ファイルを先に削除したり、権限を変えたりするフォールバックは設けない。
    for (int attempt = 0; attempt < 6; ++attempt) {
        QSaveFile file(path); file.setDirectWriteFallback(false);
        if (file.open(QIODevice::WriteOnly) && file.write(data) == data.size() && file.commit()) return;
        error = path + ": " + file.errorString();
        if (file.error() != QFileDevice::PermissionsError && file.error() != QFileDevice::RenameError) break;
        if (attempt < 5) QThread::msleep(15u << attempt);
    }
    throw std::runtime_error(error.toStdString());
}
void writeSettings(const QJsonObject& changes) {
    const QString path = settingsPath();
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) throw std::runtime_error("Could not create settings directory");
    QLockFile lock(path + ".lock");
    if (!lock.tryLock(250)) throw std::runtime_error("Another QPE is updating settings; retry shortly");
    auto value = loadJson(path);
    bool changed = false;
    for (auto it = changes.begin(); it != changes.end(); ++it) {
        if (value.value(it.key()) != it.value()) { value.insert(it.key(), it.value()); changed = true; }
    }
    if (changed) saveJson(path, value);
}
void mergeSettingsMap(const QString& key, const QJsonObject& changes) {
    const auto path = settingsPath(); if (!QDir().mkpath(QFileInfo(path).absolutePath())) throw std::runtime_error("Could not create settings directory");
    QLockFile lock(path + ".lock"); if (!lock.tryLock(250)) throw std::runtime_error("Another QPE is updating settings; retry shortly");
    auto state = loadJson(path); auto values = state[key].toObject(); const auto previous = values;
    for (auto it = changes.begin(); it != changes.end(); ++it) values[it.key()] = it.value();
    if (values != previous) { state[key] = values; saveJson(path, state); }
}

}
