/** @file editor_preferences.h
 * @brief Edit > Preferences のオン・オフ設定と文字サイズを、preferences.iniへ保存する。
 * @details 設定を追加するときは、editor_preferences.cppのkOptionsの表に1行足す
 * (docs/development.rstの「設定項目を追加する」参照)。
 */
#pragma once
#include <QHash>
#include <QList>
#include <QString>
#include <memory>

class QSettings;

namespace hedit {

/** @brief 設定の保存名(preferences.iniのキー)。打ち間違いを防ぐため、文字列は必ずこの定数を使う。
 * @note 一度公開した保存名は変えない(変えると利用者の保存済みの設定が読まれなくなる)。
 */
namespace option {
constexpr const char* kCompleteLetters = "completeLetters";       ///< 入力中の自動補完。
constexpr const char* kCompleteDot = "completeDot";               ///< 点の直後の自動補完。
constexpr const char* kIncludeKeywords = "includeKeywords";       ///< 候補に予約語を含める。
constexpr const char* kIncludeBuiltins = "includeBuiltins";       ///< 候補に組み込みの名前を含める。
constexpr const char* kStaticAnalysis = "staticAnalysis";         ///< 構文チェック。
constexpr const char* kOutputLineNumbers = "outputLineNumbers";   ///< 出力欄の行番号。
constexpr const char* kOutputWrap = "outputWrap";                 ///< 出力欄の折り返し。
constexpr const char* kSpellCheck = "spellCheck";                 ///< 英語のスペルチェック。
constexpr const char* kSmartIndent = "smartIndent";               ///< Enterでインデントを引き継ぐ。
constexpr const char* kBackspaceIndent = "backspaceIndent";       ///< Backspaceを4文字単位で消す。
constexpr const char* kWhitespace = "whitespace";                 ///< 空白とタブを記号で表示する。
constexpr const char* kTrimWhitespace = "trimWhitespace";         ///< 保存時に行末の空白を消す。
constexpr const char* kFinalNewline = "finalNewline";             ///< 保存時に末尾の改行を補う。
}  // namespace option

/** @brief 1つのオン・オフ設定の定義。 */
struct OptionDefinition {
    const char* key;              ///< 保存名(preferences.iniのキー)。一度公開したら変えない。
    const char* label;            ///< メニューの表示名。
    bool defaultValue;            ///< 初期値。
    bool separatorBefore = false; ///< メニューでこの項目の前に区切り線を入れるか。
};

/** @brief 全ての設定の定義を、メニューに並べる順で返す。 @return 設定の表。 */
const QList<OptionDefinition>& optionDefinitions();

/** @brief 設定の値を保持し、変更をpreferences.iniへ保存する。 */
class EditorPreferences {
public:
    /// 文字サイズの初期値(100%時のピクセル数)。
    static constexpr int kDefaultFontPixels = 14;

    /** @brief 保存済みの値を読み込む。保存が無い設定は初期値になる。
     * @param iniPath preferences.iniの絶対パス。空なら保存せず、全て初期値のまま使う。
     */
    explicit EditorPreferences(const QString& iniPath);

    /** @brief QSettingsを閉じる。 */
    ~EditorPreferences();

    /** @brief 設定の値を返す。 @param key 保存名。 @return オンならtrue。未登録の名前はfalse。 */
    bool option(const QString& key) const;

    /** @brief 設定を変えて保存する。
     * @param key 保存名。
     * @param enabled 新しい値。
     * @return 保存できた(または保存先が無い)ならtrue。書き込みに失敗したらfalse。
     */
    bool setOption(const QString& key, bool enabled);

    /** @brief コード欄の文字サイズ(100%のときのピクセル数)。 @return 10〜28。 */
    int fontPixels() const { return fontPixels_; }

    /** @brief 文字サイズを変えて保存する。 @param pixels 10〜28の範囲に丸める。 */
    void setFontPixels(int pixels);

    /** @brief 全ての設定と文字サイズを初期値に戻す。
     * @return 保存できた(または保存先が無い)ならtrue。書き込みに失敗したらfalse。
     * @details preferences.iniからheditの項目を消す(値が無い項目は初期値として扱われる)。
     * 項目を消すので、将来初期値を変えたときも新しい初期値が使われる。
     */
    bool resetToDefaults();

private:
    std::unique_ptr<QSettings> settings_;  ///< 保存先。保存しない場合はnullptr。
    QHash<QString, bool> values_;          ///< 設定の現在の値。
    int fontPixels_ = kDefaultFontPixels;  ///< 文字サイズ。
};

}  // namespace hedit
