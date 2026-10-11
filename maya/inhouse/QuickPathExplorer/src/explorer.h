/** @file explorer.h
 * @brief Maya非依存のカラム型ファイル閲覧画面と計測入口。
 */
#pragma once
#include <QWidget>
#include <QString>
#ifdef QPE_BUILD
#define QPE_API __declspec(dllexport)
#else
#define QPE_API __declspec(dllimport)
#endif
/** @brief 呼出元のQtイベントループに所属する画面を作る。
 * @param parent 所有者。nullptrでは呼出元が破棄する。
 * @return 新規画面。UIスレッドからだけ呼び出す。
 */
extern "C" QPE_API QWidget* qpeCreate(QWidget* parent);
/** @brief 共通シナリオを実行しJSONを保存する。
 * @param widget qpeCreateで作成した有効な画面。
 * @param config UTF-8の設定ファイルパス。
 * @param output UTF-8の結果ファイルパス。
 * @return 成功時0、検証失敗時1。
 * @note Qtイベントを処理するため、専用検証プロセスで使用する。
 */
extern "C" QPE_API int qpeBenchmark(QWidget* widget, const char* config, const char* output);
