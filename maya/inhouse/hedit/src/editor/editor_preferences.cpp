/** @file editor_preferences.cpp
 * @brief EditorPreferencesと設定の表。
 */
#include "editor/editor_preferences.h"
#include <QSettings>
#include <QtGlobal>

namespace hedit {

const QList<OptionDefinition>& optionDefinitions() {
    // メニューに並ぶ順番。separatorBeforeがtrueの項目の前に区切り線が入る。
    static const QList<OptionDefinition> options = {
        {"completeLetters", "Completion while typing", true},
        {"completeDot", "Completion after dot", true},
        {"includeKeywords", "Include Python keywords", true},
        {"includeBuiltins", "Include Python built-ins", true},
        {"staticAnalysis", "Static analysis (syntax / warnings)", false},
        {"outputLineNumbers", "Show output line numbers", false},
        {"outputWrap", "Wrap output lines", false},
        {"spellCheck", "Spell check (English)", true},
        {"smartIndent", "Smart indentation", true, true},
        {"backspaceIndent", "Backspace to indentation stop", true},
        {"whitespace", "Show spaces and tabs", false},
        {"trimWhitespace", "Trim trailing spaces on file save", false, true},
        {"finalNewline", "Ensure final newline on file save", false},
    };
    return options;
}

EditorPreferences::EditorPreferences(const QString& iniPath) {
    if (!iniPath.isEmpty()) {
        settings_ = std::make_unique<QSettings>(iniPath, QSettings::IniFormat);
    }
    for (const OptionDefinition& definition : optionDefinitions()) {
        bool value = definition.defaultValue;
        if (settings_) {
            value = settings_->value(definition.key, definition.defaultValue).toBool();
        }
        values_.insert(definition.key, value);
    }
    if (settings_) {
        fontPixels_ = settings_->value("fontPixels", kDefaultFontPixels).toInt();
    }
}

// unique_ptr<QSettings>を破棄するにはQSettingsの完全な定義が必要なので、デストラクターは.cppに置く。
EditorPreferences::~EditorPreferences() = default;

bool EditorPreferences::option(const QString& key) const {
    return values_.value(key);
}

bool EditorPreferences::setOption(const QString& key, bool enabled) {
    values_[key] = enabled;
    if (!settings_) {
        return true;
    }
    settings_->setValue(key, enabled);
    settings_->sync();  // すぐにファイルへ書く(Mayaが落ちても設定を失わない)。
    return settings_->status() == QSettings::NoError;
}

bool EditorPreferences::resetToDefaults() {
    for (const OptionDefinition& definition : optionDefinitions()) {
        values_[definition.key] = definition.defaultValue;
    }
    fontPixels_ = kDefaultFontPixels;
    if (!settings_) {
        return true;
    }
    for (const OptionDefinition& definition : optionDefinitions()) {
        settings_->remove(definition.key);
    }
    settings_->remove("fontPixels");
    settings_->sync();
    return settings_->status() == QSettings::NoError;
}

void EditorPreferences::setFontPixels(int pixels) {
    fontPixels_ = qBound(10, pixels, 28);
    if (settings_) {
        settings_->setValue("fontPixels", fontPixels_);
        settings_->sync();
    }
}

}  // namespace hedit
