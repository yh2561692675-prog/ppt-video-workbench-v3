export function CompareMode({
  left,
  right,
  active,
}: {
  left: string;
  right: string;
  active: 'left' | 'right';
}) {
  return (
    <div className="compare-mode" data-active={active}>
      <div className="compare-mode__left" data-emphasis={active === 'left' ? 'high' : 'normal'}>
        {left}
      </div>
      <div className="compare-mode__right" data-emphasis={active === 'right' ? 'high' : 'normal'}>
        {right}
      </div>
    </div>
  );
}
