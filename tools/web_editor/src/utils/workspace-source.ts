import type { WorkspaceFile } from '../store/workspace-store';

export interface WorkspaceFileRange {
  fileId: string;
  fileName: string;
  startLine: number;
  endLine: number;
  lineCount: number;
}

export interface WorkspaceSourceMap {
  source: string;
  files: WorkspaceFileRange[];
}

function normalizeNewlines(source: string): string {
  return source.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

function countNewlines(source: string): number {
  let count = 0;
  for (let i = 0; i < source.length; i += 1) {
    if (source[i] === '\n') {
      count += 1;
    }
  }
  return count;
}

function countLines(source: string): number {
  // Mirrors CodeMirror (and our parser) semantics: even "" is 1 line.
  return normalizeNewlines(source).split('\n').length;
}

export function buildWorkspaceSourceMap(files: WorkspaceFile[]): WorkspaceSourceMap {
  let currentLine = 1;
  const sourceParts: string[] = [];
  const ranges: WorkspaceFileRange[] = [];

  for (const file of files) {
    const header = `\\\\ --- file: ${file.name} ---\n`;
    sourceParts.push(header);
    currentLine += countNewlines(header);

    const normalized = normalizeNewlines(file.content);
    const startLine = currentLine;
    const lineCount = countLines(normalized);
    const endLine = startLine + lineCount - 1;

    ranges.push({
      fileId: file.id,
      fileName: file.name,
      startLine,
      endLine,
      lineCount,
    });

    sourceParts.push(normalized);
    currentLine += countNewlines(normalized);

    // Always terminate file blocks with a newline so the next header starts on a fresh line,
    // even if the file itself ends in a trailing newline.
    sourceParts.push('\n');
    currentLine += 1;
  }

  return {
    source: sourceParts.join(''),
    files: ranges,
  };
}

export function fileForGlobalLine(
  map: WorkspaceSourceMap | undefined,
  globalLine: number
): { fileId: string; fileName: string; fileLine: number } | undefined {
  if (!map || globalLine < 1) {
    return undefined;
  }

  for (const file of map.files) {
    if (globalLine >= file.startLine && globalLine <= file.endLine) {
      return {
        fileId: file.fileId,
        fileName: file.fileName,
        fileLine: globalLine - file.startLine + 1,
      };
    }
  }

  return undefined;
}

export function globalLineForFileLine(
  map: WorkspaceSourceMap | undefined,
  fileId: string,
  fileLine: number
): number | undefined {
  if (!map || fileLine < 1) {
    return undefined;
  }

  const file = map.files.find((entry) => entry.fileId === fileId);
  if (!file) {
    return undefined;
  }

  if (fileLine > file.lineCount) {
    return undefined;
  }

  return file.startLine + fileLine - 1;
}

