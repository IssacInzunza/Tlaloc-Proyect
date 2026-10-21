export interface Location { lat: number; lon: number; radius_km: number; threshold: number }
export interface Coverage { status: string; valid_fraction: number; target_valid: boolean; age_minutes: number | null; quality: string; reason?: string }
export interface RadarLayer { time: string; image: string; bounds: [[number, number], [number, number]]; source: string; unit: 'mm/h' | 'dBZ'; valid_fraction: number; max_value: number | null; echo_pixels: number; product?: string }
export interface RadarFrame { time: string; image: string; bounds: [[number, number], [number, number]]; source: string; coverage: Coverage; layers?: { rate: RadarLayer; reflectivity?: RadarLayer } }
export interface Prediction {
  id: string; level: string; intensity: string; peak_rate: number; area_km2: number;
  distance_km: number; lat: number; lon: number; direction_deg: number | null;
  speed_kmh: number | null; arrival_minutes: [number, number] | null; confidence: string;
  arrival_status?: string; event: string; observation_time: string; data_quality: string;
  vector_end: [number, number] | null; polygon: [number, number][];
}
export interface Analysis { location: Location; coverage: Coverage; frames: RadarFrame[]; predictions: Prediction[]; observation_time: string | null; processing_seconds: number }
export interface HistoryItem { time: string; action: string; alert: Prediction }
export interface Step { time: string; predictions: Prediction[]; coverage: Coverage; frame: RadarFrame }
export interface Replay { steps: Step[]; metrics: Record<string, number | null>; run_id: string; location: Location; start: string; end: string }
export interface Sample { location: Location; frames: {time: string}[] }
export interface Place { name: string; lat: number; lon: number; kind?: string; provider?: string }

export function query(location: Location) { return new URLSearchParams(Object.entries(location).map(([key, value]) => [key, String(value)])).toString(); }
export class ApiRequestError extends Error {
  constructor(public status: number, detail: string) { super(detail); }
}
export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiRequestError(response.status, typeof body.detail === 'string' ? body.detail : 'request_failed');
  }
  return response.json() as Promise<T>;
}
export function readStored<T>(key: string, fallback: T): T {
  try { const value = localStorage.getItem(key); return value === null ? fallback : JSON.parse(value) as T; }
  catch { return fallback; }
}
export function store(key: string, value: unknown) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage may be disabled. */ } }
export function validLocation(value: Location): boolean {
  return !!value && Number.isFinite(value.lat) && Math.abs(value.lat) <= 90 && Number.isFinite(value.lon) && Math.abs(value.lon) <= 180 && value.radius_km >= 10 && value.radius_km <= 100 && value.threshold >= 0.1 && value.threshold <= 10;
}
