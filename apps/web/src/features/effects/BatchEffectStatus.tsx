export type BatchEffectStatusKind = 'pending' | 'rendering' | 'success' | 'fallback' | 'error';

export interface BatchEffectItem {
  pageId: string;
  status: BatchEffectStatusKind;
  message?: string;
}

export function BatchEffectStatus({ items }: { items: BatchEffectItem[] }) {
  const completed = items.filter(
    (item) => item.status === 'success' || item.status === 'fallback',
  ).length;
  const fallbacks = items.filter((item) => item.status === 'fallback').length;
  return (
    <section className="batch-effect-status" aria-label="批量特效状态">
      <h3>批量状态</h3>
      <p role="status">
        {completed}/{items.length} 完成
      </p>
      {fallbacks > 0 && <p>{fallbacks} 页已安全降级</p>}
      <ul>
        {items.map((item) => (
          <li key={item.pageId} data-status={item.status}>
            {item.pageId}: {statusLabel(item.status)}
            {item.message ? ` - ${item.message}` : ''}
          </li>
        ))}
      </ul>
    </section>
  );
}

function statusLabel(status: BatchEffectStatusKind): string {
  return {
    pending: '待检查',
    rendering: '渲染中',
    success: '完成',
    fallback: '已降级',
    error: '失败',
  }[status];
}
