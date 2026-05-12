"use client";

import { useEffect, useRef } from "react";

type LatLng = [number, number];

interface StageMapProps {
  start: LatLng;
  finish: LatLng;
  startName: string;
  finishName: string;
}

export default function StageMap({ start, finish, startName, finishName }: StageMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    // Clear any stale Leaflet state from HMR/StrictMode double-render
    const container = containerRef.current as HTMLElement & { _leaflet_id?: number };
    if (container._leaflet_id) {
      delete container._leaflet_id;
      container.innerHTML = "";
    }

    import("leaflet").then(({ default: L }) => {
      // Fix Leaflet default icon path issue in Next.js
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const map = L.map(containerRef.current!, { zoomControl: true, attributionControl: false });
      mapRef.current = map;

      // OpenStreetMap standard tiles
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: "© OpenStreetMap",
      }).addTo(map);

      // Bounding box
      const bounds = L.latLngBounds([start, finish]).pad(0.35);
      map.fitBounds(bounds);

      // Custom start marker (green)
      const startIcon = L.divIcon({
        html: `<div style="width:12px;height:12px;background:#10b981;border:2px solid white;border-radius:50%;box-shadow:0 0 6px rgba(16,185,129,0.6)"></div>`,
        className: "",
        iconAnchor: [6, 6],
      });

      // Custom finish marker (red)
      const finishIcon = L.divIcon({
        html: `<div style="width:14px;height:14px;background:#ef4444;border:2px solid white;border-radius:50%;box-shadow:0 0 6px rgba(239,68,68,0.6)"></div>`,
        className: "",
        iconAnchor: [7, 7],
      });

      L.marker(start, { icon: startIcon })
        .addTo(map)
        .bindTooltip(startName, { permanent: true, direction: "top", className: "leaflet-label" });

      L.marker(finish, { icon: finishIcon })
        .addTo(map)
        .bindTooltip(finishName, { permanent: true, direction: "top", className: "leaflet-label" });

      // Dashed route line
      L.polyline([start, finish], {
        color: "#10b981",
        weight: 2,
        dashArray: "8 6",
        opacity: 0.7,
      }).addTo(map);
    });

    return () => {
      if (mapRef.current) {
        (mapRef.current as { remove: () => void }).remove();
        mapRef.current = null;
      }
    };
  }, [start, finish, startName, finishName]);

  return (
    <>
      <style>{`
        .leaflet-label {
          background: rgba(15,23,42,0.9) !important;
          border: 1px solid rgba(71,85,105,0.5) !important;
          color: #e2e8f0 !important;
          font-size: 11px !important;
          font-weight: 500 !important;
          padding: 2px 6px !important;
          border-radius: 4px !important;
          box-shadow: none !important;
          white-space: nowrap !important;
        }
        .leaflet-label::before { display: none !important; }
      `}</style>
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <div ref={containerRef} style={{ width: "100%", height: "280px", borderRadius: "12px", overflow: "hidden" }} />
    </>
  );
}
