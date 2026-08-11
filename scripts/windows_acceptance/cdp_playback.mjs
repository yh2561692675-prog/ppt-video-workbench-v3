import process from 'node:process';

const port = Number(process.argv[2] ?? '9223');
const urlNeedle = process.argv[3] ?? '';
const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((response) =>
  response.json(),
);
const target = targets.find(
  (candidate) =>
    candidate.type === 'page' && (!urlNeedle || String(candidate.url).includes(urlNeedle)),
);
if (!target?.webSocketDebuggerUrl) {
  throw new Error('playback_target_not_found');
}

const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
const exceptions = [];
let nextId = 1;

await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data));
  if (message.method === 'Runtime.exceptionThrown') {
    exceptions.push(message.params?.exceptionDetails?.text ?? 'unknown_exception');
  }
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

function command(method, params = {}) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression, awaitPromise = false) {
  const response = await command('Runtime.evaluate', {
    expression,
    awaitPromise,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text ?? 'evaluation_failed');
  }
  return response.result?.value;
}

await command('Runtime.enable');
const initial = await evaluate(`(() => {
  const video = document.querySelector('video');
  if (!video) throw new Error('video_element_missing');
  video.pause();
  video.currentTime = 0;
  return {currentTime: video.currentTime, duration: video.duration, readyState: video.readyState};
})()`);
await evaluate(
  `(async () => {
  const video = document.querySelector('video');
  await video.play();
  return true;
})()`,
  true,
);

const startedAt = Date.now();
const timeoutMs = Math.max(30_000, Math.ceil(Number(initial.duration) * 1_000) + 15_000);
const samples = [];
let lastSecond = -1;
let finalState;
while (Date.now() - startedAt < timeoutMs) {
  finalState = await evaluate(`(() => {
    const video = document.querySelector('video');
    return {
      currentTime: video.currentTime,
      duration: video.duration,
      ended: video.ended,
      paused: video.paused,
      readyState: video.readyState,
      error: video.error ? {code: video.error.code, message: video.error.message} : null,
    };
  })()`);
  const second = Math.floor(finalState.currentTime);
  if (second !== lastSecond || finalState.ended) {
    samples.push(finalState);
    lastSecond = second;
  }
  if (finalState.error) throw new Error(`playback_media_error:${finalState.error.code}`);
  if (finalState.ended) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}

socket.close();
const passed =
  initial.currentTime === 0 &&
  finalState?.ended === true &&
  finalState.currentTime >= finalState.duration - 0.1 &&
  exceptions.length === 0;
console.log(
  JSON.stringify(
    {
      passed,
      target: { id: target.id, title: target.title, url: target.url },
      initial,
      final: finalState,
      elapsed_ms: Date.now() - startedAt,
      sample_count: samples.length,
      samples,
      exceptions,
    },
    null,
    2,
  ),
);
if (!passed) process.exitCode = 1;
