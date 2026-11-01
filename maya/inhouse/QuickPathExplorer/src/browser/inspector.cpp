/** @file inspector.cpp @brief 詳細は常に見せ、専門設定は操作別タブに分ける。 */
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
#include <QTabWidget>
#include <QVBoxLayout>
#include <QLocale>
#include <QToolButton>
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
    auto* scroll = new QScrollArea(this); scroll->setObjectName("inspectorScroll"); scroll->setWidgetResizable(true); scroll->setFrameShape(QFrame::NoFrame); outer->addWidget(scroll);
    auto* content = new QWidget; auto* layout = new QVBoxLayout(content); scroll->setWidget(content);
    title_ = new QLabel("Select a file below"); title_->setObjectName("fileTitle"); title_->setTextFormat(Qt::PlainText);
    title_->setWordWrap(true); title_->setMinimumWidth(0); title_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred); layout->addWidget(title_);
    information_ = new QLabel("Select a file"); information_->setTextFormat(Qt::PlainText); information_->setWordWrap(true); information_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    information_->setMinimumWidth(0); information_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    const auto button = [this](QVBoxLayout* box, const QString& label, const QString& action) {
        auto* value = new QPushButton(label); value->setObjectName(action); box->addWidget(value);
        connect(value, &QPushButton::clicked, this, [this, action] { emit requested(action); });
    };
    tabs_ = new QTabWidget; tabs_->setObjectName("readOptions"); tabs_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum); tabs_->tabBar()->setExpanding(false); layout->addWidget(tabs_);
    auto* openPage = new QWidget; auto* openBox = new QVBoxLayout(openPage); tabs_->addTab(openPage, "Open");
    auto* hint = new QLabel(maya ? "Open Maya scenes in this session. Other file types use their associated application." : "Open using the associated application."); hint->setWordWrap(true); openBox->addWidget(hint);
    button(openBox, "Open", "open");
    if (maya) {
        auto* savePage = new QWidget; auto* saveBox = new QVBoxLayout(savePage);
        button(saveBox, "Save Scene", "save");
        saveBox->addWidget(new QLabel("File name"));
        name_ = new QLineEdit; name_->setPlaceholderText("Scene name.mb"); name_->setObjectName("saveName"); saveBox->addWidget(name_);
        type_ = new QComboBox; type_->setObjectName("saveType"); type_->addItem("Maya Binary (.mb)", "mayaBinary"); type_->addItem("Maya ASCII (.ma)", "mayaAscii"); saveBox->addWidget(type_);
        connect(name_, &QLineEdit::textChanged, this, &Inspector::changed); connect(type_, qOverload<int>(&QComboBox::currentIndexChanged), this, &Inspector::changed);
        button(saveBox, "Save Scene As…", "saveAs"); button(saveBox, "Export Selection…", "export");
        button(saveBox, "New Scene", "new");
        for (const QString action : {QString("import"), QString("reference"), QString("fbx")}) {
            auto* page = new QWidget; auto* box = new QVBoxLayout(page); auto* form = new QFormLayout; form->setRowWrapPolicy(QFormLayout::WrapAllRows); box->addLayout(form);
            auto* advanced = new QWidget; auto* advancedForm = new QFormLayout(advanced); advancedForm->setRowWrapPolicy(QFormLayout::WrapAllRows);
            if (action == "fbx") { fbx_ = page; openBox->insertWidget(0, page); page->hide(); }
            else tabs_->addTab(page, action == "import" ? "Import" : "Reference");
            const auto combo = [&](const QString& key, const QString& label, const QStringList& labels, const QStringList& values) {
                auto* control = new ReadOptionCombo; for (int i = 0; i < labels.size(); ++i) control->addItem(labels[i], values.value(i));
                control->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); control->setMinimumContentsLength(8);
                control->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
                control->setObjectName(action + "_" + key); controls_[action + "/" + key] = control; (key == "loadReferenceDepth" || key == "importTimeRange" ? advancedForm : form)->addRow(label, control);
                control->setToolTip(control->currentText());
                connect(control, &QComboBox::currentTextChanged, control, &QWidget::setToolTip);
                connect(control, qOverload<int>(&QComboBox::currentIndexChanged), this, &Inspector::changed); return control;
            };
            const auto toggle = [&](const QString& key, const QString& label, bool initial) {
                auto* control = new QCheckBox(label); control->setChecked(initial); control->setObjectName(action + "_" + key);
                controls_[action + "/" + key] = control;
                (key == "mergeNamespacesOnClash" || key == "deferReference" || action == "fbx" ? form : advancedForm)->addRow(control);
                connect(control, &QCheckBox::toggled, this, &Inspector::changed); return control;
            };
            if (action == "fbx") {
                combo("mode", "File Content", {"Open as scene", "Add", "Add and update animation", "Update animation only", "Update animation (keyed transforms)"}, {"open", "add", "merge", "exmerge", "exmergekeyedxforms"});
                toggle("timeline", "Update playback range", false);
                auto* help = new QLabel("Applies to Open and double-click. Open as scene replaces the current scene; the other modes update it."); help->setWordWrap(true); box->addWidget(help);
            } else {
                auto* mode = combo("mode", "Namespace", {"File name", "Custom", "Root"}, {"file", "custom", "root"});
                auto* name = new QLineEdit; name->setObjectName(action + "_name"); name->setPlaceholderText("characterA or shot:characterA"); name->setEnabled(false); form->addRow("Namespace name", name); controls_[action + "/name"] = name;
                auto* nameLabel = form->labelForField(name); name->hide(); nameLabel->hide();
                connect(mode, qOverload<int>(&QComboBox::currentIndexChanged), name, [name, nameLabel](int i) { name->setEnabled(i == 1); name->setVisible(i == 1); nameLabel->setVisible(i == 1); });
                connect(name, &QLineEdit::textChanged, this, &Inspector::changed);
                auto* chooseNamespace = new QPushButton("Choose existing namespace…"); form->addRow(chooseNamespace);
                connect(chooseNamespace, &QPushButton::clicked, this, [this, action] { emit namespaceRequested(action); });
                toggle("mergeNamespacesOnClash", "Reuse existing namespace", false);
                toggle("groupReference", "Group objects", false); toggle("executeScriptNodes", "Execute script nodes", true);
                if (action == "import") {
                    toggle("preserveReferences", "Preserve references", true); toggle("removeDuplicateNetworks", "Remove duplicate shading networks", false);
                    toggle("mergeBaseAnimLayer", "Merge base animation layer", false); toggle("renameAll", "Rename all nodes", false);
                    toggle("importFrameRate", "Import frame rate", false); toggle("ignoreVersion", "Ignore version", false);
                    combo("importTimeRange", "Playback range", {"Keep current", "Override", "Combine"}, {"keep", "override", "combine"});
                } else { toggle("deferReference", "Defer loading", false); toggle("lockReference", "Lock reference", false); }
                combo("loadReferenceDepth", "Load references", {"As saved", "All", "Top level only", "None"}, {"", "all", "topOnly", "none"});
                auto* expand = new QToolButton; expand->setText("Advanced options"); expand->setCheckable(true); expand->setArrowType(Qt::RightArrow); expand->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
                box->addWidget(expand); box->addWidget(advanced); advanced->hide();
                connect(expand, &QToolButton::toggled, advanced, [advanced, expand](bool visible) { advanced->setVisible(visible); expand->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow); });
                button(box, action == "import" ? "Import" : "Create Reference", action);
            }
            if (action == "fbx") delete advanced;
            auto* presetToggle = new QToolButton; presetToggle->setText("Presets"); presetToggle->setCheckable(true); presetToggle->setArrowType(Qt::RightArrow); presetToggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); box->addWidget(presetToggle);
            auto* presetPage = new QWidget; auto* presets = new QVBoxLayout(presetPage); presets->setContentsMargins(0, 0, 0, 0); box->addWidget(presetPage); presetPage->hide();
            connect(presetToggle, &QToolButton::toggled, presetPage, [presetPage, presetToggle](bool visible) { presetPage->setVisible(visible); presetToggle->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow); });
            for (const auto& command : QStringList{"Save preset", "Load preset", "Delete preset"}) {
                auto* value = new QPushButton(command); presets->addWidget(value);
                connect(value, &QPushButton::clicked, this, [this, action, command] {
                    try {
                        const auto state = readSettings(); auto all = state["nativeReadPresets"].toObject();
                        auto entries = readPresetsFromSettings(state, action); bool ok = false;
                        const auto name = command == "Save preset" ? QInputDialog::getText(this, command, "Preset name", QLineEdit::Normal, {}, &ok)
                            : QInputDialog::getItem(this, command, "Preset", entries.keys(), 0, false, &ok);
                        if (!ok || name.trimmed().isEmpty()) return;
                        if (command == "Save preset") {
                            if (entries.contains(name) && QMessageBox::question(this, "Replace preset", name,
                                QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
                            entries[name] = options()[action];
                        }
                        else if (command == "Load preset") { restore(QJsonObject{{action, entries[name]}}); return; }
                        else entries.remove(name);
                        all[action] = entries; writeSettings({{"nativeReadPresets", all}});
                    } catch (const std::exception& e) { QMessageBox::warning(this, "Read presets", QString::fromUtf8(e.what())); }
                });
            }
        }
        tabs_->addTab(savePage, "Save");
        operation_ = new QComboBox; operation_->setObjectName("inspectorOperation"); operation_->setAccessibleName("Maya operation");
        for (int i = 0; i < tabs_->count(); ++i) operation_->addItem(tabs_->tabText(i));
        layout->insertWidget(layout->indexOf(tabs_), operation_); operation_->hide();
        connect(operation_, qOverload<int>(&QComboBox::currentIndexChanged), tabs_, &QTabWidget::setCurrentIndex);
        connect(tabs_, &QTabWidget::currentChanged, operation_, &QComboBox::setCurrentIndex);
    } else { tabs_->tabBar()->hide(); }
    auto* details = new QToolButton; details->setObjectName("fileDetailsToggle"); details->setText("File details"); details->setCheckable(true); details->setArrowType(Qt::RightArrow); details->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); layout->addWidget(details);
    detailsBody_ = new QWidget; auto* detailsLayout = new QVBoxLayout(detailsBody_); detailsLayout->setContentsMargins(0, 0, 0, 0);
    detailsLayout->addWidget(information_); preview_ = new QLabel; preview_->setObjectName("filePreview"); preview_->setAlignment(Qt::AlignCenter); preview_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred); detailsLayout->addWidget(preview_);
    layout->addWidget(detailsBody_); detailsBody_->hide();
    media_ = new FileJobs(this); media_->setObjectName("inspectorMedia");
    connect(media_, &FileJobs::finished, this, [this](const QJsonObject& raw) {
        const auto result = fileResultFromJson(raw); const auto data = result.extra;
        if (result.cancelled || data["path"].toString() != path_ || data["token"].toString() != token_) return;
        if (!result.errors.isEmpty()) { information_->setText(result.errors.join("\n")); return; }
        QString info = "Type\n" + QFileInfo(path_).suffix() + "\n\nSize\n" + QLocale().formattedDataSize(qint64(data["size"].toDouble()))
            + "\n\nDate modified\n" + data["modified"].toString() + "\n\nAvailability\n" + data["availability"].toString() + "\n\nLocation\n" + QFileInfo(path_).absolutePath();
        if (data.contains("width")) info += QString("\n\nDimensions\n%1 × %2").arg(data["width"].toInt()).arg(data["height"].toInt());
        if (data.contains("mayaVersion")) info += "\n\nMaya version\n" + data["mayaVersion"].toString();
        for (const auto& raw : data["dependencies"].toArray()) { const auto row = raw.toObject(); info += "\n" + row["state"].toString() + ": " + row["path"].toString(); }
        if (data.contains("scene")) info += "\n\nScene information\n" + QString::fromUtf8(QJsonDocument(data["scene"].toObject()).toJson());
        if (data.contains("text")) info += "\n\nText preview (first 16 KiB)\n" + data["text"].toString();
        if (data.contains("note")) info += "\n\n" + data["note"].toString();
        information_->setText(info);
        QPixmap image; if (image.loadFromData(QByteArray::fromBase64(data["png"].toString().toLatin1()), "PNG")) preview_->setPixmap(image.scaled(220, 180, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    });
    connect(details, &QToolButton::toggled, detailsBody_, [this, details](bool visible) { detailsBody_->setVisible(visible); details->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow); if (visible) requestDetails(); else { token_ = QUuid::createUuid().toString(); media_->cancel(); } });
    if (maya) {
        button(layout, "Maya File Dialogs…", "options");
    }
    layout->addStretch();
    connect(tabs_, &QTabWidget::currentChanged, this, [this](int active) {
        // 非表示ページの詳細設定が、現在の短いページに空白を要求しないようにする。
        for (int i = 0; i < tabs_->count(); ++i) tabs_->widget(i)->setSizePolicy(QSizePolicy::Preferred, i == active ? QSizePolicy::Preferred : QSizePolicy::Ignored);
        tabs_->updateGeometry();
    });
    for (int i = 1; i < tabs_->count(); ++i) tabs_->widget(i)->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Ignored);
}
void Inspector::updateActionSelector() {
    if (!operation_ || !tabs_) return;
    int needed = 32; for (int i = 0; i < tabs_->count(); ++i) needed += fontMetrics().horizontalAdvance(tabs_->tabText(i)) + 28;
    const bool compact = width() < needed; operation_->setVisible(compact); tabs_->tabBar()->setVisible(!compact);
}
void Inspector::resizeEvent(QResizeEvent* event) { QWidget::resizeEvent(event); updateActionSelector(); }
void Inspector::changeEvent(QEvent* event) { QWidget::changeEvent(event); if (event->type() == QEvent::FontChange) updateActionSelector(); }
void Inspector::setPath(const QString& path) {
    if (path_ == path) return;
    path_ = path; token_ = QUuid::createUuid().toString(); media_->cancel(); preview_->clear();
    const QFileInfo info(path);
    title_->setText(path.isEmpty() ? "Select a file below" : info.fileName()); title_->setToolTip(path);
    if (fbx_) fbx_->setVisible(info.suffix().compare("fbx", Qt::CaseInsensitive) == 0);
    information_->setText(path.isEmpty() ? "Select a file" : "Loading details…");
    if (!detailsBody_->isHidden()) requestDetails();
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
