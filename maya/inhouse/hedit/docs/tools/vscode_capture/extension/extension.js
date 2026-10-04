// hedit の検索バーを VS Code と見比べるための撮影用拡張機能(capture.py が一時的に読み込む。配布はしない)。
// 環境変数 HEDIT_VSCODE_SCRIPT が指す JSON の手順を、VS Code の起動後に上から順に実行する。
//   {"file": 開くファイル, "selection": [行, 列, 行, 列], "done": 完了の印を書くファイル,
//    "steps": [
//      {"command": コマンドID, "args": 引数},   // VS Code のコマンドを実行する("noWait": true で完了を待たない)
//      {"wait": ミリ秒},                         // 待つ
//      {"select": [行, 列, 行, 列]},             // 選択範囲を変える(行・列は0始まり)
//      {"capture": 名前, "settle": ミリ秒}       // 撮影の合図を出し、capture.py が撮り終わるまで待つ
//    ]}
const vscode = require('vscode');
const fs = require('fs');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function activate() {
    const scriptPath = process.env.HEDIT_VSCODE_SCRIPT;
    if (!scriptPath || !fs.existsSync(scriptPath)) {
        return;
    }
    const script = JSON.parse(fs.readFileSync(scriptPath, 'utf8'));
    const log = [];
    try {
        await sleep(script.startDelay || 1500);
        if (script.file) {
            const document = await vscode.workspace.openTextDocument(script.file);
            const editor = await vscode.window.showTextDocument(document, { preview: false });
            if (script.selection) {
                const [l1, c1, l2, c2] = script.selection;
                editor.selection = new vscode.Selection(l1, c1, l2, c2);
            }
        }
        for (const step of script.steps || []) {
            if (step.wait) {
                await sleep(step.wait);
                continue;
            }
            if (step.select) {
                // 選択範囲を変える(検索語の初期値は、選択した文字列から取られる)。
                const [l1, c1, l2, c2] = step.select;
                vscode.window.activeTextEditor.selection = new vscode.Selection(l1, c1, l2, c2);
                continue;
            }
            if (step.capture) {
                // 撮影の合図を出し、撮り終わるまで待つ(撮影は外のPythonが行う)。
                await sleep(step.settle || 500);
                const ready = script.done + '.' + step.capture + '.ready';
                const ack = script.done + '.' + step.capture + '.ack';
                fs.writeFileSync(ready, step.capture);
                for (let i = 0; i < 300 && !fs.existsSync(ack); ++i) {
                    await sleep(100);
                }
                continue;
            }
            try {
                const running = vscode.commands.executeCommand(step.command, ...(step.args === undefined ? [] : [step.args]));
                if (step.noWait) {
                    // 名前の変更・クイックフィックスなど、入力が終わるまで完了しないコマンドは待たない。
                    running.then(undefined, error => log.push({ command: step.command, ok: false, error: String(error) }));
                    await sleep(step.noWait === true ? 300 : step.noWait);
                } else {
                    await running;
                }
                log.push({ command: step.command, ok: true });
            } catch (error) {
                log.push({ command: step.command, ok: false, error: String(error) });
            }
        }
        await sleep(script.endDelay || 800);
    } catch (error) {
        log.push({ error: String(error) });
    }
    fs.writeFileSync(script.done, JSON.stringify({ log }, null, 1));
}

function deactivate() {}

module.exports = { activate, deactivate };
