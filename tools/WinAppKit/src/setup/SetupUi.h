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
    bool commandLinks = false;  ///< ボタンを縦に並べた大きな選択肢(コマンドリンク)にするか。文字の「\n」以降は小さな説明になる。
};

/** @brief 関連付けの選択(関連付けの画面で選ぶ内容)。 */
struct AssociationChoice {
    std::vector<std::wstring> extensions;  ///< 候補の拡張子。
    std::vector<bool> selected;            ///< 拡張子ごとに、関連付けるか(extensionsと同じ数)。
    /// 拡張子ごとに、関連付けられるか(前提の拡張機能が入っているか。extensionsと同じ数。空ならすべて選べる)。
    std::vector<bool> available;
    std::wstring unavailableNote;          ///< 選べない拡張子があるときに、画面の下に出す説明。
    bool hasContextMenu = false;           ///< 右クリックの項目を出せるアプリか(出せなければ選択肢を出さない)。
    bool contextMenu = true;               ///< 右クリックに項目を出すか。
};

/**
 * @brief 関連付けを選ぶ画面を出す。拡張子ごとのチェックボックス・すべて選択/解除・右クリックに出すかを選べる。
 * @param title ウィンドウのタイトル。
 * @param appName アプリの表示名(説明の文に使う)。
 * @param choice 最初の状態。「決定」なら選んだ内容で書き換える。
 * @return 「決定」ならtrue、取り消されたらfalse(choiceは変えない)。
 * @note チェックボックスを並べる必要があるので、タスクダイアログではなく、メモリ上で組み立てたダイアログを使う。
 */
bool chooseAssociations(const std::wstring& title, const std::wstring& appName, AssociationChoice& choice);

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
