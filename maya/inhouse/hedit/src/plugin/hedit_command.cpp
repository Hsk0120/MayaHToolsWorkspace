/** @file hedit_command.cpp
 * @brief HeditCommandの実装。
 */
#include "plugin/hedit_command.h"
#include "plugin/dock.h"
#include "plugin/editor_host.h"
#include "plugin/mel.h"
#include "plugin/python_bridge.h"
#include "plugin/user_paths.h"
#include "core/completion_types.h"
#include <maya/MArgDatabase.h>
#include <maya/MGlobal.h>
#include <optional>

namespace hedit {

void* HeditCommand::creator() {
    return new HeditCommand;
}

MSyntax HeditCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-sh", "-show");
    syntax.addFlag("-f", "-floating", MSyntax::kBoolean);
    syntax.addFlag("-r", "-restore");
    syntax.addFlag("-ss", "-saveState");
    syntax.addFlag("-sp", "-sessionPath");
    syntax.addFlag("-cl", "-closed");
    syntax.addFlag("-qt", "-quitting");
    syntax.addFlag("-cp", "-complete", MSyntax::kString);
    syntax.addFlag("-dc", "-declarations", MSyntax::kString);
    syntax.addFlag("-ds", "-describe", MSyntax::kString);
    return syntax;
}

MStatus HeditCommand::doIt(const MArgList& args) {
    MStatus status;
    MArgDatabase flags(syntax(), args, &status);
    if (!status) {
        return status;
    }

    if (flags.isFlagSet("-sp")) {
        // 画面を作らないので、バッチやmayapyでも使える。
        setResult(toMString(sessionFilePath()));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-cp") || flags.isFlagSet("-dc")) {
        // テスト用: 画面を作らずに、C++の補完・宣言の抽出の結果をJSONで返す(mayapyでも使える)。
        const bool complete = flags.isFlagSet("-cp");
        MString source;
        flags.getFlagArgument(complete ? "-cp" : "-dc", 0, source);
        const QByteArray json = complete ? completionResultToJson(python::complete(fromMString(source)))
                                         : python::declarationsJson(fromMString(source));
        setResult(toMString(QString::fromUtf8(json)));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-ds")) {
        // テスト用: 本文の末尾の名前のホバーの説明をJSONで返す(画面を作らないので、mayapyでも使える)。
        MString source;
        flags.getFlagArgument("-ds", 0, source);
        const QString text = fromMString(source);
        setResult(toMString(QString::fromUtf8(hoverInfoToJson(python::describe(text, text.size())))));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-cl")) {
        dock::onClosed();
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-qt")) {
        dock::onQuitting();
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-ss")) {
        dock::saveState();
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-r")) {
        return dock::restore() ? MS::kSuccess : MS::kFailure;
    }
    if (flags.isFlagSet("-sh")) {
        // std::optionalは「値が無い」状態を持てる型。-floatingを付けなければ空のまま(配置を変えない)。
        std::optional<bool> floating;
        if (flags.isFlagSet("-f")) {
            bool value = false;
            flags.getFlagArgument("-f", 0, value);
            floating = value;
        }
        if (MGlobal::mayaState() != MGlobal::kInteractive) {
            MGlobal::displayError("hedit UI requires interactive Maya.");
            return MS::kFailure;
        }
        dock::show(floating);
        return MS::kSuccess;
    }

    // フラグなし: 画面のアドレスを文字列で返す(テストがPySideで画面を取り出すのに使う)。
    QMainWindow* editor = host::editor(true);
    if (!editor) {
        return MS::kFailure;
    }
    setResult(MString(QString::number(reinterpret_cast<quintptr>(editor)).toLatin1().constData()));
    return MS::kSuccess;
}

}  // namespace hedit
