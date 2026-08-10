import { ChangeEvent, DragEvent, useMemo, useState } from 'react';

import { api, SourceFile } from '../../api/client';

interface Props {
  projectId: string;
  initialSources: SourceFile[];
}

export function MaterialImport({ projectId, initialSources }: Props) {
  const [sources, setSources] = useState(initialSources);
  const [pending, setPending] = useState<File[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const images = useMemo(
    () =>
      sources
        .filter((source) => source.kind === 'image')
        .sort((a, b) => (a.image_order ?? 0) - (b.image_order ?? 0)),
    [sources],
  );

  function choose(event: ChangeEvent<HTMLInputElement>) {
    setPending(Array.from(event.target.files ?? []));
    setMessage('');
  }

  async function upload() {
    if (!pending.length) return;
    const existingNames = new Set(sources.map((source) => source.original_name));
    const duplicates = pending.filter((file) => existingNames.has(file.name));
    if (duplicates.length && !window.confirm('存在同名材料，将保留两个版本并自动改名。是否继续？'))
      return;
    setBusy(true);
    setMessage(`正在导入 0/${pending.length}`);
    try {
      const imported = await api.importSources(projectId, pending);
      setSources((current) => [...current, ...imported]);
      setPending([]);
      setMessage(`已导入 ${imported.length} 个文件`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '导入失败');
    } finally {
      setBusy(false);
    }
  }

  async function saveOrder(ordered: SourceFile[]) {
    setBusy(true);
    try {
      const saved = await api.reorderImages(
        projectId,
        ordered.map((source) => source.id),
      );
      const byId = new Map(saved.map((source) => [source.id, source]));
      setSources((current) => current.map((source) => byId.get(source.id) ?? source));
      setMessage('图片顺序已保存');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '顺序保存失败');
    } finally {
      setBusy(false);
    }
  }

  function move(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= images.length) return;
    const ordered = [...images];
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    void saveOrder(ordered);
  }

  function drop(event: DragEvent<HTMLLIElement>, targetId: string) {
    event.preventDefault();
    if (!draggedId || draggedId === targetId) return;
    const ordered = [...images];
    const from = ordered.findIndex((source) => source.id === draggedId);
    const to = ordered.findIndex((source) => source.id === targetId);
    const [moved] = ordered.splice(from, 1);
    ordered.splice(to, 0, moved);
    setDraggedId(null);
    void saveOrder(ordered);
  }

  return (
    <section className="material-import">
      <div className="drop-zone" onDragOver={(event) => event.preventDefault()}>
        <label htmlFor="material-files">选择材料文件</label>
        <input
          id="material-files"
          type="file"
          multiple
          accept=".docx,.pptx,.pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
          onChange={choose}
        />
        <p className="muted">支持 Word、PPTX、PDF 与多张图片；图片默认按自然文件名排序。</p>
        <button
          className="primary"
          disabled={busy || !pending.length}
          onClick={() => void upload()}
        >
          {busy ? '处理中…' : '开始导入'}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
      <ul className="source-list">
        {images.map((source, index) => (
          <li
            key={source.id}
            draggable
            onDragStart={() => setDraggedId(source.id)}
            onDrop={(event) => drop(event, source.id)}
          >
            <span>{source.original_name}</span>
            <div>
              <button
                className="secondary"
                aria-label={`上移 ${source.original_name}`}
                disabled={busy || index === 0}
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                className="secondary"
                aria-label={`下移 ${source.original_name}`}
                disabled={busy || index === images.length - 1}
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
