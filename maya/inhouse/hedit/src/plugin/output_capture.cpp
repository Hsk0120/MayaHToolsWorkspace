/** @file output_capture.cpp
 * @brief OutputCaptureの実装。
 */
#include "plugin/output_capture.h"
#include "core/history_text.h"
#include "editor/editor.h"
#include "plugin/mel.h"
#include <maya/MQtUtil.h>
#include <QApplication>
#include <QMutexLocker>
#include <QStringList>
#include <QPlainTextEdit>
#include <QTextCursor>
#include <QTextEdit>
#include <QThread>
#include <memory>

namespace hedit {
namespace {

/// キューに貯める文字数の上限(1Mi文字)。超えたら古いものから捨てる。
constexpr int kMaximumPendingCharacters = 1024 * 1024;

/// 1回の出力・起動時の履歴から取り込む文字数の上限(512Ki文字)。
constexpr int kMaximumChunkCharacters = 512 * 1024;

/** @brief 文字列の末尾だけを残す。途中で切ったUTF-16の文字(サロゲートペアの後半)は取り除く。
 * @param text 対象の文字列。
 * @param length 残す文字数。
 * @return 末尾のlength文字。
 */
QString keepTail(const QString& text, int length) {
    QString tail = text.right(length);
    // 絵文字などは2つのQCharで1文字になる。前半を切り落とした後半だけが先頭に残ったら捨てる。
    if (!tail.isEmpty() && tail.at(0).isLowSurrogate()) {
        tail.remove(0, 1);
    }
    return tail;
}

/** @brief Mayaの出力の種類を、heditの種類に変換する。
 * @param type MCommandMessageの種類。
 * @return 対応するOutputKind。
 */
OutputKind toOutputKind(MCommandMessage::MessageType type) {
    switch (type) {
    case MCommandMessage::kWarning:
        return OutputKind::Warning;
    case MCommandMessage::kError:
        return OutputKind::Error;
    case MCommandMessage::kResult:
        return OutputKind::Result;
    case MCommandMessage::kInfo:
        return OutputKind::Info;
    case MCommandMessage::kHistory:
        return OutputKind::History;
    default:
        return OutputKind::Normal;
    }
}

/** @brief Mayaのmain threadから呼ばれているか。 @return Qtの画面のスレッドならtrue。 */
bool onMainThread() {
    return qApp && QThread::currentThread() == qApp->thread();
}

/** @brief MayaのUI名から、reporterが表示に使っているQtの文書を探す。
 * @param control cmdScrollFieldReporterのUI名(フルパスでも可)。
 * @return 表示文書。見つからなければnullptr。所有者はMayaのUI。
 * @details reporterの実体はQTextEditかQPlainTextEdit、またはそれを子に持つ部品なので、本体→子の順に探す。
 */
QTextDocument* findReporterDocument(const QString& control) {
    QWidget* widget = MQtUtil::findControl(toMString(control));
    if (!widget) {
        return nullptr;
    }
    auto rich = qobject_cast<QTextEdit*>(widget);
    auto plain = qobject_cast<QPlainTextEdit*>(widget);
    if (!rich && !plain) {
        rich = widget->findChild<QTextEdit*>();
        plain = widget->findChild<QPlainTextEdit*>();
    }
    if (rich) {
        return rich->document();
    }
    return plain ? plain->document() : nullptr;
}

/** @brief Mayaが保持している過去の出力を読む。
 * @return 詰めた履歴(最大512Ki文字)。Maya側ですでに消えた履歴は含まない。
 * @details 標準Script Editorのreporterがあればその文書を読み、無ければ標準のエディタを開かずに
 * 一時的な非表示reporterで読む。設定・選択・履歴は変更しない。
 */
QString readMayaHistory() {
    QString reporter = mel("global string $gCommandReporter; string $heditReporter = $gCommandReporter;");
    QString temporaryWindow;
    if (reporter.isEmpty() || !melBool("cmdScrollFieldReporter -exists " + melQuote(reporter))) {
        temporaryWindow = mel("window");
        mel("columnLayout");
        reporter = mel("cmdScrollFieldReporter");
    }
    QString text;
    if (QTextDocument* document = findReporterDocument(reporter)) {
        text = document->toPlainText();
    } else {
        text = mel("cmdScrollFieldReporter -q -text " + melQuote(reporter));
    }
    if (!temporaryWindow.isEmpty()) {
        mel("deleteUI -window " + melQuote(temporaryWindow));
    }
    return compactHistory(keepTail(text, kMaximumChunkCharacters));
}

}  // namespace

namespace {
/// プラグインで1つだけの出力の取り込み。initializePluginで作り、uninitializePluginの最後に壊す。
std::unique_ptr<OutputCapture> captureInstance;
}  // namespace

void createOutputCapture() {
    if (!captureInstance) {
        captureInstance = std::make_unique<OutputCapture>();
    }
}

void destroyOutputCapture() {
    captureInstance.reset();
}

OutputCapture& outputCapture() {
    // 作る前・壊した後に呼ぶのはプログラムの誤り(呼出しの順番はplugin.cppのコメントを参照)。
    Q_ASSERT(captureInstance);
    return *captureInstance;
}

bool OutputCapture::start() {
    if (running_) {
        return true;  // 購読中。
    }
    // 同じメインスレッドで、履歴を一度取り込んでから購読を始める。
    // 既存の履歴と新しい出力の境目を分け、同じ出力を二重に表示しない。
    importHistory();
    // 出力の通知は、どちらの方式でも使う(速い方式は本文、正確な方式は種類)。
    // reporterより先に登録し、reporterへの追記の直前に種類が分かるようにする。
    typeCallback_ = MCommandMessage::addCommandOutputCallback(onCommandOutput, this);
    running_ = true;
    if (mode_ == Mode::Exact && !subscribeReporter()) {
        MGlobal::displayWarning("hedit: Maya's output reporter was not found; showing plain command output.");
    }
    return true;
}

void OutputCapture::setMode(Mode mode) {
    mode_ = mode;
    if (!running_ || (mode == Mode::Exact) == bool(reporterDocument_)) {
        return;  // 購読前(startで反映する)か、既にその方式。
    }
    if (mode == Mode::Exact) {
        if (!subscribeReporter()) {
            MGlobal::displayWarning("hedit: Maya's output reporter was not found; showing plain command output.");
        }
    } else {
        unsubscribeReporter();
    }
}

void OutputCapture::importHistory() {
    const QStringList lines = readMayaHistory().split('\n');
    QMutexLocker lock(&mutex_);
    for (int i = 0; i < lines.size(); ++i) {
        const QString& line = lines.at(i);
        const bool trailingEmpty = i == lines.size() - 1 && line.isEmpty();
        if (trailingEmpty) {
            break;  // 最後の改行の後ろの空文字列。
        }
        pending_.append({line + '\n', classifyHistoryLine(line)});
        pendingSize_ += line.size() + 1;
    }
}

bool OutputCapture::subscribeReporter() {
    // 1. 非表示のreporterを作る。作る途中で変わるMayaの「現在の親レイアウト」は元に戻す
    //    (他のツールのUI作成に影響させないため)。
    const QString previousParent = mel("setParent -q");
    reporterWindow_ = mel("window");
    mel("columnLayout");
    const QString reporter = mel("cmdScrollFieldReporter");
    if (!previousParent.isEmpty()) {
        mel("setParent " + melQuote(previousParent));
    }
    // 試験用: 環境変数で、reporterが見つからないMayaと同じ動き(代わりの取り込み)にできる。
    const bool forceFallback = qEnvironmentVariable("HEDIT_OUTPUT_FALLBACK") == QLatin1String("1");
    reporterDocument_ = forceFallback ? nullptr : findReporterDocument(reporter);
    if (!reporterDocument_) {
        // reporterの部品の作りはMayaの版で変わり得る(内部の構造に頼っているため)。見つからなければ、
        // 速い方式(公式の通知の本文を自分で整える)のまま動く。編集画面は開ける。
        unsubscribeReporter();
        return false;
    }
    // hedit専用の文書だけ行数を制限する。取り出すのは追記された部分だけなので、多くは要らない
    // (表示用の保持は編集画面の出力欄が持つ)。
    reporterDocument_->setMaximumBlockCount(1000);

    // 2. 文書への追記を購読する。contentsChangeは(位置, 削除した文字数, 追加した文字数)を知らせる。
    reporterConnection_ = QObject::connect(
        reporterDocument_.data(), &QTextDocument::contentsChange, reporterDocument_.data(),
        [this](int position, int removed, int added) {
            Q_UNUSED(removed);
            if (!reporterDocument_ || added == 0) {
                return;
            }
            // 追加された範囲を選択して取り出す。
            QTextCursor cursor(reporterDocument_);
            cursor.setPosition(position);
            cursor.setPosition(qMin(position + added, reporterDocument_->characterCount() - 1), QTextCursor::KeepAnchor);
            QString text = cursor.selectedText();
            text.replace(QChar::ParagraphSeparator, '\n');
            text.replace(QChar::LineSeparator, '\n');
            receive(text, toOutputKind(lastType_));
        });
    return true;
}

void OutputCapture::unsubscribeReporter() {
    QObject::disconnect(reporterConnection_);
    reporterDocument_ = nullptr;
    if (!reporterWindow_.isEmpty() && melBool("window -exists " + melQuote(reporterWindow_))) {
        mel("deleteUI -window " + melQuote(reporterWindow_));
    }
    reporterWindow_.clear();
}

void OutputCapture::onCommandOutput(const MString& message, MCommandMessage::MessageType type, void* clientData) {
    auto self = static_cast<OutputCapture*>(clientData);
    if (!self->reporterDocument_) {
        // 速い方式: 通知の本文を自分で整える(receiveは別スレッドからでも鍵を取って安全に貯める)。
        const OutputKind kind = toOutputKind(type);
        // Maya 2022のreporterは古い書き方(最後に「 // 」を付ける)なので、それに合わせる。
        static const bool legacy = MGlobal::apiVersion() < 20230000;
        self->receive(formatCommandOutput(fromMString(message), kind, legacy), kind);  // receiveの中で鍵を取る。
        return;
    }
    if (onMainThread()) {
        self->lastType_ = type;
    }
}

void OutputCapture::receive(QString text, OutputKind kind) {
    if (exiting_) {
        return;
    }
    // CRLFをQtの段落として二重に入れない。printの分割通知には改行を足さない。
    if (text.contains('\r')) {
        text.replace("\r\n", "\n");
        text.replace('\r', '\n');
    }
    {
        QMutexLocker lock(&mutex_);
        appendLocked(text, kind);
    }
    // take()が同じ鍵を使うので、描画の前に鍵を手放している(上の{}を出た時点で解放)。
    // ファイルの読み込み中などはQtのタイマーが動かないため、メインスレッドなら直接描き直す。
    if (onMainThread()) {
        refreshEditorOutput(editor_.data());
    }
}

void OutputCapture::appendLocked(const QString& input, OutputKind kind) {
    QString text = input;
    if (text.size() > kMaximumChunkCharacters) {
        text = keepTail(text, kMaximumChunkCharacters);
        omitted_ = true;
    }
    if (text.isEmpty()) {
        return;
    }
    pendingSize_ += text.size();
    // 同じ種類が続く場合は、1つの項目へつなげる(細切れの通知で項目が増えすぎないように)。
    if (!pending_.isEmpty() && pending_.last().kind == kind) {
        pending_.last().text += text;
    } else {
        pending_.append({text, kind});
    }
    // 上限を超えたら、古い項目から捨てる。
    while (pendingSize_ > kMaximumPendingCharacters && pending_.size() > 1) {
        pendingSize_ -= pending_.first().text.size();
        pending_.removeFirst();
        omitted_ = true;
    }
    // 1項目だけで上限を超える場合は、その項目の末尾だけを残す。
    if (pendingSize_ > kMaximumPendingCharacters) {
        pending_.last().text = keepTail(pending_.last().text, kMaximumChunkCharacters);
        pendingSize_ = pending_.last().text.size();
        omitted_ = true;
    }
}

QList<OutputMessage> OutputCapture::take() {
    QMutexLocker lock(&mutex_);
    QList<OutputMessage> result;
    result.swap(pending_);  // 中身を入れ替えて、キューを空にする。
    pendingSize_ = 0;
    if (omitted_) {
        result.prepend({"[hedit: older buffered output omitted]\n", OutputKind::Info});
    }
    omitted_ = false;
    return result;
}

void OutputCapture::stopForExit() {
    exiting_ = true;
    QObject::disconnect(reporterConnection_);
    reporterDocument_ = nullptr;
}

MStatus OutputCapture::stop() {
    running_ = false;
    unsubscribeReporter();
    if (typeCallback_) {
        const MStatus status = MMessage::removeCallback(typeCallback_);
        if (!status) {
            return status;
        }
        typeCallback_ = 0;
    }
    return MS::kSuccess;
}

}  // namespace hedit
