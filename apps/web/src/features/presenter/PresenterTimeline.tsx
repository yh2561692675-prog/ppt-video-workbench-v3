import { useState } from 'react';

import type { Project } from '../../api/client';
import {
  PresenterApiError,
  presenterApi,
  type PresenterAnchor,
  type PresenterTimeline as Timeline,
} from './api';

export function PresenterTimeline({
  projectId,
  timeline,
  onChanged,
}: {
  projectId: string;
  timeline: Timeline | null;
  onChanged: (project: Project) => void;
}) {
  const [conflict, setConflict] = useState('');
  async function lock(anchor: PresenterAnchor, startMs: number, endMs: number) {
    setConflict('');
    try {
      onChanged(
        await presenterApi.patchAnchor(projectId, anchor.page_id, {
          expected_revision: timeline!.revision,
          start_ms: startMs,
          end_ms: endMs,
          manual_lock: true,
        }),
      );
    } catch (reason) {
      if (reason instanceof PresenterApiError && reason.status === 409) {
        setConflict(
          `版本冲突：服务器当前为 r${reason.currentRevision ?? '?'}，请刷新后比较，未覆盖任何修改。`,
        );
        return;
      }
      setConflict(reason instanceof Error ? reason.message : '锚点更新失败');
    }
  }
  return (
    <section className="presenter-zone presenter-timeline" aria-label="演讲者时间线">
      <h3>5. 时间线与人工锁定</h3>
      {!timeline ? (
        <p>尚未生成时间线</p>
      ) : (
        timeline.anchors.map((anchor, index) => (
          <AnchorEditor key={anchor.page_id} anchor={anchor} pageNumber={index + 1} onLock={lock} />
        ))
      )}
      {conflict && (
        <p className="error" role="alert">
          {conflict}
        </p>
      )}
    </section>
  );
}

function AnchorEditor({
  anchor,
  pageNumber,
  onLock,
}: {
  anchor: PresenterAnchor;
  pageNumber: number;
  onLock: (anchor: PresenterAnchor, startMs: number, endMs: number) => Promise<void>;
}) {
  const [startMs, setStartMs] = useState(anchor.start_ms);
  const [endMs, setEndMs] = useState(anchor.end_ms);
  return (
    <div className="presenter-anchor-row">
      <span>
        第 {pageNumber} 页 {anchor.manual_lock ? '· 已锁定' : ''}
      </span>
      <label>
        开始 ms
        <input
          aria-label={`第 ${pageNumber} 页开始`}
          type="number"
          min={0}
          value={startMs}
          onChange={(event) => setStartMs(Number(event.target.value))}
        />
      </label>
      <label>
        结束 ms
        <input
          aria-label={`第 ${pageNumber} 页结束`}
          type="number"
          min={1}
          value={endMs}
          onChange={(event) => setEndMs(Number(event.target.value))}
        />
      </label>
      <button className="secondary" onClick={() => void onLock(anchor, startMs, endMs)}>
        保存并锁定
      </button>
    </div>
  );
}
