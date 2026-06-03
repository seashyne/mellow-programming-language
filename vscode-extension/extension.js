const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const lc = require('vscode-languageclient/node');

let client;
let output;

function existing(p) {
  try { return !!p && fs.existsSync(p); } catch { return false; }
}

function workspaceCandidates() {
  const folders = vscode.workspace.workspaceFolders || [];
  const names = process.platform === 'win32' ? ['mellow.exe', 'mellow.cmd', 'mellow.bat'] : ['mellow'];
  const rels = [
    ['.venv', 'Scripts'],
    ['venv', 'Scripts'],
    ['.venv', 'bin'],
    ['venv', 'bin'],
  ];
  const out = [];
  for (const folder of folders) {
    for (const rel of rels) {
      for (const name of names) {
        out.push(path.join(folder.uri.fsPath, ...rel, name));
      }
    }
  }
  return out;
}

function resolveMellowLangCommand() {
  const cfg = vscode.workspace.getConfiguration('mellowlang');
  const userPath = String(cfg.get('executablePath') || '').trim();
  if (userPath) return { command: userPath, source: 'settings' };

  for (const p of workspaceCandidates()) {
    if (existing(p)) return { command: p, source: 'workspace' };
  }

  if (process.platform === 'win32') {
    const candidates = [];
    if (process.env.ProgramFiles) candidates.push(path.join(process.env.ProgramFiles, 'MellowLang', 'mellow.exe'));
    if (process.env.LOCALAPPDATA) candidates.push(path.join(process.env.LOCALAPPDATA, 'Programs', 'MellowLang', 'mellow.exe'));
    for (const p of candidates) {
      if (existing(p)) return { command: p, source: 'common-install' };
    }
  }

  return { command: 'mellow', source: 'PATH' };
}

function currentServerOptions() {
  const resolved = resolveMellowLangCommand();
  const cfg = vscode.workspace.getConfiguration('mellowlang');
  const extraArgs = Array.isArray(cfg.get('extraArgs')) ? cfg.get('extraArgs') : [];
  const args = ['lsp', ...extraArgs];
  output.appendLine(`[MellowLang] Using ${resolved.command} (${resolved.source}) ${args.join(' ')}`);
  return {
    command: resolved.command,
    args,
    options: {}
  };
}

function traceLevel() {
  const cfg = vscode.workspace.getConfiguration('mellowlang');
  const value = String(cfg.get('trace.server') || 'off');
  if (value === 'messages') return lc.Trace.Messages;
  if (value === 'verbose') return lc.Trace.Verbose;
  return lc.Trace.Off;
}

function startClient(context) {
  const serverOptions = currentServerOptions();
  const clientOptions = {
    documentSelector: [{ scheme: 'file', language: 'mellow' }],
    synchronize: { configurationSection: 'mellowlang' },
    outputChannel: output,
    markdown: { isTrusted: true }
  };

  client = new lc.LanguageClient('mellowlang', 'MellowLang Language Server', serverOptions, clientOptions);
  client.setTrace(traceLevel());
  context.subscriptions.push(client.start());
  output.appendLine('[MellowLang] Language server started');
}

async function restartClient(context) {
  if (client) {
    try { await client.stop(); } catch {}
    client = undefined;
  }
  startClient(context);
}

function activate(context) {
  output = vscode.window.createOutputChannel('MellowLang');
  output.appendLine('MellowLang extension activated');
  startClient(context);

  context.subscriptions.push(vscode.commands.registerCommand('mellowlang.restartLanguageServer', async () => {
    await restartClient(context);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('mellowlang.runDoctor', async () => {
    const resolved = resolveMellowLangCommand();
    const terminal = vscode.window.createTerminal('MellowLang Doctor');
    terminal.show(true);
    terminal.sendText(`"${resolved.command}" doctor`);
  }));

  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(async (event) => {
    if (event.affectsConfiguration('mellowlang')) {
      output.appendLine('[MellowLang] Configuration changed, restarting language server');
      await restartClient(context);
    }
  }));

  context.subscriptions.push(output);
}

function deactivate() {
  if (client) return client.stop();
  return undefined;
}

module.exports = { activate, deactivate };
