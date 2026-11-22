/** @file session_recovery.cpp
 * @brief 多重起動・強制終了・移行・最新状態のみの保管を専用データで検証する。
 */
#include "editor/session_store.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDebug>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QLockFile>
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
    require(!QFile::exists(path + ".recovery/snapshots/" + first), "historical manifest removed");
    require(!QFile::exists(originalBody), "old body removed");
    require(snapshots(path).size() == 2, "only concurrent heads retained");
    require(QFile::remove(path + ".lock"), "remove old fixture lock");
    save(a, ad);
    require(!QFile::exists(path) && !QFile::exists(temp.path() + "/tabs/orphan.txt"), "legacy history removed after commit");
    qInfo() << "PASS migration, simultaneous edits, merged restart, late writer, latest heads only";

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
    mce::SessionStore corrupt(fp); mce::SessionData unreadable;
    require(corrupt.open(&unreadable) == mce::SessionStore::OpenResult::Unreadable, "no retired history fallback");
    write(snapshotsDir + "/broken.json", "{");
    save(fs, sample("after repair"));
    require(texts(load(fp)) == QStringList{"after repair"}, "available current state recovered");
    require(QFile::exists(snapshotsDir + "/broken.json"), "bad metadata not removed");
    qInfo() << "PASS commit failure, retry, partial file, corrupt body and corrupt metadata";

    // タブ閉じは次回の一覧と保管本文から除く。
    QTemporaryDir closed;
    const QString cp = closed.path() + "/tabs.json";
    mce::SessionStore cs(cp); mce::SessionData cd; cs.open(&cd);
    cd = sample("keep"); auto removed = cd.tabs[0]; removed.id = "closedTab"; removed.text = "closed code";
    cd.tabs.append(removed); save(cs, cd);
    const QString closedBody = cs.textPath(removed.id);
    cd.tabs.removeLast(); cd.tabs[0].textLoaded = false; save(cs, cd);
    require(texts(load(cp)) == QStringList{"keep"} && !QFile::exists(closedBody), "closed tab body removed");
    const int writes = cs.textWrites(); save(cs, cd);
    require(cs.textWrites() == writes && cs.jsonWrites() == 2, "unchanged no writes");
    require(snapshots(cp).size() == 1, "only latest state on close");
    write(cs.textPath(cd.tabs[0].id), "externally damaged body");
    require(!cs.save(cd, &error), "changed file invalidates verified unchanged-body cache");
    qInfo() << "PASS close tab removal and unchanged body reuse";

    // 古い画面の未表示タブも、別Mayaが本文を整理した後に再保存できる。
    QTemporaryDir stale;
    const QString sp = stale.path() + "/tabs.json";
    mce::SessionStore sa(sp), sb(sp); mce::SessionData sd, staleData;
    sa.open(&sd); save(sa, sample("old pending body")); sb.open(&staleData);
    const auto oldBody = sb.textPath("sharedTab");
    save(sa, sample("new body"));
    require(!QFile::exists(oldBody), "obsolete body actually removed");
    staleData.tabs[0].textLoaded = false;
    save(sb, staleData);
    require(texts(load(sp)) == QStringList({"new body", "old pending body"}), "pending tab rehydrated after pruning");
    qInfo() << "PASS live unmodified tab survives other writer pruning";

    // 旧版の長い履歴を一度の保存で整理する。最新状態を確定する前は何も消さない。
    QTemporaryDir history;
    const QString hp = history.path() + "/tabs.json";
    mce::SessionStore hs(hp); mce::SessionData hd; hs.open(&hd); save(hs, sample("current"));
    const auto initial = snapshots(hp).first();
    QFile manifest(hp + ".recovery/snapshots/" + initial);
    require(manifest.open(QIODevice::ReadOnly), "read seed manifest");
    auto root = QJsonDocument::fromJson(manifest.readAll()).object(); manifest.close();
    QString parent = QFileInfo(initial).completeBaseName();
    for (int index = 0; index < 1276; ++index) {
        const QString id = "history" + QString::number(index);
        root.insert("parents", QJsonArray{parent});
        write(hp + ".recovery/snapshots/" + id + ".json", QJsonDocument(root).toJson());
        parent = id;
    }
    mce::SessionStore migrated(hp); migrated.open(&hd);
    require(snapshots(hp).size() == 1277, "open alone preserves legacy generations");
    save(migrated, hd);
    require(snapshots(hp).size() == 1 && texts(load(hp)) == QStringList{"current"}, "old history compacted to current");
    qInfo() << "PASS 1277 old generations migrate to one current state";

    // ロック取得中は読み取りも保存も開始しない。失敗後に同じ保存を再試行できる。
    {
        QLockFile lock(hp + ".recovery/store.lock");
        require(lock.tryLock(), "hold store lock");
        mce::SessionStore blocked(hp); mce::SessionData blockedData;
        require(blocked.open(&blockedData) == mce::SessionStore::OpenResult::Unreadable
            && !blocked.canSave(), "contended open cannot overwrite recovered tabs");
        require(!migrated.save(sample("retry after lock"), &error), "contended save waits for retry");
        lock.unlock();
        save(migrated, sample("retry after lock"));
        require(texts(load(hp)) == QStringList{"retry after lock"}, "lock retry preserves state");
    }
    qInfo() << "PASS contended open/save do not overwrite current state";

    // GUIは本文を同期確定し、整理だけ次のイベントへまとめる。再起動は最新だけを読む。
    QTemporaryDir queued;
    const QString qp = queued.path() + "/tabs.json";
    mce::SessionStore qs(qp); mce::SessionData qd; qs.open(&qd);
    save(qs, sample("before queued cleanup"));
    require(qs.save(sample("latest before cleanup"), &error, false), "deferred cleanup save");
    require(snapshots(qp).size() == 2 && texts(load(qp)) == QStringList{"latest before cleanup"},
        "crash before cleanup still restores latest only");
    require(qs.discardHistory() && snapshots(qp).size() == 1, "queued cleanup removes earlier generation");
    qInfo() << "PASS deferred cleanup keeps synchronous durable save";

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
    require(snapshots(perf.path() + "/tabs.json").size() == 1, "editing never accumulates history");
    require(QDir(perf.path() + "/tabs.json.recovery/bodies").entryList({"*.qz"}, QDir::Files).size() == 1,
        "editing never accumulates bodies");
    qInfo() << "PERF 100 edits of 100 KB:" << timer.elapsed() << "ms";
}

}  // namespace

/** @brief テストと専用子プロセスの入口。 @param argc 引数数。 @param argv 引数。 @return 成功0、失敗1。 */
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    try {
        if (app.arguments().value(1) == "--worker") { return worker(app.arguments()); }
        if (app.arguments().value(1) == "--benchmark") {
            // コピーした専用セッションだけを指定する。本文はログへ出さずハッシュで一致を調べる。
            for (int run = 0; run < 3; ++run) {
                QElapsedTimer timer; timer.start();
                const auto data = load(app.arguments().value(2));
                const auto elapsed = timer.nsecsElapsed() / 1000000.0;
                QCryptographicHash hash(QCryptographicHash::Sha256);
                for (const auto& tab : data.tabs) { hash.addData(tab.text.toUtf8()); }
                qInfo() << "RESTORE" << run << "ms" << elapsed << "tabs" << data.tabs.size() << "sha256" << hash.result().toHex();
            }
            return 0;
        }
        recoveryPasses();
        return 0;
    } catch (const std::exception& error) {
        qCritical() << "FAIL" << error.what();
        return 1;
    }
}
