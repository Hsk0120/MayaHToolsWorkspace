/** @file ui_language.h @brief QPEだけの表示翻訳。Mayaや他ツールのQt翻訳・ロケールは変更しない。 */
#pragma once
#include <QString>
#include <QStringList>
#include <QDialogButtonBox>
#include <QMessageBox>
#include <QLineEdit>
#include <QLocale>
namespace qpe {
/** @brief 保存されたUI言語を返す。未設定/未知の値は日本語。 @return jaまたはen。 */
QString savedUiLanguage();
/** @brief 現在構築中のQPEの言語を設定する。 @param language jaまたはen。 */
void setUiLanguage(const QString& language);
/** @brief 現在のQPE表示言語。 @return jaまたはen。 */
QString uiLanguage();
/** @brief 容量などUI文字の書式。Windowsの日時設定やアプリ全体の既定ロケールは変更しない。 @return QPE用ロケール。 */
const QLocale& uiLocale();
/** @brief 表示文字だけを翻訳する。パス・入力本文・保存IDには使わない。 @param source 英語原文。 @return 表示文字。 */
QString uiText(const QString& source);
/** @brief 表示専用リストを翻訳する。 @param source 英語原文。 @return 表示リスト。 */
QStringList uiTexts(const QStringList& source);
/** @brief 所有するダイアログの標準ボタンだけを翻訳する。 @param buttons QPEのボタン群。 */
void uiButtons(QDialogButtonBox* buttons);
/** @brief ユーザーの入力文字列を翻訳しない、QPE専用入力ダイアログ。 */
class UiInputDialog {
public:
    /** @brief 文字列を入力する。 @param parent 所有者。 @param title 題名。 @param label 説明。 @param mode 入力モード。 @param text 初期文字。 @param ok 確定結果。 @return 入力本文。 */
    static QString getText(QWidget* parent, const QString& title, const QString& label, QLineEdit::EchoMode mode = QLineEdit::Normal, const QString& text = {}, bool* ok = nullptr);
    /** @brief 項目を選ぶ。項目本文は翻訳しない。 @param parent 所有者。 @param title 題名。 @param label 説明。 @param items 項目。 @param current 選択位置。 @param editable 編集可否。 @param ok 確定結果。 @return 選択文字。 */
    static QString getItem(QWidget* parent, const QString& title, const QString& label, const QStringList& items, int current = 0, bool editable = true, bool* ok = nullptr);
};
/** @brief Qt標準メッセージをQPE内だけで日本語化する。 */
class UiMessageBox {
public:
    /** @brief 確認を表示する。 @param parent 所有者。 @param title 題名。 @param text 本文。 @param buttons 選択肢。 @param initial 既定。 @return 選択。 */
    static QMessageBox::StandardButton question(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons = QMessageBox::Yes | QMessageBox::No, QMessageBox::StandardButton initial = QMessageBox::NoButton);
    /** @brief 警告を表示する。 @param parent 所有者。 @param title 題名。 @param text 本文。 @param buttons 選択肢。 @param initial 既定。 @return 選択。 */
    static QMessageBox::StandardButton warning(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons = QMessageBox::Ok, QMessageBox::StandardButton initial = QMessageBox::NoButton);
    /** @brief 情報を表示する。 @param parent 所有者。 @param title 題名。 @param text 本文。 @param buttons 選択肢。 @param initial 既定。 @return 選択。 */
    static QMessageBox::StandardButton information(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons = QMessageBox::Ok, QMessageBox::StandardButton initial = QMessageBox::NoButton);
    /** @brief エラーを表示する。 @param parent 所有者。 @param title 題名。 @param text 本文。 @param buttons 選択肢。 @param initial 既定。 @return 選択。 */
    static QMessageBox::StandardButton critical(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons = QMessageBox::Ok, QMessageBox::StandardButton initial = QMessageBox::NoButton);
};
}
