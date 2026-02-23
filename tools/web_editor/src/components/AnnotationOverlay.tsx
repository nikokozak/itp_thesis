import type { DefinitionAnalysis, LabelPropagationResult } from '../analysis/types';
import type { WorkspaceSourceMap } from '../utils/workspace-source';
import { fileForGlobalLine } from '../utils/workspace-source';

interface AnnotationOverlayProps {
  analyses: DefinitionAnalysis[];
  labels: LabelPropagationResult[];
  sourceMap?: WorkspaceSourceMap;
}

export function AnnotationOverlay({ analyses, labels, sourceMap }: AnnotationOverlayProps) {
  return (
    <div className="annotation-pane">
      <div className="panel-header">
        <span>Annotations</span>
        <span className="hint">Line-level stack labels and diagnostics.</span>
      </div>

      <div className="annotation-list">
        {analyses.map((analysis) => {
          const trace = labels.find((item) => item.word.toUpperCase() === analysis.name.toUpperCase());
          const startLoc = sourceMap ? fileForGlobalLine(sourceMap, analysis.startLine) : undefined;
          const endLoc = sourceMap ? fileForGlobalLine(sourceMap, analysis.endLine) : undefined;
          return (
            <div key={analysis.name} className="annotation-word-block">
              <strong>{analysis.name}</strong>
              <div className="muted">
                {startLoc && endLoc && startLoc.fileId === endLoc.fileId
                  ? `${startLoc.fileName}:L${startLoc.fileLine}-L${endLoc.fileLine}`
                  : `${analysis.startLine}-${analysis.endLine}`}
              </div>

              {trace?.steps.map((step, index) => (
                <div key={`${step.token.line}-${index}`} className="annotation-line">
                  <span>
                    {sourceMap
                      ? (() => {
                          const loc = fileForGlobalLine(sourceMap, step.token.line);
                          return loc ? `${loc.fileName}:L${loc.fileLine}` : `L${step.token.line}`;
                        })()
                      : `L${step.token.line}`}
                  </span>
                  <code>{step.token.text}</code>
                  <span>[ {step.after.join(' ')} ]</span>
                </div>
              ))}

              {analysis.errors.map((error) => (
                <div key={error} className="error-text">
                  {error}
                </div>
              ))}
              {analysis.warnings.map((warning) => (
                <div key={warning} className="warning-text">
                  {warning}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
