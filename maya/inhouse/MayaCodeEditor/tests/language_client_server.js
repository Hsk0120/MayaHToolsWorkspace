// LSPの取消、逆順応答、破損フレームを再現する専用サーバー。ユーザーコードは読まない。
let buffer = Buffer.alloc(0);
function send(message) {
    const body = Buffer.from(JSON.stringify(message));
    process.stdout.write(`Content-Length: ${body.length}\r\n\r\n`);
    process.stdout.write(body);
}
process.stdin.on('data', data => {
    buffer = Buffer.concat([buffer, data]);
    for (;;) {
        const end = buffer.indexOf('\r\n\r\n');
        if (end < 0) return;
        const length = Number(buffer.subarray(0, end).toString().match(/Content-Length: (\d+)/)[1]);
        if (buffer.length < end + 4 + length) return;
        const item = JSON.parse(buffer.subarray(end + 4, end + 4 + length));
        buffer = buffer.subarray(end + 4 + length);
        if (item.method === 'initialize') send({jsonrpc: '2.0', id: item.id, result: {capabilities: {}}});
        if (item.method === 'delayed') setTimeout(() => send({jsonrpc: '2.0', id: item.id, result: item.params.value}), item.params.delay);
        if (item.method === 'malformed') process.stdout.write('Content-Length: -1\r\n\r\n');
        if (item.method === 'exit') process.exit(0);
    }
});
