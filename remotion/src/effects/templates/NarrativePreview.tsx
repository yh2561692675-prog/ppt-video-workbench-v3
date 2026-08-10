export function NarrativePreview({ cards }: { cards: string[] }) {
  return (
    <div className="narrative-preview" data-card-count={Math.min(cards.length, 6)}>
      {cards.slice(0, 6).map((card, index) => (
        <div
          key={`${index}-${card}`}
          className="narrative-preview__card"
          data-card-index={index + 1}
        >
          {card}
        </div>
      ))}
    </div>
  );
}
