/** @file module_scanner.h
 * @brief ``import xxx`` / ``from xxx`` のトップレベル名の補完を、Pythonを介さずに行う。
 * @details sys.pathのフォルダーの中身を調べるだけの処理なので、PythonのGIL(一度に1つのスレッドしか
 * Pythonを実行できないようにするロック)を取らないC++のスレッドで行い、Mayaの画面を止めない。
 * Mayaには依存しないため、tests/ui_smoke.cppでも検証する。
 *
 * 使い方:
 * - 編集画面の作成時に ModuleScanner::refresh() で走査を始める。
 * - Ctrl+Spaceのたびに topLevelImportPrefix() で対象の行かを判定し、
 *   ModuleScanner::names() の結果を completionItems() でJSONにする。
 */
#pragma once
#include "core/completion_types.h"
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
 * @return importできるトップレベルの名前。``*.py``のファイル名(拡張子なし)、拡張モジュール
 * (``name.pyd``・``name.cp311-win_amd64.pyd``)の最初の点より前の名前、フォルダー名のうち、
 * Pythonの識別子として使えるもの(``my-tool.py``のような名前はimportできないので除く)。
 */
QSet<QString> scanTopLevel(const QStringList& paths, const std::atomic_bool* cancel = nullptr);

/** @brief 本文の末尾が、トップレベル名を補完する``import``/``from``の行か。
 * @param source カーソルまでの本文。
 * @param prefix 補完中の名前の途中(例: ``import hl``なら``hl``)を入れる。nullptrなら入れない。
 * @return ``import xxx``/``from xxx``で、名前にドットを含まない場合true。
 */
bool topLevelImportPrefix(const QString& source, QString* prefix);

/** @brief 候補の名前から、補完の結果を作る。
 * @param names 候補の名前。
 * @param prefix 補完中の名前の途中。``_``で始まらなければ``_``で始まる名前を除く。
 * @param pending 走査が進行中ならtrue(エディタが少し後に問い合わせ直す)。
 * @return 入力との一致の度合いのよい順(fuzzyScore)で最大250件の候補。
 */
CompletionResult completionItems(const QSet<QString>& names, const QString& prefix, bool pending);

/** @brief sys.pathのトップレベル名を別スレッドで走査し、結果を保持する。
 * @details 結果の読み書きはmutex(同時に1つのスレッドだけが入れる鍵)で守る。
 * 走査中のスレッドはstop()(またはデストラクター)で止めて合流(join)させる。
 * hedit.mllのアンロード後に、解放済みのスレッドのコードが動かないようにするため。
 */
class ModuleScanner {
public:
    /** @brief 走査器を作る。まだ走査は始めない。
     * @param minimumInterval 次の走査を始めるまでの最短の間隔(ミリ秒)。
     */
    explicit ModuleScanner(int minimumInterval = 5000);

    /** @brief 走査中なら止めて合流する。 */
    ~ModuleScanner();

    /** @brief 走査を始める。実行中、または前回の開始から最短の間隔が経っていなければ何もしない。
     * @param paths sys.pathの各フォルダー。
     */
    void refresh(const QStringList& paths);

    /** @brief 最初の走査が終わるまで待つ。
     * @param milliseconds 待つ上限(ミリ秒)。
     * @return 最初の走査が終わっていればtrue。
     */
    bool waitForFirst(int milliseconds);

    /** @brief 直近の走査結果の写しを返す。
     * @param pending 走査中ならtrueを入れる。nullptrなら入れない。
     * @return 名前の集合。
     */
    QSet<QString> names(bool* pending = nullptr) const;

    /** @brief 走査中なら止めて合流する。 */
    void stop();

private:
    /** @brief 別スレッドで走査し、結果を差し替える。
     * @param paths 走査するフォルダー。スレッドへ値で渡す(呼出し元の変数の寿命に依存しない)。
     */
    void run(QStringList paths);

    mutable std::mutex mutex_;                 ///< 下の結果と状態を守る鍵。
    std::condition_variable finished_;         ///< 走査の完了を待つ側へ知らせる。
    std::thread worker_;                       ///< 走査用のスレッド。
    std::atomic_bool cancel_{false};           ///< trueで走査を途中でやめる。
    QSet<QString> scanned_;                    ///< 直近の完全な走査結果。
    bool completed_ = false;                   ///< 1回でも走査を終えたか。
    bool running_ = false;                     ///< 走査中か。
    QElapsedTimer started_;                    ///< 前回の走査を始めてからの時間。
    int interval_;                             ///< 次の走査までの最短の間隔(ミリ秒)。
};

}  // namespace hedit
