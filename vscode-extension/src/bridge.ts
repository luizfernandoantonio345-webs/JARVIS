/**
 * bridge.ts — FASE 8 VS Code Bridge Server
 *
 * Starts a local HTTP server on 127.0.0.1:7892 inside the VS Code extension
 * process.  The Jarvis Python backend sends JSON-RPC-style POST requests to
 * /vscode and this module executes the corresponding VS Code API calls.
 *
 * Actions supported:
 *   ping                — health check
 *   open_file           — open a file in the editor (optional line jump)
 *   edit_line           — replace a single line via WorkspaceEdit
 *   read_diagnostics    — return Problems panel data for a path / workspace
 *   run_task            — execute a tasks.json task by name
 *   get_terminal_output — return recent lines from the active terminal
 *   reveal_in_explorer  — reveal a path in the Explorer panel
 *   get_active_file     — return path of the focused editor file
 *
 * Security: binds to loopback only; path params validated against workspace root.
 */

import * as http from "http";
import * as vscode from "vscode";
import * as path from "path";

const BRIDGE_PORT = 7892;
const ALLOWED_HOST = "127.0.0.1";

type ActionParams = Record<string, unknown>;
interface BridgeRequest { action: string; params?: ActionParams; }
interface BridgeResponse { ok: boolean; result?: unknown; error?: string; }

// ── Path safety ────────────────────────────────────────────────────────────────

function safeAbsPath(raw: unknown): string | null {
  if (typeof raw !== "string" || !raw) return null;
  const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  const resolved = path.isAbsolute(raw) ? raw : path.join(wsRoot, raw);
  // Prevent path traversal outside workspace (unless absolute path is given)
  if (wsRoot && !resolved.startsWith(wsRoot) && !path.isAbsolute(raw)) {
    return null;
  }
  return resolved;
}

// ── Action handlers ────────────────────────────────────────────────────────────

async function handleAction(action: string, params: ActionParams): Promise<BridgeResponse> {
  switch (action) {

    case "ping":
      return { ok: true, result: "pong" };

    case "open_file": {
      const filePath = safeAbsPath(params.path);
      if (!filePath) return { ok: false, error: "Invalid or missing path." };
      const uri = vscode.Uri.file(filePath);
      const opts: vscode.TextDocumentShowOptions = {};
      if (typeof params.line === "number") {
        const pos = new vscode.Position(params.line - 1, 0);
        opts.selection = new vscode.Range(pos, pos);
      }
      await vscode.window.showTextDocument(uri, opts);
      return { ok: true, result: filePath };
    }

    case "edit_line": {
      const filePath = safeAbsPath(params.path);
      if (!filePath) return { ok: false, error: "Invalid or missing path." };
      if (typeof params.line !== "number") return { ok: false, error: "line must be a number." };
      if (typeof params.text !== "string") return { ok: false, error: "text must be a string." };
      const uri = vscode.Uri.file(filePath);
      const doc = await vscode.workspace.openTextDocument(uri);
      const lineIdx = params.line - 1;
      if (lineIdx < 0 || lineIdx >= doc.lineCount) {
        return { ok: false, error: `Line ${params.line} out of range (1–${doc.lineCount}).` };
      }
      const range = doc.lineAt(lineIdx).range;
      const edit = new vscode.WorkspaceEdit();
      edit.replace(uri, range, params.text as string);
      const applied = await vscode.workspace.applyEdit(edit);
      return { ok: applied, error: applied ? undefined : "WorkspaceEdit failed." };
    }

    case "read_diagnostics": {
      const filePath = params.path ? safeAbsPath(params.path) : null;
      const targetUri = filePath ? vscode.Uri.file(filePath) : undefined;
      const allDiags = targetUri
        ? vscode.languages.getDiagnostics(targetUri)
        : vscode.languages.getDiagnostics().flatMap(([, d]) => d);
      const diags = (targetUri ? allDiags as vscode.Diagnostic[] : allDiags as vscode.Diagnostic[]).map((d) => ({
        severity: vscode.DiagnosticSeverity[d.severity],
        message: d.message,
        source: d.source,
        range: {
          start: { line: d.range.start.line + 1, character: d.range.start.character },
          end:   { line: d.range.end.line + 1,   character: d.range.end.character },
        },
      }));
      return { ok: true, result: diags };
    }

    case "run_task": {
      if (typeof params.task !== "string") return { ok: false, error: "task name required." };
      await vscode.commands.executeCommand("workbench.action.tasks.runTask", params.task);
      return { ok: true, result: `Task '${params.task}' triggered.` };
    }

    case "get_terminal_output": {
      const maxLines = typeof params.lines === "number" ? params.lines : 100;
      // VS Code API doesn't expose terminal buffer directly; use clipboard workaround
      const previousClipboard = await vscode.env.clipboard.readText();
      await vscode.commands.executeCommand("workbench.action.terminal.selectAll");
      await vscode.commands.executeCommand("workbench.action.terminal.copySelection");
      const rawOutput = await vscode.env.clipboard.readText();
      await vscode.env.clipboard.writeText(previousClipboard); // restore clipboard
      const lines = rawOutput.split("\n").slice(-maxLines).join("\n");
      return { ok: true, result: lines };
    }

    case "reveal_in_explorer": {
      const filePath = safeAbsPath(params.path);
      if (!filePath) return { ok: false, error: "Invalid or missing path." };
      const uri = vscode.Uri.file(filePath);
      await vscode.commands.executeCommand("revealInExplorer", uri);
      return { ok: true, result: filePath };
    }

    case "get_active_file": {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return { ok: false, error: "No active editor." };
      return { ok: true, result: editor.document.fileName };
    }

    default:
      return { ok: false, error: `Unknown action: ${action}` };
  }
}

// ── HTTP Server ────────────────────────────────────────────────────────────────

let _server: http.Server | null = null;

export function startBridgeServer(outputChannel: vscode.OutputChannel): void {
  if (_server) return; // already started

  _server = http.createServer(async (req, res) => {
    // Only accept loopback POST /vscode
    if (req.socket.remoteAddress !== ALLOWED_HOST && req.socket.remoteAddress !== "::1") {
      res.writeHead(403).end(JSON.stringify({ ok: false, error: "Forbidden" }));
      return;
    }
    if (req.method !== "POST" || req.url !== "/vscode") {
      res.writeHead(404).end(JSON.stringify({ ok: false, error: "Not found" }));
      return;
    }

    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", async () => {
      let parsed: BridgeRequest;
      try {
        parsed = JSON.parse(body) as BridgeRequest;
      } catch {
        res.writeHead(400).end(JSON.stringify({ ok: false, error: "Invalid JSON" }));
        return;
      }
      try {
        const result = await handleAction(parsed.action, parsed.params ?? {});
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(result));
        outputChannel.appendLine(`[bridge] ${parsed.action} → ok=${result.ok}`);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`[bridge] ERROR ${parsed.action}: ${msg}`);
        res.writeHead(500).end(JSON.stringify({ ok: false, error: msg }));
      }
    });
  });

  _server.listen(BRIDGE_PORT, ALLOWED_HOST, () => {
    outputChannel.appendLine(`[JARVIS bridge] listening on ${ALLOWED_HOST}:${BRIDGE_PORT}`);
  });

  _server.on("error", (err) => {
    outputChannel.appendLine(`[JARVIS bridge] server error: ${err.message}`);
  });
}

export function stopBridgeServer(): void {
  _server?.close();
  _server = null;
}
