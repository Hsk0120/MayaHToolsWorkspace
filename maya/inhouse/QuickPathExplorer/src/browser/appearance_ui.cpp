/** @file appearance_ui.cpp @brief 旧版のホスト別表示設定を維持する即時反映画面。 */
#include "ui_language.h"
#include "browser_window.h"
#include "../core/settings_store.h"
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QLabel>
#include <QPushButton>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QVBoxLayout>
#include <QMessageBox>
namespace qpe {
void BrowserWindow::appearanceDialog() { preferencesDialog("display"); }
QWidget* BrowserWindow::appearancePanel(QWidget* parent) {
    auto* panel = new QWidget(parent); panel->setObjectName("displaySettings");
    auto* form = new QFormLayout(panel);
    auto* theme = new QComboBox; for (const auto& pair : QList<QPair<QString, QString>>{{"Windows theme", "system"}, {"Windows Light", "light"}, {"Windows Dark", "dark"}, {"Classic Light", "finder"}}) theme->addItem(uiText(pair.first), pair.second);
    theme->setCurrentIndex(qMax(0, theme->findData(theme_))); if (!host_.maya) form->addRow(uiText("Color"), theme); else { theme->setParent(panel); theme->hide(); }
    auto* dpi = new QLabel; form->addRow(dpi);
    auto* preset = new QComboBox; preset->setObjectName("displayPreset"); preset->addItems({uiText("Very Small"), uiText("Smaller"), uiText("Standard"), uiText("Larger"), uiText("Largest"), uiText("Custom")}); form->addRow(uiText("Size"), preset);
    auto* pixels = new QSpinBox; pixels->setObjectName("displayFontSize"); pixels->setRange(10, 24); pixels->setValue(textSize_); form->addRow(uiText("Font size"), pixels);
    auto* scale = new QSpinBox; scale->setObjectName("displayUiScale"); scale->setRange(75, 200); scale->setSingleStep(25); scale->setSuffix(" %"); scale->setValue(uiPercent_); form->addRow(uiText("Additional UI scale"), scale);
    auto* density = new QComboBox; density->setObjectName("displayDensity"); density->addItems({uiText("Compact"), uiText("Comfortable")}); density->setCurrentIndex(density_ == "comfortable"); form->addRow(uiText("Row spacing"), density);
    auto* widths = new QComboBox; widths->setObjectName("columnWidthMode"); widths->addItem(uiText("Fit window"), "fit"); widths->addItem(uiText("Fit folder names"), "names"); widths->setCurrentIndex(readSettings()["columnWidthMode"].toString() == "names"); form->addRow(uiText("Column width"), widths);
    auto* effective = new QLabel; form->addRow(effective); form->addRow(new QLabel(uiText("In lists: Ctrl + / Ctrl −\nCtrl 0: reset base size")));
    const auto update = [this, pixels, scale, density, theme, effective, preset, dpi] {
        textSize_ = pixels->value(); uiPercent_ = scale->value(); density_ = density->currentIndex() ? "comfortable" : "compact"; theme_ = theme->currentData().toString();
        applyAppearance();
        dpi->setText(host_.maya && textSize_ != 10 ? QString(uiText("Maya DPI: %1%")).arg(qRound(host_.dpi * 100)) : uiText("DPI: Windows / Qt automatic"));
        const int percent = qRound(property("qpeUiScale").toReal() * 100 / host_.dpi);
        effective->setText(QString(uiText("Displayed text: %1 px · UI: %2% of standard")).arg(font().pixelSize()).arg(percent));
        QSignalBlocker guard(preset); const auto index = QList<int>{10, 11, 12, 14, 16}.indexOf(textSize_); preset->setCurrentIndex(uiPercent_ == 100 && index >= 0 ? index : 5);
    };
    connect(pixels, QOverload<int>::of(&QSpinBox::valueChanged), panel, update); connect(scale, QOverload<int>::of(&QSpinBox::valueChanged), panel, update);
    connect(density, QOverload<int>::of(&QComboBox::currentIndexChanged), panel, update); connect(theme, QOverload<int>::of(&QComboBox::currentIndexChanged), panel, update);
    connect(preset, QOverload<int>::of(&QComboBox::activated), panel, [pixels, scale](int index) { if (index < 5) { pixels->setValue(QList<int>{10, 11, 12, 14, 16}[index]); scale->setValue(100); } });
    connect(widths, QOverload<int>::of(&QComboBox::currentIndexChanged), panel, [this, widths] { perform("columnWidthPreview:" + widths->currentData().toString()); });
    auto* defaults = new QPushButton(uiText("Restore Defaults")); form->addRow(defaults);
    connect(defaults, &QPushButton::clicked, panel, [this, pixels, scale, density, widths, theme, update] { pixels->setValue(12); scale->setValue(100); density->setCurrentIndex(0); widths->setCurrentIndex(0); theme->setCurrentIndex(host_.maya ? 2 : 0); update(); });
    update(); return panel;
}
}
