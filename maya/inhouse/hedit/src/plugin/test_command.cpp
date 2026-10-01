/** @file test_command.cpp
 * @brief HeditTestCommandの実装。
 */
#include "plugin/test_command.h"
#include "core/completion_types.h"
#include "plugin/editor_host.h"
#include "plugin/mel.h"
#include "plugin/python_bridge.h"
#include <maya/MArgDatabase.h>
#include <QMainWindow>

namespace hedit {

bool HeditTestCommand::enabled() {
    return qEnvironmentVariable("HEDIT_TEST_COMMANDS") == QLatin1String("1");
}

void* HeditTestCommand::creator() {
    return new HeditTestCommand;
}

MSyntax HeditTestCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-ed", "-editor");
    syntax.addFlag("-cp", "-complete", MSyntax::kString);
    syntax.addFlag("-dc", "-declarations", MSyntax::kString);
    syntax.addFlag("-ds", "-describe", MSyntax::kString);
    return syntax;
}

MStatus HeditTestCommand::doIt(const MArgList& args) {
    MStatus status;
    MArgDatabase flags(syntax(), args, &status);
    if (!status) {
        return status;
    }
    MString source;
    if (flags.isFlagSet("-cp")) {
        // 画面を作らずに、C++の補完の結果をJSONで返す(mayapyでも使える)。
        flags.getFlagArgument("-cp", 0, source);
        setResult(toMString(QString::fromUtf8(completionResultToJson(python::complete(fromMString(source))))));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-dc")) {
        flags.getFlagArgument("-dc", 0, source);
        setResult(toMString(QString::fromUtf8(python::declarationsJson(fromMString(source)))));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-ds")) {
        flags.getFlagArgument("-ds", 0, source);
        const QString text = fromMString(source);
        setResult(toMString(QString::fromUtf8(hoverInfoToJson(python::describe(text, text.size())))));
        return MS::kSuccess;
    }
    if (flags.isFlagSet("-ed")) {
        // 画面のアドレスを文字列で返す(テストがPySideで画面を取り出すのに使う)。
        QMainWindow* editor = host::editor(true);
        if (!editor) {
            return MS::kFailure;
        }
        setResult(MString(QString::number(reinterpret_cast<quintptr>(editor)).toLatin1().constData()));
        return MS::kSuccess;
    }
    displayError("heditTest: specify -editor, -complete, -declarations or -describe.");
    return MS::kFailure;
}

}  // namespace hedit
