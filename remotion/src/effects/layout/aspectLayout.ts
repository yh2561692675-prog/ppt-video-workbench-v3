export type Aspect = '16:9' | '9:16';
export type Rect = { x: number; y: number; width: number; height: number };
export type Occupancy = { captionSafeArea: Rect; presenterRect: Rect | null };
export type LayoutSpec = {
  direction: 'horizontal' | 'vertical' | 'staged';
  fontScale: number;
  captionSafeArea: Rect;
  presenterRect: Rect | null;
  collisionResolved: boolean;
};

export function resolveLayout(template: string, aspect: Aspect, occupancy: Occupancy): LayoutSpec {
  const direction =
    aspect === '9:16'
      ? template === 'CompareMode'
        ? 'vertical'
        : template === 'ChartNarration' || template === 'MapHighlight'
          ? 'staged'
          : 'vertical'
      : 'horizontal';
  const fontScale = aspect === '9:16' ? 0.9 : 1;
  let presenterRect = occupancy.presenterRect;
  let collisionResolved = false;
  if (presenterRect && overlaps(presenterRect, occupancy.captionSafeArea)) {
    presenterRect = { x: 0.58, y: 0.05, width: 0.34, height: 0.2 };
    collisionResolved = true;
  }
  return {
    direction,
    fontScale,
    captionSafeArea: occupancy.captionSafeArea,
    presenterRect,
    collisionResolved,
  };
}

function overlaps(left: Rect, right: Rect): boolean {
  return !(
    left.x + left.width <= right.x ||
    right.x + right.width <= left.x ||
    left.y + left.height <= right.y ||
    right.y + right.height <= left.y
  );
}
