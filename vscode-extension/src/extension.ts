/**
 * JARVIS VS Code Extension
 *
 * Commands:
 *   jarvis.improveCode  — sends current file to JARVIS, shows diff, asks for confirmation
 *   jarvis.reviewCode   — review/analyze without modifying
 *   jarvis.securityScan — run security agent on current file
 *   jarvis.explainCode  — explain selected code or full file
 */

import * as vscode from "vscode";
import { JarvisClient } from "./client";
import { showDiffAndConfirm } from "./diff";
import { startBridgeServer, stopBridgeServer } from "./bridge";

let _client: JarvisClient | null = null;

function getClient(): JarvisClient {
  const cfg = vscode.workspace.getConfiguration("jarvis");
  const url = cfg.get<string>("backendUrl", "http://localhost:8000");
  const sid = cfg.get<string>("sessionId", "vscode-session");
  if (!_client) {
    _client = new JarvisClient(url, sid);
  }
  return _client;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getActiveEditorContent(): {
  editor: vscode.TextEditor;
  content: string;
  language: string;
  fileName: string;
} | null {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("JARVIS: No active editor.");
    return null;
  }
  const doc = editor.document;
  const selection = editor.selection;
  const content = selection.isEmpty
    ? doc.getText()
    : doc.getText(selection);
  return {
    editor,
    content,
    language: doc.languageId,
    fileName: doc.fileName,
  };
}

function buildPrompt(task: string, content: string, language: string): string {
  return (
    `You are reviewing a ${language} file.\n\n` +
    `Task: ${task}\n\n` +
    "Return ONLY the improved/fixed code — no explanations, no markdown fences.\n\n" +
    "--- ORIGINAL CODE ---\n" +
    content
  );
}

// ── Command: Improve Code ──────────────────────────────────────────────────────

async function cmdImproveCode(): Promise<void> {
  const ctx = getActiveEditorContent();
  if (!ctx) return;

  const { editor, content, language } = ctx;
  const cfg = vscode.workspace.getConfiguration("jarvis");
  const autoConfirm = cfg.get<boolean>("autoConfirm", false);

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS: Improving code…", cancellable: false },
    async () => {
      try {
        const client = getClient();
        const prompt = buildPrompt("Improve this code: fix bugs, improve readability, follow best practices.", content, language);
        const improved = await client.chat(prompt);

        if (!improved || improved.trim() === content.trim()) {
          vscode.window.showInformationMessage("JARVIS: No improvements suggested.");
          return;
        }

        if (autoConfirm) {
          await applyToEditor(editor, improved);
          vscode.window.showInformationMessage("JARVIS: Code improved.");
        } else {
          const accepted = await showDiffAndConfirm(editor.document, content, improved, "JARVIS — Improved Code");
          if (accepted) {
            await applyToEditor(editor, improved);
            vscode.window.showInformationMessage("JARVIS: Changes applied.");
          } else {
            vscode.window.showInformationMessage("JARVIS: Changes discarded.");
          }
        }
      } catch (err: unknown) {
        vscode.window.showErrorMessage(`JARVIS error: ${(err as Error).message}`);
      }
    }
  );
}

// ── Command: Review Code ───────────────────────────────────────────────────────

async function cmdReviewCode(): Promise<void> {
  const ctx = getActiveEditorContent();
  if (!ctx) return;

  const { content, language } = ctx;

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS: Reviewing code…", cancellable: false },
    async () => {
      try {
        const client = getClient();
        const prompt = `Review this ${language} code. List issues, bugs, and improvements in markdown.\n\n${content}`;
        const review = await client.chat(prompt);
        showOutputPanel("JARVIS — Code Review", review);
      } catch (err: unknown) {
        vscode.window.showErrorMessage(`JARVIS error: ${(err as Error).message}`);
      }
    }
  );
}

// ── Command: Security Scan ─────────────────────────────────────────────────────

async function cmdSecurityScan(): Promise<void> {
  const ctx = getActiveEditorContent();
  if (!ctx) return;

  const { content, language } = ctx;

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS: Running security scan…", cancellable: false },
    async () => {
      try {
        const client = getClient();
        const result = await client.agentRun("security", content);
        showOutputPanel("JARVIS — Security Scan", result);
      } catch (err: unknown) {
        vscode.window.showErrorMessage(`JARVIS error: ${(err as Error).message}`);
      }
    }
  );
}

// ── Command: Explain Code ──────────────────────────────────────────────────────

async function cmdExplainCode(): Promise<void> {
  const ctx = getActiveEditorContent();
  if (!ctx) return;

  const { content, language } = ctx;

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS: Explaining code…", cancellable: false },
    async () => {
      try {
        const client = getClient();
        const prompt = `/explain\n\`\`\`${language}\n${content}\n\`\`\``;
        const explanation = await client.chat(prompt);
        showOutputPanel("JARVIS — Explanation", explanation);
      } catch (err: unknown) {
        vscode.window.showErrorMessage(`JARVIS error: ${(err as Error).message}`);
      }
    }
  );
}

// ── Utilities ──────────────────────────────────────────────────────────────────

async function applyToEditor(editor: vscode.TextEditor, newContent: string): Promise<void> {
  const doc = editor.document;
  const fullRange = new vscode.Range(
    doc.lineAt(0).range.start,
    doc.lineAt(doc.lineCount - 1).range.end
  );
  const edit = new vscode.WorkspaceEdit();
  edit.replace(doc.uri, fullRange, newContent);
  await vscode.workspace.applyEdit(edit);
}

let _outputChannel: vscode.OutputChannel | null = null;
function showOutputPanel(title: string, content: string): void {
  if (!_outputChannel) {
    _outputChannel = vscode.window.createOutputChannel("JARVIS");
  }
  _outputChannel.clear();
  _outputChannel.appendLine(`=== ${title} ===`);
  _outputChannel.appendLine("");
  _outputChannel.appendLine(content);
  _outputChannel.show(true);
}

// ── Activation ─────────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
  if (!_outputChannel) {
    _outputChannel = vscode.window.createOutputChannel("JARVIS");
  }

  // Start the local HTTP bridge so the Python backend can control the IDE
  startBridgeServer(_outputChannel);

  context.subscriptions.push(
    vscode.commands.registerCommand("jarvis.improveCode",  cmdImproveCode),
    vscode.commands.registerCommand("jarvis.reviewCode",   cmdReviewCode),
    vscode.commands.registerCommand("jarvis.securityScan", cmdSecurityScan),
    vscode.commands.registerCommand("jarvis.explainCode",  cmdExplainCode),
  );
}

export function deactivate(): void {
  stopBridgeServer();
  _outputChannel?.dispose();
}
