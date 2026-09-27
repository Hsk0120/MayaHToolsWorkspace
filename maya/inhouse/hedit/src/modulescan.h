/** @file modulescan.h
 * @brief ``import xxx`` / ``from xxx`` のトップレベル名の補完を、Pythonを介さずに行う。
 * @details 旧hedit.completion.Index.scan_top(Pythonのスレッド)をC++へ移したもの。
 * sys.pathのフォルダー一覧の走査はファイル入出力だけなので、PythonのGIL(グローバルロック)を
 * 取らないC++のスレッドで行い、Mayaのメインスレッドを引っかからせない。Mayaには依存しないため、
 * オフスクリーンのテスト(tests/ui_smoke.cpp)でも検証する。
 */
#pragma once
#include <QByteArray>
#include <QElapsedTimer>
#include <QSet>
#include <QString>
#include <QStringList>
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>

namespace hedit {
/** @brief Pythonの識別子として使える名前か(str.isidentifierの近似)。
 * @param name 調べる名前。
 * @return 先頭が文字か``_``で、残りが文字・数字・``_``ならtrue。
 */
bool isIdentifier(const QString& name);
/** @brief フォルダーの直下から、importできるトップレベルの名前を集める。
 * @param paths sys.pathの各フォルダー。存在しない・読めないものは飛ばす。
 * @param cancel trueになったら途中でやめる。nullptrなら最後まで走査する。
 * @return ``*.py``のファイル名(拡張子なし)と、識別子として使えるフォルダー名。
 */
QSet<QString> scanTopLevel(const QStringList& paths, const std::atomic_bool* cancel = nullptr);
/** @brief 本文の末尾が、トップレベル名を補完する``import``/``from``の行か。
 * @param source カーソルまでの本文。
 * @param prefix 補完中の名前の途中(例: ``import hl``なら``hl``)。
 * @return ``import xxx``/``from xxx``で、名前にドットを含まない場合true。
 */
bool topLevelImportPrefix(const QString& source, QString* prefix);
/** @brief 候補の名前から、エディタへ返す補完のJSONを作る。
 * @param names 候補の名前。
 * @param prefix 補完中の名前の途中。``_``で始まらなければ``_``で始まる名前を除く。
 * @param pending 走査が進行中ならtrue(エディタが少し後に問い合わせ直す)。
 * @return ``{"items":[{"name","detail"}...],"pending":bool}``。名前順で最大250件。
 */
QByteArray completionItems(const QSet<QString>& names, const QString& prefix, bool pending);

/** @brief sys.pathのトップレベル名を別スレッドで走査し、結果を保持する。
 * @details 結果の読み書きはmutexで守る。走査中のスレッドはstop()(またはデストラクター)で
 * 止めて合流させる。hedit.mllのアンロード後にスレッドのコードが動かないようにするため。
 */
class ModuleScanner {
public:
    /** @brief 走査器を作る。 @param minimumInterval 次の走査を始めるまでの最短の間隔(ミリ秒)。 */
    explicit ModuleScanner(int minimumInterval = 5000);
    /** @brief 走査中なら止めて合流する。 */
    ~ModuleScanner();
    /** @brief 走査を始める。実行中、または前回の開始から最短の間隔が経っていなければ何もしない。
     * @param paths sys.pathの各フォルダー。
     */
    void refresh(const QStringList& paths);
    /** @brief 最初の走査が終わるまで待つ。
     * @param milliseconds 待つ上限。
     * @return 最初の走査が終わっていればtrue。
     */
    bool waitForFirst(int milliseconds);
    /** @brief 直近の走査結果の写し。 @param pending 走査中ならtrueを入れる。 @return 名前の集合。 */
    QSet<QString> names(bool* pending = nullptr) const;
    /** @brief 走査中なら止めて合流する。 */
    void stop();

private:
    /** @brief 別スレッドで走査し、結果を差し替える。 @param paths 走査するフォルダー。 */
    void run(QStringList paths);
    mutable std::mutex mutex;
    std::condition_variable finished;
    std::thread worker;
    std::atomic_bool cancel{false};
    QSet<QString> scanned;
    bool completed = false;
    bool running = false;
    QElapsedTimer started;
    int interval;
};
}
