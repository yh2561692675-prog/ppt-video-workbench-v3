type MapPoint = { name: string; region: string };

export function MapHighlight({ points, conclusion }: { points: MapPoint[]; conclusion: string }) {
  return (
    <div className="map-highlight">
      <div className="map-highlight__stable-map" />
      {points.slice(0, 1).map((point) => (
        <div key={point.name} className="map-highlight__point" data-region={point.region}>
          {point.name}
        </div>
      ))}
      <div className="map-highlight__conclusion">{conclusion}</div>
    </div>
  );
}
