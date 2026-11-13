import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GeoValidacion } from "../api/schemas";

const CABA: L.LatLngTuple = [-34.6118, -58.4173];

export function MapView({ geo }: { geo: GeoValidacion | null }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const [tilesError, setTilesError] = useState(false);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: false, attributionControl: true }).setView(CABA, 11);
    const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    });
    tiles.on("tileerror", () => setTilesError(true));
    tiles.addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    marker.current?.remove();
    marker.current = null;
    if (geo?.lat != null && geo.lon != null) {
      const ok = geo.estado === "validada";
      marker.current = L.circleMarker([geo.lat, geo.lon], {
        radius: 10,
        color: ok ? "#3fb950" : "#f5a524",
        weight: 3,
        fillOpacity: 0.35,
      })
        .addTo(m)
        .bindTooltip(geo.direccion_normalizada ?? "", { direction: "top" });
      m.setView([geo.lat, geo.lon], 16, { animate: true });
    } else {
      m.setView(CABA, 11);
    }
  }, [geo?.lat, geo?.lon, geo?.estado, geo?.direccion_normalizada]);

  return (
    <div className="map-wrap">
      <div ref={el} className="map" />
      {geo?.lat == null && <div className="map-overlay">Sin coordenadas: validar la dirección</div>}
      {tilesError && geo?.lat != null && (
        <div className="map-overlay small">
          Mapa sin conexión · {geo.lat.toFixed(5)}, {geo.lon?.toFixed(5)}
        </div>
      )}
      {geo?.comisaria_vecinal && <div className="map-tag">Comisaría vecinal {geo.comisaria_vecinal}</div>}
    </div>
  );
}
