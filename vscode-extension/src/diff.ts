/**
 * Diff preview — shows a side-by-side diff and asks for confirmation
 * before the extension applies any AI changes to the editor.
 *
 * Uses VS Code's built-in diff provider (vscode.diff command) so no
 * external deps are needed.
 */

import * as vscode from "vscode";

/**
 * Open a diff tab showing original vs. proposed content.
 * Returns true if the user clicks "Apply", false otherwise.
 */
export async function showDiffAndConfirm(
  originalDoc: vscode.TextDocument,
  originalContent: string,
  proposedContent: string,
  title: string,
): Promise<boolean> {
  // Write the proposed content into an in-memory ("untitled") document
  // via a virtual URI so VS Code can diff them without touching the real file.
  const scheme = "jarvis-diff";
  const proposedUri = originalDoc.uri.with({ scheme });

  // Register a one-shot content provider for this URI
  const provider = new SingleUseProvider(proposedContent);
  const providerReg = vscode.workspace.registerTextDocumentContentProvider(scheme, provider);

  try {
    // Open the diff editor
    await vscode.commands.executeCommand(
      "vscode.diff",
      originalDoc.uri,       // left — original (real file, read-only in diff)
      proposedUri,           // right — proposed (virtual)
      title,
      { preview: true, viewColumn: vscode.ViewColumn.Active }
    );

    // Ask the user
    const answer = await vscode.window.showInformationMessage(
      "JARVIS: Apply AI-suggested changes?",
      { modal: false },
      "Apply",
      "Discard",
    );

    return answer === "Apply";
  } finally {
    providerReg.dispose();
    // Close the diff tab automatically after the decision
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
  }
}

// ── Virtual document provider ──────────────────────────────────────────────────

class SingleUseProvider implements vscode.TextDocumentContentProvider {
  constructor(private readonly content: string) {}

  provideTextDocumentContent(_uri: vscode.Uri): string {
    return this.content;
  }
}
