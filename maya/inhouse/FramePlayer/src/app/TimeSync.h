/**
 * @file TimeSync.h
 * @brief タイムスライダーを外部のアプリ(Mayaなど)と連携させるための窓口。
 */
#pragma once

namespace frameplayer {

/**
 * @brief タイムスライダーの変化を外部へ知らせる窓口。連携の方式(Mayaのcommandなど)ごとに派生クラスを作る。
 * @note フレーム番号はタイムスライダーに表示している番号(動画の1コマ目が開始フレーム)で渡す。
 *       Mayaのフレームとの対応(オフセット・倍率など)は派生クラス側で行う。
 *       どの関数もUIスレッドから呼ばれる。時間のかかる通信は派生クラス側で別のスレッドに任せること。
 *
 *       外部からFramePlayerを動かすときは、PlayerWindowのgoToSceneFrame()・setPlaybackRangeScene()・
 *       setPlaying()を使う(UIスレッドから呼ぶ。別スレッドで受け取った場合はPostMessageで渡す)。
 */
class TimeSync {
public:
    /** @brief 派生クラスの資源(接続など)を解放する。 */
    virtual ~TimeSync() = default;

    /**
     * @brief 現在のフレームが変わった。再生中は表示するコマが変わるたびに呼ばれる。
     * @param frame 現在のフレーム番号。
     */
    virtual void currentFrameChanged(int frame) = 0;

    /**
     * @brief 再生範囲が変わった。
     * @param first 範囲の最初のフレーム番号。
     * @param last 範囲の最後のフレーム番号。
     */
    virtual void playbackRangeChanged(int first, int last) = 0;

    /**
     * @brief 再生を始めた、または止めた。
     * @param playing 再生中ならtrue。
     */
    virtual void playStateChanged(bool playing) = 0;
};

}  // namespace frameplayer
