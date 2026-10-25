"""テスト専用プロセスを、Maya側のイベントループに依存せず監視する。"""
import json
import os
import subprocess
import time


def read_result(path):
    """書込み途中のJSONは次の監視周期で読み直す。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stop_owned_process(process):
    """呼出元が生成したPopenのプロセスだけを終了する。名前による一括終了はしない。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except subprocess.TimeoutExpired:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def monitor_process(process, directory, timeout, shutdown_timeout, poll_seconds=0.25):
    """起動・テスト・終了ごとに期限を設け、進行段階と停止結果を返す。"""
    phase = "startup"
    phase_start = time.monotonic()
    history = [{"phase": phase, "elapsed_seconds": 0}]
    started = phase_start
    while process.poll() is None:
        result = read_result(directory / "result.json")
        if result.get("status") in ("passed", "failed", "error"):
            current = "shutdown"
        elif (directory / "started.json").exists():
            current = "tests"
        else:
            current = "startup"
        now = time.monotonic()
        if current != phase:
            phase = current
            phase_start = now
            history.append({"phase": phase, "elapsed_seconds": round(now - started, 2)})
        limit = shutdown_timeout if phase == "shutdown" else timeout
        if now - phase_start >= limit:
            stop_owned_process(process)
            return {"timed_out": True, "timeout_phase": phase, "timeout_seconds": limit,
                    "suite_status": result.get("status", "not_started"),
                    "owned_process_stopped": process.poll() is not None, "phases": history}
        time.sleep(poll_seconds)
    return {"timed_out": False, "exit_code": process.returncode, "phases": history}
