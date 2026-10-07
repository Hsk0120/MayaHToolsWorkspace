/** @file editor_preferences.cpp
 * @brief EditorPreferencesと設定の表。
 */
#include "editor/editor_preferences.h"
#include "core/json_file.h"
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonObject>
#include <QSettings>
#include <QtGlobal>

namespace hedit {

const QList<OptionDefinition>& optionDefinitions() {
    // メニューに並ぶ順番。separatorBeforeがtrueの項目の前に区切り線が入る。
    static const QList<OptionDefinition> options = {
        {option::kCompleteLetters, "Completion while typing", true},
        {option::kCompleteDot, "Completion after dot", true},
        {option::kIncludeKeywords, "Include Python keywords", true},
        {option::kIncludeBuiltins, "Include Python built-ins", true},
        {option::kStaticAnalysis, "Static analysis (syntax / warnings)", false},
        {option::kOutputLineNumbers, "Show output line numbers", false},
        {option::kOutputWrap, "Wrap output lines", false},
        {option::kExactOutput, "Exact Script Editor output format (slower)", false},
        {option::kSpellCheck, "Spell check (English)", true},
        {option::kSmartIndent, "Smart indentation", true, true},
        {option::kBackspaceIndent, "Backspace to indentation stop", true},
        {option::kWhitespace, "Show spaces and tabs", false},
        {option::kTrimWhitespace, "Trim trailing spaces on file save", false, true},
        {option::kFinalNewline, "Ensure final newline on file save", false},
        {option::kAutoClosing, "Auto-close brackets and quotes", true, true},
        {option::kStickyScroll, "Sticky scroll (class / def headers)", true},
    };
    return options;
}

namespace {

/// 文字サイズの保存名。
constexpr const char* kFontPixelsKey = "fontPixels";

/// 最近開いたファイルの保存名と、残す件数。
constexpr const char* kRecentFilesKey = "recentFiles";
constexpr int kMaximumRecentFiles = 20;

/// メニューに無い表示の状態をまとめて保存する名前(``{"outlineVisible": true}``)。
constexpr const char* kFlagsKey = "viewState";

/** @brief 0.2.xのpreferences.iniの値を読む(移行用)。
 * @param iniPath preferences.iniのパス。
 * @return 保存されていた項目。ファイルが無ければ空。
 */
QJsonObject readLegacyIni(const QString& iniPath) {
    QJsonObject values;
    if (!QFileInfo::exists(iniPath)) {
        return values;
    }
    QSettings legacy(iniPath, QSettings::IniFormat);
    for (const OptionDefinition& definition : optionDefinitions()) {
        if (legacy.contains(definition.key)) {
            values.insert(definition.key, legacy.value(definition.key).toBool());
        }
    }
    if (legacy.contains(kFontPixelsKey)) {
        values.insert(kFontPixelsKey, legacy.value(kFontPixelsKey).toInt());
    }
    return values;
}

}  // namespace

EditorPreferences::EditorPreferences(const QString& path) : path_(path) {
    QJsonObject saved;
    if (!path_.isEmpty() && !readJsonFile(path_, &saved) && !QFileInfo::exists(path_)) {
        // 初めて0.3以降を使う: 同じフォルダーのpreferences.ini(0.2.x)の値を移す。iniは消さずに残す。
        saved = readLegacyIni(QFileInfo(path_).absolutePath() + "/preferences.ini");
        if (!saved.isEmpty()) {
            writeJsonFile(path_, saved);
        }
    }
    for (const OptionDefinition& definition : optionDefinitions()) {
        values_.insert(definition.key, saved.value(definition.key).toBool(definition.defaultValue));
    }
    fontPixels_ = qBound(10, saved.value(kFontPixelsKey).toInt(kDefaultFontPixels), 28);
    for (const QJsonValue& value : saved.value(kRecentFilesKey).toArray()) {
        if (value.isString() && !recentFiles_.contains(value.toString())) {
            recentFiles_.append(value.toString());
        }
    }
    const QJsonObject flags = saved.value(kFlagsKey).toObject();
    for (auto it = flags.begin(); it != flags.end(); ++it) {
        flags_.insert(it.key(), it.value().toBool());
    }
}

void EditorPreferences::addRecentFile(const QString& path) {
    recentFiles_.removeAll(path);
    recentFiles_.prepend(path);
    while (recentFiles_.size() > kMaximumRecentFiles) {
        recentFiles_.removeLast();
    }
    if (!path_.isEmpty()) {
        updateJsonFile(path_, kRecentFilesKey, QJsonArray::fromStringList(recentFiles_));
    }
}

void EditorPreferences::clearRecentFiles() {
    recentFiles_.clear();
    if (!path_.isEmpty()) {
        updateJsonFile(path_, kRecentFilesKey, QJsonArray());
    }
}

void EditorPreferences::setFlag(const QString& key, bool value) {
    flags_.insert(key, value);
    if (path_.isEmpty()) {
        return;
    }
    QJsonObject flags;
    for (auto it = flags_.begin(); it != flags_.end(); ++it) {
        flags.insert(it.key(), it.value());
    }
    updateJsonFile(path_, kFlagsKey, flags);
}

bool EditorPreferences::option(const QString& key) const {
    return values_.value(key);
}

bool EditorPreferences::setOption(const QString& key, bool enabled) {
    values_[key] = enabled;
    // 変えた項目だけを書き換える。すぐにファイルへ書くので、Mayaが落ちても設定を失わない。
    return path_.isEmpty() || updateJsonFile(path_, key, enabled);
}

bool EditorPreferences::resetToDefaults() {
    for (const OptionDefinition& definition : optionDefinitions()) {
        values_[definition.key] = definition.defaultValue;
    }
    fontPixels_ = kDefaultFontPixels;
    if (path_.isEmpty()) {
        return true;
    }
    // heditの項目を消す(値が無い項目は初期値として扱う)。知らない項目(新しい版の設定など)は残す。
    QJsonObject saved;
    readJsonFile(path_, &saved);
    for (const OptionDefinition& definition : optionDefinitions()) {
        saved.remove(definition.key);
    }
    saved.remove(kFontPixelsKey);
    return writeJsonFile(path_, saved);
}

void EditorPreferences::setFontPixels(int pixels) {
    fontPixels_ = qBound(10, pixels, 28);
    if (!path_.isEmpty()) {
        updateJsonFile(path_, kFontPixelsKey, fontPixels_);
    }
}

}  // namespace hedit
