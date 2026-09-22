"""Run a saved file in Maya and return Python output to the task terminal."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import runpy
import socket
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]


class Tee:
    def __init__(self, original, captured):
        self.original = original
        self.captured = captured

    def write(self, text):
        self.captured.write(text)
        self.original.write(text)
        return len(text)

    def flush(self):
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


def execute_in_maya(path, result_path):
    captured = io.StringIO()
    ok = True
    with contextlib.redirect_stdout(Tee(sys.stdout, captured)), contextlib.redirect_stderr(Tee(sys.stderr, captured)):
        try:
            runpy.run_path(path, run_name='__main__')
        except SystemExit as error:
            ok = error.code is None or error.code == 0
            if not ok:
                traceback.print_exc()
        except BaseException:
            ok = False
            traceback.print_exc()
    result = Path(result_path)
    temporary = result.with_suffix('.tmp')
    temporary.write_text(json.dumps({'ok': ok, 'output': captured.getvalue()}, ensure_ascii=False), encoding='utf-8')
    temporary.replace(result)


def validate_path(value):
    path = Path(value).resolve()
    path.relative_to(ROOT)
    if not path.is_file() or path.suffix.lower() != '.py':
        raise ValueError('Save and open a .py file inside this workspace first.')
    if path == Path(__file__).resolve():
        raise ValueError('Open the target tool, not send_to_maya.py.')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file')
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    try:
        path = validate_path(args.file)
    except (OSError, ValueError) as error:
        print('Invalid target: ' + str(error), file=sys.stderr)
        return 2
    try:
        directory = ROOT / '.maya-output'
        directory.mkdir(exist_ok=True)
        result_path = directory / (uuid.uuid4().hex + '.json')
        command = "__import__('runpy').run_path({})['execute_in_maya']({}, {}); None\n".format(
            ascii(str(Path(__file__).resolve())), ascii(str(path)), ascii(str(result_path)))
        with socket.create_connection(('127.0.0.1', 7002), timeout=5) as connection:
            connection.sendall(command.encode('ascii'))
            print('Running in Maya: ' + str(path), flush=True)
            connection.setblocking(False)
            response = bytearray()
            deadline = time.monotonic() + 300
            while not result_path.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError('No result after 300 seconds. Execution in Maya is not cancelled.')
                try:
                    chunk = connection.recv(4096)
                except BlockingIOError:
                    chunk = None
                if chunk:
                    response.extend(chunk)
                if chunk == b'' or b'\x00' in response:
                    if not result_path.exists():
                        raise RuntimeError('Maya returned without an output report: ' + response.decode('utf-8', errors='replace'))
                time.sleep(0.05)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        print(result['output'], end='', flush=True)
        print('\n[Maya] ' + ('Completed' if result['ok'] else 'FAILED'))
        result_path.unlink()
        return 0 if result['ok'] else 1
    except (OSError, ValueError, RuntimeError) as error:
        print('Maya execution error: ' + str(error), file=sys.stderr)
        print('Check Maya and port 7002. Do not automatically resend after a timeout.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
