import { afterEach, describe, expect, it, vi } from 'vitest';
import en from '../i18n/en.json';
import es from '../i18n/es.json';
import { readStored, request, store, validLocation } from '../services/api';
import type { Analysis, Prediction, RadarFrame, Replay } from '../services/api';
import { predictionsForFrame } from './temporal';

afterEach(() => vi.unstubAllGlobals());
const keys = (value: object, prefix = ''): string[] => Object.entries(value).flatMap(([key, child]) => typeof child === 'object' ? keys(child, `${prefix}${key}.`) : [`${prefix}${key}`]).sort();
describe('localization and persistence', () => {
  it('provides identical English and Spanish keys including provider errors and scientific quality', () => {
    expect(keys(es)).toEqual(keys(en));
    expect(es.errors.provider_unavailable).not.toEqual(en.errors.provider_unavailable);
    for (const value of Object.values(es.quality)) expect(value.length).toBeGreaterThan(4);
  });
  it('preserves location and alert settings and tolerates blocked storage', () => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) });
    const location = { lat: 27, lon: -82.5, radius_km: 75, threshold: .3 };
    store('location', location); store('levels', ['preventive']);
    expect(readStored('location', {})).toEqual(location);
    expect(readStored('levels', [])).toEqual(['preventive']);
    values.set('location', '{invalid'); expect(readStored('location', location)).toEqual(location);
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error(); }, setItem: () => { throw new Error(); } });
    expect(readStored('location', location)).toEqual(location); expect(() => store('location', location)).not.toThrow();
    expect(validLocation(location)).toBe(true); expect(validLocation({ ...location, lat: 100 })).toBe(false);
    expect(validLocation({ ...location, radius_km: 0 })).toBe(false);
  });
  it('surfaces honest provider failure codes instead of invented observations', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'provider_unavailable' }) }));
    await expect(request('/api/replay')).rejects.toThrow('provider_unavailable');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => { throw new Error(); } }));
    await expect(request('/api/analysis')).rejects.toThrow('request_failed');
  });
});
describe('forecast temporal isolation', () => {
  const first = '2026-10-17T08:00:00Z', second = '2026-10-17T08:02:00Z';
  const frames = [{ time: first }, { time: second }] as RadarFrame[];
  const latest = { id: 'latest', observation_time: second } as Prediction;
  const earlier = { id: 'earlier', observation_time: first } as Prediction;
  const analysis = { frames, predictions: [latest] } as Analysis;
  const replay = { steps: [{ frame: frames[0], predictions: [earlier] }, { frame: frames[1], predictions: [latest, earlier] }] } as Replay;
  it('suppresses latest forecasts while scrubbing to earlier live observations', () => {
    expect(predictionsForFrame('live', 0, analysis, null)).toEqual([]);
    expect(predictionsForFrame('live', 1, analysis, null)).toEqual([latest]);
    expect(predictionsForFrame('live', 8, analysis, null)).toEqual([]);
  });
  it('selects only forecasts made for the replay step, rejecting inconsistent timestamps', () => {
    expect(predictionsForFrame('replay', 0, null, replay)).toEqual([earlier]);
    expect(predictionsForFrame('replay', 1, null, replay)).toEqual([latest]);
    expect(predictionsForFrame('replay', 1, null, null)).toEqual([]);
  });
});
