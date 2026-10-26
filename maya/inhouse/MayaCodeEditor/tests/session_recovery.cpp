/** @file session_recovery.cpp
 * @brief 多重起動・強制終了・破損・移行・履歴保全を専用データで検証する。
 */
#include "editor/session_store.h"
#include <QCoreApplication>
#include <QDebug>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QTemporaryDir>
#include <QThread>
#include <stdexcept>

namespace {

/** @brief 条件が偽ならテストを中断する。 @param ok 条件。 @param message 診断文。 */
void require(bool ok, const char* message) {
    if (!ok) { throw std::runtime_error(message); }
}

/** @brief 試験データを書込む。 @param path パス。 @param bytes 内容。 */
void write(const QString& path, const QByteArray& bytes) {
    QFile file(path);
    require(file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size(), "fixture write");
}

/** @brief 本文が1つの試験データを作る。 @param text 本文。 @return セッション。 */
mce::SessionData sample(const QString& text) {
    mce::SessionData data;
    mce::TabState tab;
    tab.id = "sharedTab";
    tab.text = text;
    tab.modified = true;
    tab.language = "python";
    data.tabs.append(tab);
    return data;
}

/** @brief 保存結果を検査する。 @param store ストア。 @param data セッション。 */
void save(mce::SessionStore& store, const mce::SessionData& data) {
    QString error;
    if (!store.save(data, &error)) { throw std::runtime_error(error.toStdString()); }
}

/** @brief 再起動相当の読込を行う。 @param path 保存基準。 @return 復元内容。 */
mce::SessionData load(const QString& path) {
    mce::SessionStore store(path);
    mce::SessionData data;
    require(store.open(&data) == mce::SessionStore::OpenResult::Loaded, "load recovery");
    return data;
}

/** @brief 復元本文の集合を返す。 @param data セッション。 @return 本文一覧。 */
QStringList texts(const mce::SessionData& data) {
    QStringList result;
    for (const auto& tab : data.tabs) { result.append(tab.text); }
    result.sort();
    return result;
}

/** @brief 世代IDを読む。 @param path 保存基準。 @return 世代一覧。 */
QStringList snapshots(const QString& path) {
    return QDir(path + ".recovery/snapshots").entryList({"*.json"}, QDir::Files, QDir::Name);
}

/** @brief 別プロセスの準備を待つ。 @param path 合図ファイル。 */
void waitFor(const QString& path) {
    QElapsedTimer timer;
    timer.start();
    while (!QFile::exists(path) && timer.elapsed() < 15000) { QThread::msleep(10); }
    require(QFile::exists(path), "worker signal timeout");
}

/** @brief 強制終了対象のプロセス。 @param args 起動引数。 @return 通常は戻らない。 */
int worker(const QStringList& args) {
    mce::SessionStore store(args[2]);
    mce::SessionData data;
    require(store.open(&data) == mce::SessionStore::OpenResult::Loaded, "worker load");
    write(args[3] + ".ready", "ready");
    waitFor(args[3] + ".go");
    data.tabs[0].text = args[4];
    save(store, data);
    write(args[3] + ".saved", "saved");
    for (;;) { QThread::msleep(1000); }
}

/** @brief 既存版移行・同時編集・遅い旧画面・破損・失敗再試行を検証する。 */
void recoveryPasses() {
    QTemporaryDir temp;
    const QString path = temp.path() + "/tabs.json";
    // 旧本文は読込専用。別の旧Mayaのロックがあっても新しい保管先へ保存できる。
    QDir().mkpath(temp.path() + "/tabs");
    const auto original = sample(QString::fromUtf8("# 日本語\nbase = 1\n"));
    const QByteArray legacy = mce::sessionToJson(original);
    write(path, legacy);
    write(temp.path() + "/tabs/sharedTab.txt", original.tabs[0].text.toUtf8());
    write(path + ".lock", "old Maya lock");
    write(temp.path() + "/tabs/orphan.txt", "do not delete");
    mce::SessionStore a(path);
    mce::SessionData ad;
    require(a.open(&ad) == mce::SessionStore::OpenResult::Loaded, "legacy load with lock");
    save(a, ad);
    const QString first = snapshots(path).first();
    const QString originalBody = a.textPath("sharedTab");
    QFile old(path); require(old.open(QIODevice::ReadOnly) && old.readAll() == legacy, "legacy unchanged"); old.close();
    require(QFile::exists(temp.path() + "/tabs/orphan.txt"), "orphan preserved");
    mce::SessionStore b(path);
    mce::SessionData bd;
    require(b.open(&bd) == mce::SessionStore::OpenResult::Loaded && b.canSave(), "second writer enabled");
    ad.tabs[0].text = "branch A";
    bd.tabs[0].text = "branch B";
    save(a, ad); save(b, bd);
    require(texts(load(path)) == QStringList({"branch A", "branch B"}), "concurrent conflict retained");
    mce::SessionStore merged(path);
    mce::SessionData md;
    merged.open(&md); save(merged, md);
    require(texts(load(path)) == texts(md), "merged restart deduplicated");
    ad.tabs[0].text = "branch A later"; save(a, ad);
    const auto later = texts(load(path));
    require(later.contains("branch A later") && later.contains("branch B"), "old running writer not suppressed");
    mce::SessionData historical;
    require(merged.readSnapshot(QFileInfo(first).completeBaseName(), &historical)
        && texts(historical) == texts(original), "historical text retained");
    require(QFile::exists(originalBody), "old body retained");
    qInfo() << "PASS migration, simultaneous edits, merged restart, late writer, retained history";

    // 確定直前の失敗。新本文は存在しても、前の世代を上書きしない。再試行で新世代を確定できる。
    QTemporaryDir failure;
    const QString fp = failure.path() + "/tabs.json";
    mce::SessionStore fs(fp); mce::SessionData fd;
    fs.open(&fd); save(fs, sample("before"));
    const QString snapshotsDir = fp + ".recovery/snapshots";
    require(QDir().rename(snapshotsDir, snapshotsDir + ".held"), "block commit setup");
    write(snapshotsDir, "block directory");
    QString error;
    require(!fs.save(sample("after"), &error) && !error.isEmpty(), "commit must fail");
    require(fs.jsonWrites() == 1, "failed commit not marked saved");
    require(QFile::remove(snapshotsDir) && QDir().rename(snapshotsDir + ".held", snapshotsDir), "unblock commit");
    require(texts(load(fp)) == QStringList{"before"}, "incomplete commit ignored");
    save(fs, sample("after"));
    require(texts(load(fp)) == QStringList{"after"}, "retry committed");
    write(fs.textPath("sharedTab"), "corrupt");
    require(texts(load(fp)) == QStringList{"before"}, "bad body falls back");
    write(snapshotsDir + "/broken.json", "{");
    require(texts(load(fp)) == QStringList{"before"}, "bad metadata preserved fallback");
    require(QFile::exists(snapshotsDir + "/broken.json"), "bad metadata not removed");
    qInfo() << "PASS commit failure, retry, partial file, corrupt body and corrupt metadata";

    // タブ閉じは次回の一覧から除くが、過去世代には本文が残る。
    QTemporaryDir closed;
    const QString cp = closed.path() + "/tabs.json";
    mce::SessionStore cs(cp); mce::SessionData cd; cs.open(&cd);
    cd = sample("keep"); auto removed = cd.tabs[0]; removed.id = "closedTab"; removed.text = "closed code";
    cd.tabs.append(removed); save(cs, cd);
    const QString closedBody = cs.textPath(removed.id);
    cd.tabs.removeLast(); cd.tabs[0].textLoaded = false; save(cs, cd);
    require(texts(load(cp)) == QStringList{"keep"} && QFile::exists(closedBody), "closed tab retained only in history");
    const int writes = cs.textWrites(); save(cs, cd);
    require(cs.textWrites() == writes && cs.jsonWrites() == 2, "unchanged no writes");
    qInfo() << "PASS close tab, history preservation and unchanged body reuse";

    // 本当に別プロセスから同じ保存先へ書き、終了ハンドラーを呼ばずに停止する。
    QTemporaryDir processes;
    const QString pp = processes.path() + "/tabs.json";
    mce::SessionStore ps(pp); mce::SessionData pd; ps.open(&pd); save(ps, sample("seed"));
    QProcess left, right;
    left.start(QCoreApplication::applicationFilePath(), {"--worker", pp, pp + "L", "left unsaved"});
    right.start(QCoreApplication::applicationFilePath(), {"--worker", pp, pp + "R", "right unsaved"});
    require(left.waitForStarted() && right.waitForStarted(), "start workers");
    waitFor(pp + "L.ready"); waitFor(pp + "R.ready");
    write(pp + "L.go", "go"); write(pp + "R.go", "go");
    waitFor(pp + "L.saved"); waitFor(pp + "R.saved");
    right.kill(); require(right.waitForFinished(), "kill right");
    left.kill(); require(left.waitForFinished(), "kill left");
    require(texts(load(pp)) == QStringList({"left unsaved", "right unsaved"}), "killed processes recovered");
    qInfo() << "PASS two real processes, reversed forced exit and recovery";

    QTemporaryDir perf;
    mce::SessionStore timed(perf.path() + "/tabs.json"); mce::SessionData td; timed.open(&td);
    td = sample(QString(100000, 'a'));
    QElapsedTimer timer; timer.start();
    for (int edit = 0; edit < 100; ++edit) { td.tabs[0].text.append(QString::number(edit)); save(timed, td); }
    qInfo() << "PERF 100 edits of 100 KB:" << timer.elapsed() << "ms";
}

}  // namespace

/** @brief テストと専用子プロセスの入口。 @param argc 引数数。 @param argv 引数。 @return 成功0、失敗1。 */
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    try {
        if (app.arguments().value(1) == "--worker") { return worker(app.arguments()); }
        recoveryPasses();
        return 0;
    } catch (const std::exception& error) {
        qCritical() << "FAIL" << error.what();
        return 1;
    }
}
