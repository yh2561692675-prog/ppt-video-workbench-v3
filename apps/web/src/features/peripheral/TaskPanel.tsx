import { useEffect, useState } from 'react';

export interface PeripheralTaskState {
  job_id: string;
  status: string;
  progress: number;
  error?: { message: string } | null;
}

export function TaskPanel({
  task,
  onCancel,
  onRetry,
}: {
  task: PeripheralTaskState | null;
  onCancel?: () => void;
  onRetry?: () => void;
}) {
  const [visible, setVisible] = useState(true);
  useEffect(() => setVisible(true), [task?.job_id]);
  if (!task || !visible) return null;
  const terminal = ['succeeded', 'failed', 'cancelled'].includes(task.status);
  return (
    <section aria-label="S1 task" className="rounded border p-3">
      <div className="flex items-center justify-between">
        <strong>{task.status}</strong>
        {terminal && <button onClick={() => setVisible(false)}>关闭</button>}
      </div>
      <progress max={100} value={task.progress} />
      {task.error && <p role="alert">{task.error.message}</p>}
      {!terminal && onCancel && <button onClick={onCancel}>取消</button>}
      {task.status === 'failed' && onRetry && <button onClick={onRetry}>重试</button>}
    </section>
  );
}
