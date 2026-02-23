export function simplifyLabelExpression(expression: string): string {
  const trimmed = expression.trim();
  if (!trimmed) {
    return '?';
  }

  const duplicatedSquare = trimmed.match(/^(.+)\*\1$/);
  if (duplicatedSquare) {
    return `${duplicatedSquare[1]}²`;
  }

  const duplicatedSum = trimmed.match(/^(.+)\+\1$/);
  if (duplicatedSum) {
    return `2${duplicatedSum[1]}`;
  }

  return trimmed;
}

export function isCompoundStringLabels(labels: string[]): boolean {
  if (labels.length < 2) {
    return false;
  }

  const last = labels[labels.length - 1];
  const penultimate = labels[labels.length - 2];
  return penultimate.endsWith('.addr') && last.endsWith('.len');
}
