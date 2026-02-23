import type { DefinitionAnalysis } from './types';

export interface ControlFlowDiagnostic {
  word: string;
  line: number;
  severity: 'error' | 'warning';
  message: string;
}

function extractLine(message: string): number {
  const match = message.match(/:(\d+)/);
  if (!match) {
    return 0;
  }
  return Number(match[1]);
}

export function collectControlFlowDiagnostics(
  analyses: DefinitionAnalysis[]
): ControlFlowDiagnostic[] {
  const diagnostics: ControlFlowDiagnostic[] = [];

  for (const analysis of analyses) {
    for (const error of analysis.errors) {
      diagnostics.push({
        word: analysis.name,
        line: extractLine(error),
        severity: 'error',
        message: error,
      });
    }

    for (const warning of analysis.warnings) {
      diagnostics.push({
        word: analysis.name,
        line: extractLine(warning),
        severity: 'warning',
        message: warning,
      });
    }
  }

  diagnostics.sort((a, b) => a.line - b.line);
  return diagnostics;
}
