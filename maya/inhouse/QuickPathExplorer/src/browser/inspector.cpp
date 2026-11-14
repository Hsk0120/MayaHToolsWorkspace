/** @file inspector.cpp @brief 下段右の作業ペインに頻用設定を示し、補助操作はメニューへまとめる。 */
#include "ui_language.h"
#include <QStyleOptionButton>
#include <QPainter>
#include "inspector.h"
#include "../core/settings_store.h"
#include "../core/file_operations.h"
#include <QCheckBox>
#include <QComboBox>
#include <QDir>
#include <QFileInfo>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QScrollBar>
#include <QTabWidget>
#include <QVBoxLayout>
#include <QLocale>
#include <QToolButton>
#include <QMenu>
#include <QInputDialog>
#include <QMessageBox>
#include <QJsonArray>
#include <QTabBar>
#include <QUuid>
#include <QPixmap>
#include <QJsonDocument>
#include <QResizeEvent>
#include <QAbstractItemView>
#include <QGuiApplication>
#include <QScreen>
#include <QStyle>
#include <stdexcept>
namespace qpe {
/** @brief 日本語の長い項目を折り返し、狭い詳細ペインへ最小幅を強制しない。 */
class ReadOptionCheck final : public QCheckBox {
public:
    /** @brief チェック状態とキーボード入力は標準QCheckBoxへ任せる。 @param text 項目名。 */
    explicit ReadOptionCheck(const QString& text) : QCheckBox(text) {
        auto policy = sizePolicy(); policy.setHorizontalPolicy(QSizePolicy::Expanding); policy.setHeightForWidth(true); setSizePolicy(policy);
    }
    /** @brief 折り返しの高さを有効にする。 @return 常にtrue。 */
    bool hasHeightForWidth() const override { return true; }
    /** @brief 字形とインジケーターから必要な高さを求める。 @param width 使用可能幅。 @return 必要高。 */
    int heightForWidth(int width) const override {
        QStyleOptionButton option; initStyleOption(&option); option.rect = QRect(0, 0, qMax(1, width), 1000);
        const auto content = style()->subElementRect(QStyle::SE_CheckBoxContents, &option, this);
        return qMax(style()->pixelMetric(QStyle::PM_IndicatorHeight, &option, this), fontMetrics().boundingRect(QRect(0, 0, qMax(1, content.width()), 1000), Qt::TextWordWrap, text()).height()) + 6;
    }
    /** @brief 通常ペイン内の幅を提案する。 @return 折り返した推奨寸法。 */
    QSize sizeHint() const override { return {240, heightForWidth(240)}; }
    /** @brief ラベルの長さによる横方向の固定を避ける。 @return 最小寸法。 */
    QSize minimumSizeHint() const override { return {0, fontMetrics().height() + 6}; }
protected:
    /** @brief 標準のチェックと、折り返したラベルを描く。 @param event 描画要求。 */
    void paintEvent(QPaintEvent*) override {
        QStyleOptionButton option; initStyleOption(&option); const auto label = option.text; option.text.clear();
        QPainter painter(this); style()->drawControl(QStyle::CE_CheckBox, &option, &painter, this);
        painter.setFont(font());
        painter.setPen(palette().color(isEnabled() ? QPalette::Active : QPalette::Disabled, QPalette::WindowText));
        painter.drawText(style()->subElementRect(QStyle::SE_CheckBoxContents, &option, this), Qt::AlignVCenter | Qt::TextWordWrap, label);
    }
    /** @brief 折り返したラベル上でもクリックして切り替えられる。 @param pos 入力位置。 @return 自分の領域内か。 */
    bool hitButton(const QPoint& pos) const override { return rect().contains(pos); }
};
/** @brief ドック幅を広げず、選択肢を画面内で全文表示するコンボボックス。 */
class ReadOptionCombo final : public QComboBox {
public:
    /** @brief ポップアップだけを項目幅に合わせる。親ペインの最小幅は変更しない。 */
    void showPopup() override {
        int contentWidth = width();
        for (int i = 0; i < count(); ++i)
            contentWidth = qMax(contentWidth, fontMetrics().horizontalAdvance(itemText(i)) + 36);
        auto* target = QGuiApplication::screenAt(mapToGlobal(rect().center()));
        if (!target) target = QGuiApplication::primaryScreen();
        if (target) contentWidth = qMin(contentWidth, target->availableGeometry().width() - 16);
        view()->setMinimumWidth(contentWidth);
        QComboBox::showPopup();
    }
};
Inspector::Inspector(bool maya, QWidget* parent) : QWidget(parent) {
    setObjectName("inspector");
    auto* outer = new QVBoxLayout(this); outer->setContentsMargins(0, 0, 0, 0);
    auto* scroll = new QScrollArea(this); scroll->setObjectName("inspectorScroll"); scroll->setWidgetResizable(true); scroll->setFrameShape(QFrame::NoFrame); outer->addWidget(scroll, 1);
    // 実行は設定のスクロール量と無関係に届く場所へ置く。親ドックには最小高を要求しない。
    auto* actions = new QWidget(this); actions->setObjectName("inspectorActions");
    auto* actionBox = new QVBoxLayout(actions); actionBox->setContentsMargins(9, 4, 9, 9);
    outer->addWidget(actions); actions->hide();
    auto* content = new QWidget; auto* layout = new QVBoxLayout(content); scroll->setWidget(content);
    title_ = new QLabel(uiText("Select a file below")); title_->setObjectName("fileTitle"); title_->setTextFormat(Qt::PlainText);
    title_->setWordWrap(true); title_->setMinimumWidth(0); title_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred); layout->addWidget(title_);
    information_ = new QLabel(uiText("Select a file")); information_->setTextFormat(Qt::PlainText); information_->setWordWrap(true); information_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    information_->setMinimumWidth(0); information_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    const auto button = [this](QVBoxLayout* box, const QString& label, const QString& action) {
        auto* value = new QPushButton(uiText(label)); value->setObjectName(action); box->addWidget(value);
        connect(value, &QPushButton::clicked, this, [this, action] { emit requested(action); });
    };
    tabs_ = new QTabWidget; tabs_->setObjectName("readOptions"); tabs_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum); tabs_->tabBar()->setExpanding(false); layout->addWidget(tabs_);
    auto* openPage = new QWidget; auto* openBox = new QVBoxLayout(openPage); tabs_->addTab(openPage, uiText("Open"));
    auto* hint = new QLabel(maya ? uiText("Open Maya scenes in this session. Other file types use their associated application.") : uiText("Open using the associated application.")); hint->setWordWrap(true); openBox->addWidget(hint);
    hint->setObjectName("openHint");
    button(openBox, uiText("Open"), "open");
    // Mayaの読込設定タブに合わせて領域が広がっても、案内と開くボタンは上にまとめる。
    openBox->setAlignment(Qt::AlignTop);
    if (maya) {
        auto* savePage = new QWidget; auto* saveBox = new QVBoxLayout(savePage); saveBox->setAlignment(Qt::AlignTop);
        button(saveBox, uiText("Save Scene"), "save");
        saveBox->addWidget(new QLabel(uiText("File name")));
        name_ = new QLineEdit; name_->setPlaceholderText(uiText("Scene name.mb")); name_->setObjectName("saveName"); saveBox->addWidget(name_);
        type_ = new QComboBox; type_->setObjectName("saveType"); type_->addItem(uiText("Maya Binary (.mb)"), "mayaBinary"); type_->addItem(uiText("Maya ASCII (.ma)"), "mayaAscii"); saveBox->addWidget(type_);
        connect(name_, &QLineEdit::textChanged, this, &Inspector::changed); connect(type_, qOverload<int>(&QComboBox::currentIndexChanged), this, &Inspector::changed);
        button(saveBox, uiText("Save Scene As…"), "saveAs"); button(saveBox, uiText("Export Selection…"), "export");
        button(saveBox, uiText("New Scene"), "new");
        for (const QString action : {QString("import"), QString("reference"), QString("fbx")}) {
            auto* page = new QWidget; auto* box = new QVBoxLayout(page); auto* form = new QFormLayout; form->setRowWrapPolicy(QFormLayout::WrapAllRows); box->addLayout(form);
            auto* advanced = new QWidget; auto* advancedForm = new QFormLayout(advanced); advancedForm->setRowWrapPolicy(QFormLayout::WrapAllRows);
            if (action == "fbx") { fbx_ = page; openBox->insertWidget(0, page); page->hide(); }
            else tabs_->addTab(page, action == "import" ? uiText("Import") : uiText("Reference"));
            const auto combo = [&](const QString& key, const QString& label, const QStringList& labels, const QStringList& values) {
                auto* control = new ReadOptionCombo; for (int i = 0; i < labels.size(); ++i) control->addItem(uiText(labels[i]), values.value(i));
                control->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); control->setMinimumContentsLength(8);
                control->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
                control->setObjectName(action + "_" + key); controls_[action + "/" + key] = control; (key == "loadReferenceDepth" || key == "importTimeRange" ? advancedForm : form)->addRow(uiText(label), control);
                control->setToolTip(control->currentText());
                connect(control, &QComboBox::currentTextChanged, control, &QWidget::setToolTip);
                connect(control, qOverload<int>(&QComboBox::currentIndexChanged), this, &Inspector::changed); return control;
            };
            const auto toggle = [&](const QString& key, const QString& label, bool initial) {
                auto* control = new ReadOptionCheck(uiText(label)); control->setChecked(initial); control->setObjectName(action + "_" + key);
                controls_[action + "/" + key] = control;
                (key == "mergeNamespacesOnClash" || key == "deferReference" || action == "fbx" ? form : advancedForm)->addRow(control);
                connect(control, &QCheckBox::toggled, this, &Inspector::changed); return control;
            };
            if (action == "fbx") {
                combo("mode", uiText("File Content"), {uiText("Open as scene"), uiText("Add"), uiText("Add and update animation"), uiText("Update animation only"), uiText("Update animation (keyed transforms)")}, {"open", "add", "merge", "exmerge", "exmergekeyedxforms"});
                toggle("timeline", uiText("Update playback range"), false);
                auto* help = new QLabel(uiText("Applies to Open and double-click. Open as scene replaces the current scene; the other modes update it.")); help->setWordWrap(true); box->addWidget(help);
            } else {
                auto* mode = combo("mode", uiText("Namespace"), {uiText("File name"), uiText("Custom"), uiText("Root")}, {"file", "custom", "root"});
                auto* name = new QLineEdit; name->setObjectName(action + "_name"); name->setPlaceholderText(uiText("characterA or shot:characterA")); name->setEnabled(false); form->addRow(uiText("Namespace name"), name); controls_[action + "/name"] = name;
                auto* nameLabel = form->labelForField(name); name->hide(); nameLabel->hide();
                connect(mode, qOverload<int>(&QComboBox::currentIndexChanged), name, [name, nameLabel](int i) { name->setEnabled(i == 1); name->setVisible(i == 1); nameLabel->setVisible(i == 1); });
                connect(name, &QLineEdit::textChanged, this, &Inspector::changed);
                auto* chooseNamespace = new QPushButton(uiText("Choose existing namespace…")); form->addRow(chooseNamespace);
                connect(chooseNamespace, &QPushButton::clicked, this, [this, action] { emit namespaceRequested(action); });
                toggle("mergeNamespacesOnClash", uiText("Reuse existing namespace"), false);
                toggle("groupReference", uiText("Group objects"), false); toggle("executeScriptNodes", uiText("Execute script nodes"), true);
                if (action == "import") {
                    toggle("preserveReferences", uiText("Preserve references"), true); toggle("removeDuplicateNetworks", uiText("Remove duplicate shading networks"), false);
                    toggle("mergeBaseAnimLayer", uiText("Merge base animation layer"), false); toggle("renameAll", uiText("Rename all nodes"), false);
                    toggle("importFrameRate", uiText("Import frame rate"), false); toggle("ignoreVersion", uiText("Ignore version"), false);
                    combo("importTimeRange", uiText("Playback range"), {uiText("Keep current"), uiText("Override"), uiText("Combine")}, {"keep", "override", "combine"});
                } else { toggle("deferReference", uiText("Defer loading"), false); toggle("lockReference", uiText("Lock reference"), false); }
                combo("loadReferenceDepth", uiText("Load references"), {uiText("As saved"), uiText("All"), uiText("Top level only"), uiText("None")}, {"", "all", "topOnly", "none"});
                auto* expand = new QToolButton; expand->setText(uiText("Advanced options")); expand->setCheckable(true); expand->setArrowType(Qt::RightArrow); expand->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
                box->addWidget(expand); box->addWidget(advanced); advanced->hide();
                connect(expand, &QToolButton::toggled, advanced, [advanced, expand](bool visible) { advanced->setVisible(visible); expand->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow); });
                button(actionBox, action == "import" ? uiText("Import") : uiText("Create Reference"), action);
            }
            if (action == "fbx") delete advanced;
            // 補助操作を展開して入力欄を押し下げず、明示操作時だけメニューを開く。
            auto* presetToggle = new QToolButton; presetToggle->setText(uiText("Presets")); presetToggle->setObjectName(action + "Presets");
            presetToggle->setPopupMode(QToolButton::InstantPopup); box->addWidget(presetToggle);
            auto* presets = new QMenu(presetToggle); presetToggle->setMenu(presets);
            for (const auto& command : QStringList{"Save preset", "Load preset", "Delete preset"}) {
                auto* value = presets->addAction(uiText(command));
                connect(value, &QAction::triggered, this, [this, action, command] {
                    try {
                        const auto state = readSettings(); auto all = state["nativeReadPresets"].toObject();
                        auto entries = readPresetsFromSettings(state, action); bool ok = false;
                        const auto name = command == "Save preset" ? UiInputDialog::getText(this, uiText(command), uiText("Preset name"), QLineEdit::Normal, {}, &ok)
                            : UiInputDialog::getItem(this, uiText(command), uiText("Preset"), entries.keys(), 0, false, &ok);
                        if (!ok || name.trimmed().isEmpty()) return;
                        if (command == "Save preset") {
                            if (entries.contains(name) && UiMessageBox::question(this, uiText("Replace preset"), name,
                                QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                            entries[name] = options()[action];
                        }
                        else if (command == "Load preset") { restore(QJsonObject{{action, entries[name]}}); return; }
                        else entries.remove(name);
                        all[action] = entries; writeSettings({{"nativeReadPresets", all}});
                    } catch (const std::exception& e) { UiMessageBox::warning(this, uiText("Read presets"), uiText(QString::fromUtf8(e.what()))); }
                });
            }
        }
        tabs_->addTab(savePage, uiText("Save"));
        operation_ = new QComboBox; operation_->setObjectName("inspectorOperation"); operation_->setAccessibleName(uiText("Maya operation"));
        for (int i = 0; i < tabs_->count(); ++i) operation_->addItem(tabs_->tabText(i));
        layout->insertWidget(layout->indexOf(tabs_), operation_); operation_->hide();
        connect(operation_, qOverload<int>(&QComboBox::currentIndexChanged), tabs_, &QTabWidget::setCurrentIndex);
        connect(tabs_, &QTabWidget::currentChanged, operation_, &QComboBox::setCurrentIndex);
    } else { tabs_->tabBar()->hide(); }
    auto* details = new QToolButton; details->setObjectName("fileDetailsToggle"); details->setText(uiText("File details")); details->setCheckable(true); details->setArrowType(Qt::RightArrow); details->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); layout->addWidget(details);
    detailsBody_ = new QWidget; auto* detailsLayout = new QVBoxLayout(detailsBody_); detailsLayout->setContentsMargins(0, 0, 0, 0);
    detailsLayout->addWidget(information_); preview_ = new QLabel; preview_->setObjectName("filePreview"); preview_->setAlignment(Qt::AlignCenter); preview_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred); detailsLayout->addWidget(preview_);
    layout->addWidget(detailsBody_); detailsBody_->hide();
    media_ = new FileJobs(this); media_->setObjectName("inspectorMedia");
    connect(media_, &FileJobs::finished, this, [this](const QJsonObject& raw) {
        const auto result = fileResultFromJson(raw); const auto data = result.extra;
        if (result.cancelled || data["path"].toString() != path_ || data["token"].toString() != token_) return;
        if (!result.errors.isEmpty()) { information_->setText(result.errors.join("\n")); return; }
        QString info = uiText("Type") + "\n" + QFileInfo(path_).suffix() + "\n\n" + uiText("Size") + "\n" + uiLocale().formattedDataSize(qint64(data["size"].toDouble()))
            + "\n\n" + uiText("Date modified") + "\n" + data["modified"].toString() + "\n\n" + uiText("Availability") + "\n" + data["availability"].toString() + "\n\n" + uiText("Location") + "\n" + QFileInfo(path_).absolutePath();
        if (data.contains("width")) info += QString("\n\n" + uiText("Dimensions") + "\n%1 × %2").arg(data["width"].toInt()).arg(data["height"].toInt());
        if (data.contains("mayaVersion")) info += "\n\n" + uiText("Maya version") + "\n" + data["mayaVersion"].toString();
        for (const auto& raw : data["dependencies"].toArray()) { const auto row = raw.toObject(); info += "\n" + row["state"].toString() + ": " + row["path"].toString(); }
        if (data.contains("scene")) info += "\n\n" + uiText("Scene information") + "\n" + QString::fromUtf8(QJsonDocument(data["scene"].toObject()).toJson());
        if (data.contains("text")) info += "\n\n" + uiText("Text preview (first 16 KiB)") + "\n" + data["text"].toString();
        if (data.contains("note")) info += "\n\n" + data["note"].toString();
        information_->setText(info);
        if (previewSource_.loadFromData(QByteArray::fromBase64(data["png"].toString().toLatin1()), "PNG")) fitPreview();
    });
    connect(details, &QToolButton::toggled, detailsBody_, [this, details](bool visible) { detailsBody_->setVisible(visible); details->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow); if (visible) requestDetails(); else { token_ = QUuid::createUuid().toString(); media_->cancel(); } });
    // Maya標準ダイアログは「ツール > Maya」へ集約し、通常作業の設定と混在させない。
    layout->addStretch();
    connect(tabs_, &QTabWidget::currentChanged, this, [this, scroll, actions](int active) {
        actions->setVisible(active == 1 || active == 2);
        for (auto* value : actions->findChildren<QPushButton*>())
            value->setVisible(value->objectName() == (active == 1 ? "import" : "reference"));
        // 非表示ページの詳細設定が、現在の短いページに空白を要求しないようにする。
        for (int i = 0; i < tabs_->count(); ++i) tabs_->widget(i)->setSizePolicy(QSizePolicy::Preferred, i == active ? QSizePolicy::Preferred : QSizePolicy::Ignored);
        tabs_->updateGeometry();
        updateTitle();
        // 明示的な操作切替だけ先頭へ戻し、非同期詳細取得や同じ操作内のスクロールは維持する。
        scroll->verticalScrollBar()->setValue(0);
    });
    for (int i = 1; i < tabs_->count(); ++i) tabs_->widget(i)->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Ignored);
}
void Inspector::updateActionSelector() {
    if (!operation_ || !tabs_) return;
    int needed = 32; for (int i = 0; i < tabs_->count(); ++i) needed += fontMetrics().horizontalAdvance(tabs_->tabText(i)) + 28;
    const bool compact = width() < needed; operation_->setVisible(compact); tabs_->tabBar()->setVisible(!compact);
}
void Inspector::fitPreview() {
    if (previewSource_.isNull()) return;
    const auto* scroll = findChild<QScrollArea*>("inspectorScroll");
    const auto margins = scroll->widget()->layout()->contentsMargins();
    const int available = width() - margins.left() - margins.right() - scroll->style()->pixelMetric(QStyle::PM_ScrollBarExtent);
    preview_->setPixmap(previewSource_.scaled(qBound(1, available, 220), 180, Qt::KeepAspectRatio, Qt::SmoothTransformation));
}
void Inspector::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    updateActionSelector();
    if (event->oldSize().width() != event->size().width()) fitPreview();
}
void Inspector::changeEvent(QEvent* event) {
    QWidget::changeEvent(event);
    if (event->type() == QEvent::FontChange) { updateActionSelector(); fitPreview(); }
}
void Inspector::setPath(const QString& path) {
    if (path_ == path) return;
    path_ = path; token_ = QUuid::createUuid().toString(); media_->cancel(); previewSource_ = QPixmap(); preview_->clear();
    const QFileInfo info(path);
    updateTitle();
    if (fbx_) fbx_->setVisible(info.suffix().compare("fbx", Qt::CaseInsensitive) == 0);
    information_->setText(path.isEmpty() ? uiText("Select a file") : uiText("Loading details…"));
    if (!detailsBody_->isHidden()) requestDetails();
}
void Inspector::updateTitle() {
    const bool saving = name_ && tabs_ && tabs_->currentIndex() == 3;
    title_->setText(saving ? uiText("Save Scene") : path_.isEmpty() ? uiText("Select a file below") : QFileInfo(path_).fileName());
    title_->setToolTip(saving ? QString() : path_);
}
void Inspector::requestDetails() {
    token_ = QUuid::createUuid().toString(); media_->cancel();
    if (!path_.isEmpty()) media_->enqueue({"media", {path_}, {}, "rename", {{"token", token_}}});
}
void Inspector::showAction(const QString& action) {
    if (!tabs_) return;
    const int index = action == "import" ? 1 : action == "reference" ? 2 : action == "saveAs" || action == "save" || action == "export" ? 3 : 0;
    if (index < tabs_->count()) tabs_->setCurrentIndex(index);
}
void Inspector::setDirectory(const QString& path) { directory_ = path; }
QJsonObject Inspector::options() const {
    QJsonObject result;
    for (auto it = controls_.begin(); it != controls_.end(); ++it) {
        const auto action = it.key().section('/', 0, 0), key = it.key().section('/', 1);
        auto values = result[action].toObject();
        if (auto* v = qobject_cast<QComboBox*>(it.value())) values[key] = v->currentData().toString();
        else if (auto* v = qobject_cast<QCheckBox*>(it.value())) values[key] = v->isChecked();
        else if (auto* v = qobject_cast<QLineEdit*>(it.value())) values[key] = v->text();
        result[action] = values;
    }
    if (name_) { result["fileName"] = name_->text(); result["fileType"] = type_->currentData().toString(); result["directory"] = directory_; }
    return result;
}
void Inspector::restore(const QJsonObject& state) {
    for (auto it = controls_.begin(); it != controls_.end(); ++it) {
        const QJsonValue value = state[it.key().section('/', 0, 0)].toObject().value(it.key().section('/', 1));
        if (value.isUndefined()) continue;
        if (auto* v = qobject_cast<QComboBox*>(it.value())) {
            // Python版の保存値はindex、新版は明示した値。既存設定を読み捨てない。
            const int i = value.isDouble() ? value.toInt(-1) : v->findData(value.toString()); if (i >= 0 && i < v->count()) v->setCurrentIndex(i);
        }
        else if (auto* v = qobject_cast<QCheckBox*>(it.value())) { if (value.isBool()) v->setChecked(value.toBool()); }
        else if (auto* v = qobject_cast<QLineEdit*>(it.value())) v->setText(value.toString());
    }
    if (name_) { if (state.contains("fileName")) name_->setText(state["fileName"].toString()); if (state.contains("fileType")) type_->setCurrentIndex(qMax(0, type_->findData(state["fileType"].toString("mayaBinary")))); }
}
}
