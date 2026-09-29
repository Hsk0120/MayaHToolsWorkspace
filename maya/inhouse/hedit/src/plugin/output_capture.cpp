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

OutputCapture& outputCapture() {
    // 関数の中のstatic変数は、最初に呼ばれたときに1回だけ作られる。
    static OutputCapture instance;
    return instance;
}

bool OutputCapture::start() {
    if (reporterDocument_) {
        return true;  // 購読中。
    }
    // 同じメインスレッドで、履歴を一度取り込んでから購読を始める。
    // 既存の履歴と新しい出力の境目を分け、同じ出力を二重に表示しない。
    importHistory();
    if (!subscribe()) {
        stop();
        MGlobal::displayError("hedit: native output reporter unavailable.");
        return false;
    }
    return true;
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

bool OutputCapture::subscribe() {
    // 1. 出力の種類の通知。専用reporterより先に登録し、追記の直前に種類が分かるようにする。
    typeCallback_ = MCommandMessage::addCommandOutputCallback(onCommandOutput, this);

    // 2. 非表示のreporterを作る。作る途中で変わるMayaの「現在の親レイアウト」は元に戻す
    //    (他のツールのUI作成に影響させないため)。
    const QString previousParent = mel("setParent -q");
    reporterWindow_ = mel("window");
    mel("columnLayout");
    const QString reporter = mel("cmdScrollFieldReporter");
    if (!previousParent.isEmpty()) {
        mel("setParent " + melQuote(previousParent));
    }
    reporterDocument_ = findReporterDocument(reporter);
    if (!reporterDocument_) {
        return false;
    }
    // hedit専用の文書だけ行数を制限し、長時間使ってもメモリが増え続けないようにする。
    reporterDocument_->setMaximumBlockCount(5000);

    // 3. 文書への追記を購読する。contentsChangeは(位置, 削除した文字数, 追加した文字数)を知らせる。
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

void OutputCapture::onCommandOutput(const MString& message, MCommandMessage::MessageType type, void* clientData) {
    Q_UNUSED(message);
    auto self = static_cast<OutputCapture*>(clientData);
    if (onMainThread()) {
        self->lastType_ = type;
    }
}

void OutputCapture::receive(QString text, OutputKind kind) {
    if (exiting_) {
        return;
    }
    // CRLFをQtの段落として二重に入れない。printの分割通知には改行を足さない。
    text.replace("\r\n", "\n");
    text.replace('\r', '\n');
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
    QObject::disconnect(reporterConnection_);
    reporterDocument_ = nullptr;
    if (!reporterWindow_.isEmpty() && melBool("window -exists " + melQuote(reporterWindow_))) {
        mel("deleteUI -window " + melQuote(reporterWindow_));
    }
    reporterWindow_.clear();
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
