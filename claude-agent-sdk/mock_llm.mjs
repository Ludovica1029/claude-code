// Mock Anthropic Messages API (streaming SSE). Logs request shape; scripts one shell tool call, then a final answer.
import http from 'node:http'
import fs from 'node:fs'

const port = Number(process.argv[2] || 8787)
const logFile = process.argv[3] || 'requests.jsonl'
let n = 0

function sse(res, events) {
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
  for (const [type, data] of events) res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`)
  res.end()
}

function message(content, stop_reason) {
  const ev = [['message_start', { message: { id: 'msg_' + n, type: 'message', role: 'assistant', model: 'mock', content: [], stop_reason: null, usage: { input_tokens: 10, output_tokens: 1 } } }]]
  content.forEach((b, i) => {
    if (b.type === 'text') {
      ev.push(['content_block_start', { index: i, content_block: { type: 'text', text: '' } }])
      ev.push(['content_block_delta', { index: i, delta: { type: 'text_delta', text: b.text } }])
    } else {
      ev.push(['content_block_start', { index: i, content_block: { type: 'tool_use', id: b.id, name: b.name, input: {} } }])
      ev.push(['content_block_delta', { index: i, delta: { type: 'input_json_delta', partial_json: JSON.stringify(b.input) } }])
    }
    ev.push(['content_block_stop', { index: i }])
  })
  ev.push(['message_delta', { delta: { stop_reason, stop_sequence: null }, usage: { output_tokens: 5 } }])
  ev.push(['message_stop', {}])
  return ev
}

http.createServer((req, res) => {
  let body = ''
  req.on('data', (c) => (body += c))
  req.on('end', () => {
    if (!req.url.includes('/messages')) {
      if (req.url.includes('/models')) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify({ data: [] })) }
      res.writeHead(404); return res.end('{}')
    }
    n++
    const j = JSON.parse(body || '{}')
    if (req.url.includes('count_tokens')) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end('{"input_tokens":100}') }
    const sys = typeof j.system === 'string' ? j.system : (j.system || []).map((b) => b.text || '').join('\n')
    const tools = (j.tools || []).map((t) => t.name)
    const msgs = j.messages || []
    const last = msgs.at(-1)
    const lastHasToolResult = Array.isArray(last?.content) && last.content.some((b) => b.type === 'tool_result')
    fs.appendFileSync(logFile, JSON.stringify({
      n, url: req.url, model: j.model, stream: j.stream, max_tokens: j.max_tokens, thinking: j.thinking,
      bytes: body.length, system_chars: sys.length, tool_count: tools.length, tools, msg_count: msgs.length,
      lastHasToolResult, tool_result: lastHasToolResult ? JSON.stringify(last.content.find((b) => b.type === 'tool_result').content).slice(0, 300) : undefined,
      system_head: sys.slice(0, 400),
    }) + '\n')
    if (n === 1 || process.env.DUMP_ALL) fs.writeFileSync(logFile + `.req${n}.json`, body)

    const shell = (j.tools || []).find((t) => /^(bash|shell|exec|run_command|terminal)/i.test(t.name))
    let content, stop
    if (shell && !lastHasToolResult && !msgs.some((m) => Array.isArray(m.content) && m.content.some((b) => b.type === 'tool_use'))) {
      const props = Object.keys(shell.input_schema?.properties || {})
      const key = props.find((p) => /command|cmd|script/i.test(p)) || 'command'
      content = [{ type: 'text', text: 'Running it.' }, { type: 'tool_use', id: 'toolu_' + n, name: shell.name, input: { ...Object.fromEntries((shell.input_schema?.required || []).map((r) => [r, 'mock ' + r])), [key]: 'echo hello > out.txt && uname -s && cat out.txt' } }]
      stop = 'tool_use'
    } else {
      content = [{ type: 'text', text: lastHasToolResult ? 'DONE: shell tool executed.' : 'ok' }]
      stop = 'end_turn'
    }
    if (j.stream) return sse(res, message(content, stop))
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ id: 'msg_' + n, type: 'message', role: 'assistant', model: 'mock', content, stop_reason: stop, usage: { input_tokens: 10, output_tokens: 5 } }))
  })
}).listen(port, '127.0.0.1', () => console.log('mock on', port))
