import { Fragment, useEffect, useMemo } from 'react';
import { Circle, CircleMarker, ImageOverlay, MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { divIcon } from 'leaflet';
import { Marker } from 'react-leaflet';
import { useTranslation } from 'react-i18next';
import type { Location, Prediction, RadarFrame } from '../services/api';

const targetIcon = divIcon({ className: 'target-marker', html: '<span></span>', iconSize: [24, 24], iconAnchor: [12, 12] });

function Controls({ location, onMove }: { location: Location; onMove: (lat: number, lon: number) => void }) {
  const map = useMap();
  useEffect(() => { map.setView([location.lat, location.lon], map.getZoom(), { animate: false }); }, [location.lat, location.lon, map]);
  useMapEvents({ click: event => { const point = event.latlng.wrap(); onMove(point.lat, point.lng); } });
  return null;
}
export default function RadarMap({ location, frame, predictions, onMove }: { location: Location; frame?: RadarFrame; predictions: Prediction[]; onMove: (lat: number, lon: number) => void }) {
  const { t } = useTranslation();
  const targetPosition = useMemo<[number, number]>(() => [location.lat, location.lon], [location.lat, location.lon]);
  return <MapContainer center={[location.lat, location.lon]} zoom={8} className="radar-map" scrollWheelZoom>
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <Controls location={location} onMove={onMove} />
    {frame && <ImageOverlay key={`${frame.time}:${frame.source}`} url={frame.image} bounds={frame.bounds} opacity={0.76} zIndex={300} />}
    <Circle center={[location.lat, location.lon]} radius={location.radius_km * 1000} pathOptions={{ color: '#65e0c2', weight: 1, dashArray: '5 6', fillOpacity: 0.025 }} />
    <Marker position={targetPosition} draggable icon={targetIcon} eventHandlers={{ dragend: event => { const point = event.target.getLatLng().wrap(); onMove(point.lat, point.lng); } }}><Tooltip>{t('target')}</Tooltip></Marker>
    {predictions.map(p => <Fragment key={p.id}>
      {p.polygon.length > 2 && <Polygon positions={p.polygon} pathOptions={{ color: p.level === 'imminent' ? '#ff8084' : '#f3c469', weight: 1.5, fillOpacity: .1 }} />}
      <CircleMarker center={[p.lat, p.lon]} radius={4} pathOptions={{ color: '#f3c469' }}><Tooltip>{t(p.intensity)} · {p.peak_rate.toFixed(1)} mm/h</Tooltip></CircleMarker>
      {p.vector_end && p.direction_deg != null && (p.speed_kmh ?? 0) >= 1.8 && <><Polyline positions={[[p.lat, p.lon], p.vector_end]} pathOptions={{ color: '#faf5e8', weight: 2, dashArray: '4 4' }} /><Marker position={p.vector_end} interactive={false} icon={divIcon({ className: 'motion-arrow', html: `<span style="transform:rotate(${p.direction_deg}deg)">↑</span>`, iconSize: [20, 24], iconAnchor: [10, 12] })} /></>}
    </Fragment>)}
  </MapContainer>;
}
