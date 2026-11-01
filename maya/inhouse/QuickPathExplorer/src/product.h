/** @file product.h @brief 製品と固定検証ビルドの識別名を分離する。 */
#pragma once
#ifdef QPE_PRODUCT_BUILD
#define QPE_COMMAND "quickPathExplorer"
#define QPE_CONTROL "QuickPathExplorerWorkspaceControl"
#define QPE_MENU "quickPathExplorerWindowMenuItem"
#define QPE_LABEL "QuickPathExplorer"
#define QPE_VERSION "1.0.0"
#else
#define QPE_COMMAND "quickPathExplorerNative"
#define QPE_CONTROL "QPENativeMigrationWorkspaceControl"
#define QPE_MENU "qpeNativeMenu"
#define QPE_LABEL "QuickPathExplorer C++"
#define QPE_VERSION "1.0.0-validation"
#endif
