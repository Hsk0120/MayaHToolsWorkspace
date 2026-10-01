/** @file hedit_command.cpp
 * @brief HeditCommandの実装。
 */
#include "plugin/hedit_command.h"
#include "plugin/dock.h"
#include "plugin/editor_host.h"
#include "plugin/mel.h"
#include "plugin/user_paths.h"
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
    // -show、またはフラグなし: 画面を開く。-floatingを付けたときだけ浮動状態を変える。
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

}  // namespace hedit
