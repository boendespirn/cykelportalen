"use client";

import dynamic from "next/dynamic";

const StageMap = dynamic(() => import("./StageMap"), { ssr: false });

type LatLng = [number, number];

export default function StageMapLoader(props: {
  start: LatLng;
  finish: LatLng;
  startName: string;
  finishName: string;
}) {
  return <StageMap {...props} />;
}
