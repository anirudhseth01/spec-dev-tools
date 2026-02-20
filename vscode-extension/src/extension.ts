import * as vscode from 'vscode';
import * as path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

// Diagnostic collection for spec validation
let diagnosticCollection: vscode.DiagnosticCollection;

// Status bar item
let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    console.log('Spec Dev Tools extension is now active');

    // Create diagnostic collection
    diagnosticCollection = vscode.languages.createDiagnosticCollection('spec-dev');
    context.subscriptions.push(diagnosticCollection);

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'specDev.validate';
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('specDev.validate', validateCurrentSpec),
        vscode.commands.registerCommand('specDev.implement', implementSpec),
        vscode.commands.registerCommand('specDev.preview', previewGeneratedCode),
        vscode.commands.registerCommand('specDev.lint', lintCurrentSpec),
        vscode.commands.registerCommand('specDev.createFromTemplate', createFromTemplate),
        vscode.commands.registerCommand('specDev.showGraph', showDependencyGraph)
    );

    // Register hover provider
    context.subscriptions.push(
        vscode.languages.registerHoverProvider('markdown', new SpecHoverProvider())
    );

    // Register completion provider
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            'markdown',
            new SpecCompletionProvider(),
            '#', '|', '-'
        )
    );

    // Register code actions provider
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            'markdown',
            new SpecCodeActionProvider(),
            { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
        )
    );

    // Auto-validate on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((document) => {
            if (isSpecFile(document)) {
                const config = vscode.workspace.getConfiguration('specDev');
                if (config.get('autoValidate')) {
                    validateDocument(document);
                }
                if (config.get('lintOnSave')) {
                    lintDocument(document);
                }
            }
        })
    );

    // Update status bar on editor change
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor((editor) => {
            updateStatusBar(editor);
        })
    );

    // Initial status bar update
    updateStatusBar(vscode.window.activeTextEditor);
}

export function deactivate() {
    diagnosticCollection.dispose();
    statusBarItem.dispose();
}

// Check if document is a spec file
function isSpecFile(document: vscode.TextDocument): boolean {
    const fileName = path.basename(document.fileName);
    return fileName === 'block.md' || fileName.endsWith('.spec.md');
}

// Get spec name from document
function getSpecName(document: vscode.TextDocument): string {
    const filePath = document.fileName;
    const specsDir = vscode.workspace.getConfiguration('specDev').get('specsDirectory') as string;

    // Find specs directory in path
    const specsIndex = filePath.indexOf(specsDir);
    if (specsIndex === -1) {
        return path.basename(path.dirname(filePath));
    }

    const relativePath = filePath.substring(specsIndex + specsDir.length + 1);
    const parts = relativePath.split(path.sep);

    if (parts[parts.length - 1] === 'block.md') {
        parts.pop();
    }

    return parts.join('/');
}

// Update status bar
function updateStatusBar(editor: vscode.TextEditor | undefined) {
    if (editor && isSpecFile(editor.document)) {
        const specName = getSpecName(editor.document);
        statusBarItem.text = `$(file-code) Spec: ${specName}`;
        statusBarItem.tooltip = 'Click to validate spec';
        statusBarItem.show();
    } else {
        statusBarItem.hide();
    }
}

// Run Python CLI command
async function runSpecDevCommand(args: string[]): Promise<{ stdout: string; stderr: string }> {
    const config = vscode.workspace.getConfiguration('specDev');
    const pythonPath = config.get('pythonPath') as string;
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';

    const command = `${pythonPath} -m src.cli.main ${args.join(' ')}`;

    return execAsync(command, { cwd: workspaceFolder });
}

// Validate current spec
async function validateCurrentSpec() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !isSpecFile(editor.document)) {
        vscode.window.showWarningMessage('No spec file is currently open');
        return;
    }

    await validateDocument(editor.document);
}

// Validate document
async function validateDocument(document: vscode.TextDocument) {
    const specName = getSpecName(document);
    const diagnostics: vscode.Diagnostic[] = [];

    try {
        statusBarItem.text = '$(sync~spin) Validating...';

        const { stdout, stderr } = await runSpecDevCommand([
            'validate', specName, '--json'
        ]);

        // Parse validation results
        if (stderr) {
            const match = stderr.match(/error|warning|invalid/i);
            if (match) {
                diagnostics.push(new vscode.Diagnostic(
                    new vscode.Range(0, 0, 0, 0),
                    stderr,
                    vscode.DiagnosticSeverity.Error
                ));
            }
        }

        statusBarItem.text = diagnostics.length > 0
            ? `$(error) Spec: ${specName} (${diagnostics.length} issues)`
            : `$(check) Spec: ${specName}`;

    } catch (error: any) {
        diagnostics.push(new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 0),
            `Validation failed: ${error.message}`,
            vscode.DiagnosticSeverity.Error
        ));
        statusBarItem.text = `$(error) Spec: ${specName}`;
    }

    diagnosticCollection.set(document.uri, diagnostics);
}

// Lint current spec
async function lintCurrentSpec() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !isSpecFile(editor.document)) {
        vscode.window.showWarningMessage('No spec file is currently open');
        return;
    }

    await lintDocument(editor.document);
}

// Lint document
async function lintDocument(document: vscode.TextDocument) {
    const specName = getSpecName(document);
    const diagnostics: vscode.Diagnostic[] = [];

    try {
        const { stdout } = await runSpecDevCommand([
            'lint', specName, '--json'
        ]);

        // Parse lint results
        const results = JSON.parse(stdout);

        for (const result of results) {
            for (const issue of result.issues || []) {
                const line = (issue.line || 1) - 1;
                const severity = issue.severity === 'error'
                    ? vscode.DiagnosticSeverity.Error
                    : issue.severity === 'warning'
                    ? vscode.DiagnosticSeverity.Warning
                    : vscode.DiagnosticSeverity.Information;

                const diagnostic = new vscode.Diagnostic(
                    new vscode.Range(line, 0, line, 1000),
                    `[${issue.rule_id}] ${issue.message}`,
                    severity
                );
                diagnostic.source = 'spec-dev';
                diagnostic.code = issue.rule_id;

                diagnostics.push(diagnostic);
            }
        }

    } catch (error: any) {
        // Ignore lint errors silently
    }

    // Merge with existing diagnostics
    const existing = diagnosticCollection.get(document.uri) || [];
    diagnosticCollection.set(document.uri, [...existing, ...diagnostics]);
}

// Implement spec
async function implementSpec() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !isSpecFile(editor.document)) {
        vscode.window.showWarningMessage('No spec file is currently open');
        return;
    }

    const specName = getSpecName(editor.document);

    const options = await vscode.window.showQuickPick([
        { label: 'Full Implementation', value: '' },
        { label: 'Dry Run (Preview)', value: '--dry-run' },
        { label: 'Skip Tests', value: '--skip-tests' },
        { label: 'Incremental', value: '--incremental' },
    ], {
        placeHolder: 'Select implementation mode'
    });

    if (!options) return;

    const terminal = vscode.window.createTerminal('Spec Dev');
    terminal.show();
    terminal.sendText(`python3 -m src.cli.main implement ${specName} ${options.value}`);
}

// Preview generated code
async function previewGeneratedCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !isSpecFile(editor.document)) {
        vscode.window.showWarningMessage('No spec file is currently open');
        return;
    }

    const specName = getSpecName(editor.document);

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `Previewing code for ${specName}...`,
        cancellable: false
    }, async () => {
        try {
            const { stdout } = await runSpecDevCommand([
                'implement', specName, '--dry-run', '--verbose'
            ]);

            // Show in output channel
            const outputChannel = vscode.window.createOutputChannel('Spec Dev Preview');
            outputChannel.clear();
            outputChannel.appendLine(stdout);
            outputChannel.show();

        } catch (error: any) {
            vscode.window.showErrorMessage(`Preview failed: ${error.message}`);
        }
    });
}

// Create spec from template
async function createFromTemplate() {
    // Get available templates
    let templates: string[] = [];

    try {
        const { stdout } = await runSpecDevCommand(['template', 'list', '--json']);
        const data = JSON.parse(stdout);
        templates = data.map((t: any) => t.name);
    } catch {
        templates = ['api-service', 'cli-tool', 'library', 'worker-service', 'data-pipeline'];
    }

    const template = await vscode.window.showQuickPick(templates, {
        placeHolder: 'Select a template'
    });

    if (!template) return;

    const specName = await vscode.window.showInputBox({
        prompt: 'Enter spec name',
        placeHolder: 'my-feature'
    });

    if (!specName) return;

    try {
        await runSpecDevCommand([
            'template', 'create', template, specName
        ]);

        // Open the created file
        const config = vscode.workspace.getConfiguration('specDev');
        const specsDir = config.get('specsDirectory') as string;
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (workspaceFolder) {
            const filePath = path.join(workspaceFolder, specsDir, specName, 'block.md');
            const document = await vscode.workspace.openTextDocument(filePath);
            vscode.window.showTextDocument(document);
        }

        vscode.window.showInformationMessage(`Created spec: ${specName}`);

    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed to create spec: ${error.message}`);
    }
}

// Show dependency graph
async function showDependencyGraph() {
    try {
        const { stdout } = await runSpecDevCommand(['graph', '--format', 'mermaid']);

        // Create webview panel
        const panel = vscode.window.createWebviewPanel(
            'specDevGraph',
            'Spec Dependency Graph',
            vscode.ViewColumn.Two,
            { enableScripts: true }
        );

        // Extract mermaid code
        const mermaidMatch = stdout.match(/```mermaid\n([\s\S]*?)```/);
        const mermaidCode = mermaidMatch ? mermaidMatch[1] : stdout;

        panel.webview.html = `
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            </head>
            <body>
                <div class="mermaid">
                    ${mermaidCode}
                </div>
                <script>
                    mermaid.initialize({ startOnLoad: true, theme: 'dark' });
                </script>
            </body>
            </html>
        `;

    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed to generate graph: ${error.message}`);
    }
}

// Hover provider for spec sections
class SpecHoverProvider implements vscode.HoverProvider {
    private sectionDescriptions: { [key: string]: string } = {
        'Metadata': 'Spec identification: ID, version, status, tech stack, author',
        'Overview': 'Summary, goals, non-goals, and background context',
        'Inputs': 'User inputs, system inputs, and environment variables',
        'Outputs': 'Return values, side effects, and events',
        'Dependencies': 'Internal modules, external packages, and services',
        'API Contract': 'Endpoints, request/response schemas, and error codes',
        'Test Cases': 'Unit tests, integration tests, and coverage targets',
        'Edge Cases': 'Boundary conditions, concurrency, and failure modes',
        'Error Handling': 'Error types, retry strategies, and handlers',
        'Performance': 'Latency targets (p50/p95/p99), RPS, memory limits',
        'Security': 'Authentication, authorization, PII handling, encryption',
        'Implementation': 'Algorithms, patterns, and constraints',
        'Acceptance': 'Acceptance criteria and definition of done',
    };

    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position
    ): vscode.ProviderResult<vscode.Hover> {
        if (!isSpecFile(document)) return null;

        const line = document.lineAt(position.line).text;

        // Check for section headers
        const sectionMatch = line.match(/^##\s+\d+\.\s+(.+)$/);
        if (sectionMatch) {
            const sectionName = sectionMatch[1].trim();
            const description = this.sectionDescriptions[sectionName];

            if (description) {
                return new vscode.Hover(
                    new vscode.MarkdownString(`**${sectionName}**\n\n${description}`)
                );
            }
        }

        return null;
    }
}

// Completion provider for spec sections
class SpecCompletionProvider implements vscode.CompletionItemProvider {
    provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position
    ): vscode.ProviderResult<vscode.CompletionItem[]> {
        if (!isSpecFile(document)) return [];

        const line = document.lineAt(position.line).text;
        const items: vscode.CompletionItem[] = [];

        // Section headers
        if (line.startsWith('##')) {
            const sections = [
                '1. Metadata',
                '2. Overview',
                '3. Inputs',
                '4. Outputs',
                '5. Dependencies',
                '6. API Contract',
                '7. Test Cases',
                '8. Edge Cases',
                '9. Error Handling',
                '10. Performance',
                '11. Security',
                '12. Implementation',
                '13. Acceptance',
            ];

            for (const section of sections) {
                const item = new vscode.CompletionItem(
                    section,
                    vscode.CompletionItemKind.Keyword
                );
                item.insertText = ` ${section}\n\n`;
                items.push(item);
            }
        }

        // Table row templates
        if (line.includes('|')) {
            const item = new vscode.CompletionItem(
                'Table Row',
                vscode.CompletionItemKind.Snippet
            );
            item.insertText = new vscode.SnippetString(
                '| ${1:value} | ${2:value} | ${3:value} |'
            );
            items.push(item);
        }

        return items;
    }
}

// Code actions provider for quick fixes
class SpecCodeActionProvider implements vscode.CodeActionProvider {
    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range,
        context: vscode.CodeActionContext
    ): vscode.ProviderResult<vscode.CodeAction[]> {
        if (!isSpecFile(document)) return [];

        const actions: vscode.CodeAction[] = [];

        for (const diagnostic of context.diagnostics) {
            if (diagnostic.code === 'COMP-001') {
                // Missing section - add it
                const action = new vscode.CodeAction(
                    'Add missing section',
                    vscode.CodeActionKind.QuickFix
                );
                action.diagnostics = [diagnostic];
                action.isPreferred = true;
                actions.push(action);
            }

            if (diagnostic.code === 'COMP-003') {
                // Missing test cases
                const action = new vscode.CodeAction(
                    'Add test case template',
                    vscode.CodeActionKind.QuickFix
                );
                action.diagnostics = [diagnostic];
                actions.push(action);
            }
        }

        return actions;
    }
}
