export function CardStack({ cards }: { cards: string[] }) {
  return (
    <div className="card-stack" data-depth-count={Math.min(cards.length, 3)}>
      {cards.slice(0, 3).map((card, index) => (
        <div key={`${index}-${card}`} className="card-stack__card" data-layer={index + 1}>
          {card}
        </div>
      ))}
    </div>
  );
}
