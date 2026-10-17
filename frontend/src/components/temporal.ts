import type { Analysis, Prediction, Replay } from '../services/api';

/** Never draw latest-only forecasts on an earlier radar image. */
export function predictionsForFrame(mode: 'live' | 'replay', index: number, analysis: Analysis | null, replay: Replay | null): Prediction[] {
  const step = replay?.steps[index];
  const frame = mode === 'replay' ? step?.frame : analysis?.frames[index];
  if (!frame || (mode === 'live' && index !== (analysis?.frames.length ?? 0) - 1)) return [];
  const predictions = mode === 'replay' ? step?.predictions : analysis?.predictions;
  return (predictions ?? []).filter(p => Date.parse(p.observation_time) === Date.parse(frame.time));
}
