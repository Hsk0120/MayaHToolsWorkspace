/** @file ui_language.cpp @brief コンパイル済みの日本語辞書を使い、実行時の外部ファイルとQt全体の翻訳を不要にする。 */
#include "ui_language.h"
#include "../core/settings_store.h"
#include <QHash>
#include <QPushButton>
#include <QInputDialog>
#include <stdexcept>
namespace qpe {
namespace {
QString activeLanguage;
/** @brief 外部I/Oなしで参照する翻訳辞書。 @return 英語から日本語への対応。 */
const QHash<QString, QString>& catalog() {
    static const QHash<QString, QString> values{
#include "ui_ja.inc"
    };
    return values;
}
/** @brief 自分のメッセージボックスだけを構築し翻訳する。 @param parent 所有者。 @param icon 種別。 @param title 題名。 @param text 本文。 @param buttons 選択肢。 @param initial 既定。 @return 選択。 */
QMessageBox::StandardButton message(QWidget* parent, QMessageBox::Icon icon, const QString& title, const QString& text, QMessageBox::StandardButtons buttons, QMessageBox::StandardButton initial) {
    // 本文にはファイル名や入力値も来るため再翻訳しない。静的な本文は呼出元でuiTextする。
    QMessageBox box(icon, title, text, buttons, parent);
    const QList<QPair<QMessageBox::StandardButton, QString>> labels{{QMessageBox::Ok,"OK"},{QMessageBox::Cancel,"Cancel"},{QMessageBox::Yes,"Yes"},{QMessageBox::No,"No"},{QMessageBox::Save,"Save"},{QMessageBox::Discard,"Discard"},{QMessageBox::Close,"Close"},{QMessageBox::Retry,"Retry"},{QMessageBox::Abort,"Stop"},{QMessageBox::Ignore,"Ignore"}};
    for (const auto& pair : labels) if (auto* button = box.button(pair.first)) button->setText(uiText(pair.second));
    if (initial != QMessageBox::NoButton) box.setDefaultButton(initial);
    return static_cast<QMessageBox::StandardButton>(box.exec());
}
}
QString savedUiLanguage() { return readSettings()["uiLanguage"].toString("ja") == "en" ? "en" : "ja"; }
void setUiLanguage(const QString& language) {
    if (language != "ja" && language != "en") throw std::invalid_argument("Unsupported QPE UI language");
    activeLanguage = language;
}
QString uiLanguage() { if (activeLanguage.isEmpty()) activeLanguage = savedUiLanguage(); return activeLanguage; }
const QLocale& uiLocale() { static const QLocale japanese("ja_JP"), english("en_US"); return uiLanguage() == "ja" ? japanese : english; }
QString uiText(const QString& source) { return uiLanguage() == "en" ? source : catalog().value(source, source); }
QStringList uiTexts(const QStringList& source) { QStringList result; for (const auto& text : source) result.append(uiText(text)); return result; }
QString UiInputDialog::getText(QWidget* parent, const QString& title, const QString& label, QLineEdit::EchoMode mode, const QString& text, bool* ok) {
    QInputDialog dialog(parent); dialog.setWindowTitle(title); dialog.setLabelText(label); dialog.setTextEchoMode(mode); dialog.setTextValue(text);
    dialog.setOkButtonText(uiText("OK")); dialog.setCancelButtonText(uiText("Cancel")); const bool accepted = dialog.exec() == QDialog::Accepted;
    if (ok) *ok = accepted; return accepted ? dialog.textValue() : QString();
}
QString UiInputDialog::getItem(QWidget* parent, const QString& title, const QString& label, const QStringList& items, int current, bool editable, bool* ok) {
    QInputDialog dialog(parent); dialog.setWindowTitle(title); dialog.setLabelText(label); dialog.setComboBoxItems(items); dialog.setComboBoxEditable(editable); dialog.setTextValue(items.value(current));
    dialog.setOkButtonText(uiText("OK")); dialog.setCancelButtonText(uiText("Cancel")); const bool accepted = dialog.exec() == QDialog::Accepted;
    if (ok) *ok = accepted; return accepted ? dialog.textValue() : QString();
}
void uiButtons(QDialogButtonBox* buttons) {
    const QList<QPair<QDialogButtonBox::StandardButton, QString>> labels{{QDialogButtonBox::Ok,"OK"},{QDialogButtonBox::Cancel,"Cancel"},{QDialogButtonBox::Save,"Save"},{QDialogButtonBox::Close,"Close"},{QDialogButtonBox::Apply,"Apply"},{QDialogButtonBox::Reset,"Reset"},{QDialogButtonBox::RestoreDefaults,"Restore Defaults"},{QDialogButtonBox::Yes,"Yes"},{QDialogButtonBox::No,"No"}};
    for (const auto& pair : labels) if (auto* button = buttons->button(pair.first)) button->setText(uiText(pair.second));
}
QMessageBox::StandardButton UiMessageBox::question(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons, QMessageBox::StandardButton initial) { return message(parent, QMessageBox::Question, title, text, buttons, initial); }
QMessageBox::StandardButton UiMessageBox::warning(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons, QMessageBox::StandardButton initial) { return message(parent, QMessageBox::Warning, title, text, buttons, initial); }
QMessageBox::StandardButton UiMessageBox::information(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons, QMessageBox::StandardButton initial) { return message(parent, QMessageBox::Information, title, text, buttons, initial); }
QMessageBox::StandardButton UiMessageBox::critical(QWidget* parent, const QString& title, const QString& text, QMessageBox::StandardButtons buttons, QMessageBox::StandardButton initial) { return message(parent, QMessageBox::Critical, title, text, buttons, initial); }
}
