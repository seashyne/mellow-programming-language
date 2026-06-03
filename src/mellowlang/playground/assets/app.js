const editor = document.getElementById('editor');
const highlightLayer = document.getElementById('highlight-layer');
const lineGutter = document.getElementById('line-gutter');
const statusPill = document.getElementById('status-pill');
const exampleSelect = document.getElementById('example-select');
const stdoutPanel = document.getElementById('stdout-panel');
const resultPanel = document.getElementById('result-panel');
const optimizationPanel = document.getElementById('optimization-panel');
const timelineList = document.getElementById('timeline-list');
const timelineSummary = document.getElementById('timeline-summary');
const debuggerMeta = document.getElementById('debugger-meta');
const debuggerWatch = document.getElementById('debugger-watch');
const debuggerDiff = document.getElementById('debugger-diff');
const debuggerStack = document.getElementById('debugger-stack');
const opcodeBreakpointsInput = document.getElementById('opcode-breakpoints-input');
const graphCanvas = document.getElementById('graph-canvas');
const graphMode = document.getElementById('graph-mode');
const shareBox = document.getElementById('share-box');
const recordingBox = document.getElementById('recording-box');
const breakpointsInput = document.getElementById('breakpoints-input');
const recordingIdInput = document.getElementById('recording-id-input');

const dumpTargets = {
  ast: document.getElementById('dump-ast'),
  ir: document.getElementById('dump-ir'),
  optimized_ir: document.getElementById('dump-optimized-ir'),
  cfg: document.getElementById('dump-cfg'),
  optimized_cfg: document.getElementById('dump-optimized-cfg'),
  ssa: document.getElementById('dump-ssa'),
  optimized_ssa: document.getElementById('dump-optimized-ssa'),
};

const state = {
  examples: [],
  lastResult: null,
  traceEvents: [],
  activeTraceIndex: -1,
  breakpoints: new Set(),
  debugSessionId: null,
  debugStop: null,
};

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function highlightSource(source) {
  const keywords = /(workflow|trigger|step|parallel|policy|retry|timeout|switch|case|default|run|use|input|output|state|emit|cron|webhook)/g;
  return source.split('
').map((raw) => {
    let line = escapeHtml(raw);
    line = line.replace(/(#.*)$/g, '<span class="tok-comment">$1</span>');
    line = line.replace(/(".*?"|'.*?')/g, '<span class="tok-string">$1</span>');
    line = line.replace(/(\d+(?:\.\d+)?)/g, '<span class="tok-number">$1</span>');
    line = line.replace(keywords, '<span class="tok-keyword">$1</span>');
    return line || '&nbsp;';
  }).join('<br>');
}

function normalizeBreakpoints(text) {
  const out = new Set();
  String(text || '').split(',').map((part) => part.trim()).filter(Boolean).forEach((part) => {
    if (part.includes('-')) {
      const [a, b] = part.split('-', 2).map((n) => Number(n.trim()));
      if (Number.isFinite(a) && Number.isFinite(b)) {
        const lo = Math.min(a, b);
        const hi = Math.max(a, b);
        for (let i = lo; i <= hi; i += 1) out.add(i);
      }
      return;
    }
    const num = Number(part);
    if (Number.isFinite(num)) out.add(num);
  });
  return out;
}

function breakpointsToText() {
  return [...state.breakpoints].sort((a, b) => a - b).join(',');
}

function renderGutter(lineCount) {
  lineGutter.innerHTML = Array.from({ length: lineCount }, (_, idx) => {
    const line = idx + 1;
    const cls = state.breakpoints.has(line) ? 'gline breakpoint' : 'gline';
    return `<span class="${cls}" data-line="${line}">${line}</span>`;
  }).join('');
}

function syncEditorPresentation() {
  const value = editor.value || '';
  highlightLayer.innerHTML = highlightSource(value);
  const lines = Math.max(value.split('
').length, 1);
  renderGutter(lines);
}

function syncScroll() {
  highlightLayer.scrollTop = editor.scrollTop;
  highlightLayer.scrollLeft = editor.scrollLeft;
  lineGutter.scrollTop = editor.scrollTop;
}

function setStatus(text, tone = 'idle') {
  statusPill.textContent = text;
  statusPill.style.borderColor = tone === 'error' ? 'rgba(248, 113, 113, .4)' : tone === 'ok' ? 'rgba(52, 211, 153, .4)' : tone === 'warn' ? 'rgba(251, 191, 36, .4)' : 'rgba(124, 156, 255, .3)';
  statusPill.style.background = tone === 'error' ? 'rgba(248, 113, 113, .12)' : tone === 'ok' ? 'rgba(52, 211, 153, .12)' : tone === 'warn' ? 'rgba(251, 191, 36, .12)' : 'rgba(124, 156, 255, .12)';
}

function setStats(payload = {}) {
  document.getElementById('stat-pipeline').textContent = payload.pipeline || '-';
  document.getElementById('stat-compile').textContent = payload.compile_ms != null ? `${payload.compile_ms} ms` : '-';
  document.getElementById('stat-run').textContent = payload.run_ms != null ? `${payload.run_ms} ms` : '-';
  document.getElementById('stat-bytecode').textContent = payload.bytecode_count != null ? String(payload.bytecode_count) : '-';
}

function setDumps(dumps = {}) {
  dumpTargets.ast.textContent = dumps.ast || '';
  dumpTargets.ir.textContent = dumps.ir || '';
  dumpTargets.optimized_ir.textContent = dumps.optimized_ir || '';
  dumpTargets.cfg.textContent = dumps.cfg || '';
  dumpTargets.optimized_cfg.textContent = dumps.optimized_cfg || '';
  dumpTargets.ssa.textContent = dumps.ssa || '';
  dumpTargets.optimized_ssa.textContent = dumps.optimized_ssa || '';
}

async function fetchExamples() {
  const res = await fetch('/api/examples');
  const data = await res.json();
  state.examples = data.examples || [];
  exampleSelect.innerHTML = state.examples.map((item, idx) => `<option value="${idx}">${item.name}</option>`).join('');
  if (!editor.value && state.examples[0]) {
    editor.value = state.examples[0].source;
    syncEditorPresentation();
  }
}

function selectedPayload() {
  return {
    source: editor.value,
    optimize: document.getElementById('optimize').checked,
    allow_net: document.getElementById('allow-net').checked,
    trace: document.getElementById('trace').checked,
    watch: document.getElementById('watch-input').value,
    engine: document.getElementById('engine-select').value,
    dump_format: 'text',
    break_lines: breakpointsToText(),
    break_opcodes: opcodeBreakpointsInput.value,
    record_execution: true,
  };
}

function renderTimeline(timeline = [], traceEvents = []) {
  state.traceEvents = traceEvents;
  state.activeTraceIndex = traceEvents.length ? 0 : -1;
  timelineSummary.textContent = traceEvents.length ? `${traceEvents.length} traced steps` : 'No trace yet';
  timelineList.innerHTML = timeline.map((item) => {
    if (item.kind === 'step') {
      return `<div class="timeline-item" data-trace-index="${item.index}">
        <div class="top"><strong>${escapeHtml(item.label)}</strong><span>${item.ms} ms</span></div>
        <div class="meta">step • line ${item.line} • <em>${item.state_diff_count || 0} diff</em></div>
      </div>`;
    }
    return `<div class="timeline-item">
      <div class="top"><strong>${escapeHtml(item.label)}</strong><span>${item.ms} ms</span></div>
      <div class="meta">${item.kind}</div>
    </div>`;
  }).join('');
  timelineList.querySelectorAll('[data-trace-index]').forEach((node) => {
    node.addEventListener('click', () => setActiveTrace(Number(node.dataset.traceIndex)));
  });
  updateDebugger();
}

function renderGraph(graph = {}) {
  graphMode.textContent = graph.mode ? `Mode: ${graph.mode}` : '-';
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  if (!nodes.length) {
    graphCanvas.innerHTML = '<div class="subtle">No graph available</div>';
    return;
  }
  const nodesHtml = nodes.map((node) => `
    <div class="graph-node ${escapeHtml(node.kind || 'node')}" data-graph-line="${node.line || 0}">
      <div class="kind">${escapeHtml(node.kind || 'node')}</div>
      <div class="label">${escapeHtml(node.label || node.id || 'node')}</div>
      <div class="line">line ${node.line || '-'}</div>
    </div>
  `).join('');
  const edgeText = edges.map((edge) => `${edge.from} → ${edge.to}`).join('
') || 'No edges';
  graphCanvas.innerHTML = `${nodesHtml}<div class="graph-edges">${escapeHtml(edgeText)}</div>`;
}

function updateDebugger() {
  const event = state.traceEvents[state.activeTraceIndex] || null;
  timelineList.querySelectorAll('[data-trace-index]').forEach((node) => {
    node.classList.toggle('active', Number(node.dataset.traceIndex) === state.activeTraceIndex);
  });
  document.querySelectorAll('.graph-node').forEach((node) => {
    node.classList.toggle('active', Number(node.dataset.graphLine) === (event ? event.line : -1));
  });
  if (!event) {
    if (state.debugStop) {
      debuggerMeta.textContent = `Paused at pc ${state.debugStop.pc}\n${state.debugStop.opcode}\n${state.debugStop.source || ''}`;
      const watchEntries = Object.entries(state.debugStop.watch_values || {});
      debuggerWatch.textContent = watchEntries.length ? watchEntries.map(([key, value]) => `${key} = ${value}`).join('\n') : 'No watch values';
      debuggerDiff.textContent = JSON.stringify(state.debugStop.locals || {}, null, 2);
      debuggerStack.textContent = JSON.stringify({ stack: state.debugStop.stack || [], frames: state.debugStop.frames || [] }, null, 2);
      if (state.debugStop.line) focusLine(state.debugStop.line);
      return;
    }
    debuggerMeta.textContent = 'Run with trace to inspect steps.';
    debuggerWatch.textContent = 'No watch values';
    debuggerDiff.textContent = 'No state diff';
    debuggerStack.textContent = 'No stack snapshot';
    return;
  }
  debuggerMeta.textContent = `Step ${event.index + 1}
${event.file}:${event.line}:${event.col}
${event.source}`;
  const watchEntries = Object.entries(event.watch || {});
  debuggerWatch.textContent = watchEntries.length
    ? watchEntries.map(([key, value]) => `${key} = ${value}`).join('
')
    : (event.watch_raw || 'No watch values');
  debuggerDiff.textContent = (event.state_diff || []).length
    ? event.state_diff.map((item) => `${item.name}: ${item.before ?? '∅'} → ${item.after ?? '∅'}`).join('
')
    : 'No state diff';
  focusLine(event.line);
}

function focusLine(lineNumber) {
  const lines = editor.value.split('
');
  let position = 0;
  for (let i = 0; i < Math.max(0, lineNumber - 1); i += 1) position += lines[i].length + 1;
  editor.focus();
  editor.setSelectionRange(position, position + (lines[Math.max(0, lineNumber - 1)] || '').length);
}

function setActiveTrace(index) {
  state.activeTraceIndex = index;
  updateDebugger();
}


async function startDebugger() {
  setStatus('Starting debugger…');
  const res = await fetch('/api/debug/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(selectedPayload()),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Debugger start failed');
  state.debugSessionId = data.session_id;
  state.debugStop = data.stop || null;
  stdoutPanel.textContent = '';
  resultPanel.textContent = data.result || '';
  optimizationPanel.textContent = `Debugger session: ${data.session_id}`;
  setStats(data);
  renderTimeline([], []);
  updateDebugger();
  setStatus(data.finished ? 'Debug finished' : 'Debugger paused', data.finished ? 'ok' : 'warn');
}

async function sendDebugCommand(command) {
  if (!state.debugSessionId) {
    setStatus('Start debugger first', 'warn');
    return;
  }
  const res = await fetch('/api/debug/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.debugSessionId, command }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Debugger command failed');
  state.debugStop = data.stop || null;
  resultPanel.textContent = data.result || '';
  optimizationPanel.textContent = `Debugger session: ${data.session_id}\nPaused: ${data.paused}\nFinished: ${data.finished}`;
  setStats(data);
  updateDebugger();
  setStatus(data.finished ? 'Debug finished' : `Paused (${command})`, data.finished ? 'ok' : 'warn');
}

async function invoke(path) {
  setStatus(path === '/api/run' ? 'Running…' : 'Compiling…');
  stdoutPanel.textContent = '';
  resultPanel.textContent = '';
  optimizationPanel.textContent = '';
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedPayload()),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Request failed');
    state.lastResult = data;
  state.debugSessionId = null;
  state.debugStop = null;
    state.debugSessionId = null;
    state.debugStop = null;
    setStats(data);
    stdoutPanel.textContent = data.stdout || '';
    resultPanel.textContent = data.result || '';
    optimizationPanel.textContent = data.optimization ? JSON.stringify(data.optimization, null, 2) : 'No optimization metadata';
    setDumps(data.dumps || {});
    renderTimeline(data.timeline || [], data.trace_events || []);
    renderGraph(data.graph || {});
    const dbg = data.debugger || {};
    if (dbg.recording_id) {
      recordingIdInput.value = dbg.recording_id;
      recordingBox.textContent = `Recording: ${dbg.recording_id}${dbg.replay_mode ? ' (replay)' : ''}`;
    }
    if (dbg.stopped) {
      const stop = dbg.stop || {};
      setStatus(`Paused at L${stop.line || '?'} breakpoint`, 'warn');
    } else {
      setStatus(path === '/api/run' ? 'Run complete' : 'Compile complete', 'ok');
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    stdoutPanel.textContent = '';
    resultPanel.textContent = msg;
    optimizationPanel.textContent = '';
    setDumps({});
    renderTimeline([], []);
    renderGraph({});
    setStats({});
    setStatus('Error', 'error');
  }
}

async function replayRecording() {
  const recordingId = recordingIdInput.value.trim();
  if (!recordingId) {
    recordingBox.textContent = 'Enter or create a recording first.';
    return;
  }
  setStatus('Replaying…');
  const res = await fetch('/api/replay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recording_id: recordingId }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Replay failed');
  state.lastResult = data;
  setStats(data);
  stdoutPanel.textContent = data.stdout || '';
  resultPanel.textContent = data.result || '';
  optimizationPanel.textContent = data.optimization ? JSON.stringify(data.optimization, null, 2) : 'No optimization metadata';
  setDumps(data.dumps || {});
  renderTimeline(data.timeline || [], data.trace_events || []);
  renderGraph(data.graph || {});
  const dbg = data.debugger || {};
  recordingBox.textContent = `Replayed recording: ${dbg.replayed_from_recording || recordingId}`;
  setStatus('Replay complete', 'ok');
}

async function shareSession() {
  if (!state.lastResult) {
    shareBox.textContent = 'Run or compile first to create a shareable session.';
    return;
  }
  const res = await fetch('/api/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: editor.value, result: state.lastResult }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Share failed');
  shareBox.textContent = data.share_url;
  history.replaceState({}, '', `/s/${data.session_id}`);
}

async function loadSharedSession() {
  const match = window.location.pathname.match(/^\/s\/([^/]+)$/);
  if (!match) return false;
  const sessionId = match[1];
  const res = await fetch(`/api/session/${sessionId}`);
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Failed to load session');
  const session = data.session || {};
  editor.value = session.source || '';
  syncEditorPresentation();
  if (session.result) {
    state.lastResult = session.result;
    state.debugSessionId = null;
    state.debugStop = null;
    setStats(session.result);
    stdoutPanel.textContent = session.result.stdout || '';
    resultPanel.textContent = session.result.result || '';
    optimizationPanel.textContent = session.result.optimization ? JSON.stringify(session.result.optimization, null, 2) : 'No optimization metadata';
    setDumps(session.result.dumps || {});
    renderTimeline(session.result.timeline || [], session.result.trace_events || []);
    renderGraph(session.result.graph || {});
    shareBox.textContent = window.location.href;
    const dbg = session.result.debugger || {};
    if (dbg.recording_id) recordingIdInput.value = dbg.recording_id;
    setStatus('Shared session loaded', 'ok');
  }
  return true;
}

function setupTabs() {
  document.querySelectorAll('.tabbar').forEach((tabbar) => {
    const target = document.getElementById(tabbar.dataset.target);
    tabbar.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        tabbar.querySelectorAll('.tab').forEach((node) => node.classList.remove('active'));
        target.querySelectorAll('.tab-panel').forEach((node) => node.classList.remove('active'));
        tab.classList.add('active');
        const panel = target.querySelector(`[data-panel="${tab.dataset.tab}"]`);
        if (panel) panel.classList.add('active');
      });
    });
  });
}

editor.addEventListener('input', syncEditorPresentation);
editor.addEventListener('scroll', syncScroll);
editor.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    invoke('/api/run');
  }
});
lineGutter.addEventListener('click', (event) => {
  const target = event.target.closest('[data-line]');
  if (!target) return;
  const line = Number(target.dataset.line);
  if (state.breakpoints.has(line)) state.breakpoints.delete(line);
  else state.breakpoints.add(line);
  breakpointsInput.value = breakpointsToText();
  syncEditorPresentation();
});
breakpointsInput.addEventListener('change', () => {
  state.breakpoints = normalizeBreakpoints(breakpointsInput.value);
  breakpointsInput.value = breakpointsToText();
  syncEditorPresentation();
});
document.getElementById('run-btn').addEventListener('click', () => invoke('/api/run'));
document.getElementById('debug-start-btn').addEventListener('click', startDebugger);
document.getElementById('compile-btn').addEventListener('click', () => invoke('/api/compile'));
document.getElementById('replay-btn').addEventListener('click', replayRecording);
document.getElementById('load-example').addEventListener('click', () => {
  const item = state.examples[Number(exampleSelect.value)];
  if (!item) return;
  editor.value = item.source;
  syncEditorPresentation();
  setStatus(`Loaded ${item.name}`);
});
document.getElementById('copy-btn').addEventListener('click', async () => {
  await navigator.clipboard.writeText(editor.value);
  setStatus('Copied', 'ok');
});
document.getElementById('share-btn').addEventListener('click', shareSession);
document.getElementById('debug-prev').addEventListener('click', () => {
  if (!state.traceEvents.length) return;
  setActiveTrace(Math.max(0, state.activeTraceIndex - 1));
});
document.getElementById('debug-next').addEventListener('click', () => {
  if (!state.traceEvents.length) return;
  setActiveTrace(Math.min(state.traceEvents.length - 1, state.activeTraceIndex + 1));
});
document.getElementById('debug-continue').addEventListener('click', () => sendDebugCommand('continue'));
document.getElementById('debug-into').addEventListener('click', () => sendDebugCommand('step_into'));
document.getElementById('debug-over').addEventListener('click', () => sendDebugCommand('step_over'));
document.getElementById('debug-out').addEventListener('click', () => sendDebugCommand('step_out'));

setupTabs();
fetchExamples().then(loadSharedSession).catch((err) => {
  setStatus(err instanceof Error ? err.message : String(err), 'error');
});
syncEditorPresentation();
