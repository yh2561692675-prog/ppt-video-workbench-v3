import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChangeEvent, useState } from 'react';

import { api, NarrationImportAssignment, NarrationPage } from '../../../api/client';

interface Props {
  projectId: string;
  pages: NarrationPage[];
}

const labels: Record<NarrationImportAssignment['method'], string> = {
  page_number: '按页码匹配',
  page_title: '按页标题匹配',
  sequential: '按顺序分配',
};

export function NarrationImportPanel({ projectId, pages }: Props) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState('');
  const [assignments, setAssignments] = useState<NarrationImportAssignment[]>([]);
  const [message, setMessage] = useState('');
  const preview = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('请选择旁白稿文件');
      return api.previewNarrationImport(projectId, file);
    },
    onSuccess: (result) => {
      setSourceName(result.source_name);
      setAssignments(result.assignments);
      setMessage('已生成逐页预览，请核对后写入草稿。');
    },
  });
  const commit = useMutation({
    mutationFn: () =>
      api.commitNarrationImport(projectId, {
        source_name: sourceName,
        assignments: assignments.map((assignment) => ({
          page_id: assignment.page_id,
          text: assignment.text,
          expected_revision_id:
            pages.find((page) => page.id === assignment.page_id)?.narration?.revision_id ?? null,
          method: assignment.method,
        })),
      }),
    onSuccess: (result) => {
      setMessage(`已写入 ${result.length} 页旁白草稿，仍需逐页确认。`);
      void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      void queryClient.invalidateQueries({
        queryKey: ['narration-gate', projectId],
      });
    },
  });

  function choose(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setAssignments([]);
    setMessage('');
  }

  function changeText(pageId: string, text: string) {
    setAssignments((current) =>
      current.map((item) => (item.page_id === pageId ? { ...item, text } : item)),
    );
  }

  function writeDrafts() {
    if (assignments.some((item) => !item.text.trim())) {
      setMessage('请先补齐每一页旁白，再写入草稿。');
      return;
    }
    if (
      assignments.some((item) => pages.find((page) => page.id === item.page_id)?.narration) &&
      !window.confirm('写入后会生成新的未确认版本，现有确认状态将失效。是否继续？')
    )
      return;
    commit.mutate();
  }

  return (
    <section className="narration-import-panel">
      <h3>导入旁白稿</h3>
      <p className="muted">
        支持按页标题/页码分段，或将整篇连续文本按页顺序分配；写入前可逐页修改。
      </p>
      <label>
        上传旁白稿
        <input type="file" accept=".docx,.txt" onChange={choose} />
      </label>
      <button
        className="secondary"
        disabled={!file || preview.isPending}
        onClick={() => preview.mutate()}
      >
        {preview.isPending ? '正在解析…' : '解析并生成逐页预览'}
      </button>
      {preview.error ? <p className="error">{preview.error.message}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      {assignments.map((assignment) => (
        <div className="narration-import-assignment" key={assignment.page_id}>
          <strong>
            第 {assignment.page_order} 页 · {assignment.page_title ?? '未命名页面'}
          </strong>
          <span className="muted">{labels[assignment.method]}</span>
          {assignment.warning ? <p className="error">{assignment.warning}</p> : null}
          <label>
            第 {assignment.page_order} 页旁白正文
            <textarea
              rows={6}
              value={assignment.text}
              onChange={(event) => changeText(assignment.page_id, event.target.value)}
            />
          </label>
        </div>
      ))}
      {assignments.length ? (
        <button className="primary" disabled={commit.isPending} onClick={writeDrafts}>
          {commit.isPending ? '正在写入…' : `写入 ${assignments.length} 页草稿`}
        </button>
      ) : null}
      {commit.error ? <p className="error">{commit.error.message}</p> : null}
    </section>
  );
}
