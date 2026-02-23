import type { DefinitionAnalysis, LabelPropagationResult } from '../analysis/types';

interface DataflowDiagramProps {
  selectedWord?: string;
  analyses: DefinitionAnalysis[];
  labels: LabelPropagationResult[];
}

export function DataflowDiagram({ selectedWord, analyses, labels }: DataflowDiagramProps) {
  const analysis = selectedWord
    ? analyses.find((item) => item.name.toUpperCase() === selectedWord.toUpperCase())
    : analyses[0];
  const labelTrace = selectedWord
    ? labels.find((item) => item.word.toUpperCase() === selectedWord.toUpperCase())
    : labels[0];

  if (!analysis || !labelTrace) {
    return (
      <div className="dataflow-pane">
        <div className="panel-header">
          <span>Dataflow</span>
        </div>
        <div className="muted">Select a compiled word to inspect dataflow.</div>
      </div>
    );
  }

  return (
    <div className="dataflow-pane">
      <div className="panel-header">
        <span>Dataflow: {analysis.name}</span>
        <span className="hint">Producer/consumer view (token highlights). Arrow overlay deferred.</span>
      </div>

      <div className="dataflow-list">
        {analysis.steps.map((step, index) => {
          const labelStep = labelTrace.steps[index];
          return (
            <div key={`${step.token.line}-${step.token.column}-${index}`} className="dataflow-step">
              <div className="dataflow-token">{step.token.text}</div>
              <div className="dataflow-io">
                <span>consumes {step.consumed}</span>
                <span>produces {step.produced}</span>
              </div>
              <div className="dataflow-labels">
                <span>before: [ {labelStep?.before.join(' ') ?? ''} ]</span>
                <span>after: [ {labelStep?.after.join(' ') ?? ''} ]</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
