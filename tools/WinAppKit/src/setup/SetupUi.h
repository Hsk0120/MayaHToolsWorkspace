/**
 * @file SetupUi.h
 * @brief セットアップの画面。Windows標準のタスクダイアログ(TaskDialogIndirect)で、確認・進み具合・完了・エラーを出す。
 */
#pragma once

#include <windows.h>

#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace wak {

/** @brief ダイアログの左上に出す絵。 */
enum class DialogIcon { App, Information, Warning, Error };

/** @brief ダイアログの中身。 */
struct DialogSpec {
    std::wstring title;        ///< ウィンドウのタイトル。
    std::wstring instruction;  ///< 大きく出す見出し。
    std::wstring content;      ///< 本文。<a href="...">…</a> でリンクを書ける。
    std::vector<std::pair<int, std::wstring>> buttons;  ///< 自分で用意するボタン(番号と文字)。
    bool cancelButton = false;     ///< 「キャンセル」(IDCANCEL)を出すか。
    bool closeButton = false;      ///< 「閉じる」(IDCLOSE)を出すか。
    int defaultButton = 0;         ///< 最初に選ばれているボタン(0なら最初のボタン)。
    std::wstring verification;     ///< 下のチェックボックスの文字(空なら出さない)。
    bool verificationChecked = false;  ///< チェックボックスの最初の状態。
    DialogIcon icon = DialogIcon::App;
    std::function<void(const std::wstring&)> onLink;  ///< リンクが押されたときに呼ぶ(hrefを渡す)。
};

/** @brief ダイアログの結果。 */
struct DialogResult {
    int button = IDCANCEL;  ///< 押されたボタン。
    bool verification = false;  ///< チェックボックスの状態。
};

/**
 * @brief ダイアログを出し、閉じるまで待つ。
 * @param spec 中身。
 * @return 押されたボタンと、チェックボックスの状態。
 */
DialogResult showDialog(const DialogSpec& spec);

/**
 * @brief 進み具合のダイアログを出し、作業(別のスレッドで動かす)が終わったら閉じる。
 * @param title ウィンドウのタイトル。
 * @param instruction 見出し。
 * @param work 作業。進み具合(0〜100)と説明を知らせる関数を受け取る。作業は別のスレッドで動く。
 * @note 作業中は閉じられない(途中で止めると中途半端になるため。失敗したときの巻き戻しは作業の側で行う)。
 */
void runWithProgress(const std::wstring& title, const std::wstring& instruction,
                     const std::function<void(const std::function<void(int, const std::wstring&)>&)>& work);

/**
 * @brief フォルダを選ぶ画面を出す。
 * @param title 画面のタイトル。
 * @param initial 最初に開くフォルダ。
 * @return 選んだフォルダ。取り消されたら空。
 */
std::wstring chooseFolder(const std::wstring& title, const std::wstring& initial);

}  // namespace wak
