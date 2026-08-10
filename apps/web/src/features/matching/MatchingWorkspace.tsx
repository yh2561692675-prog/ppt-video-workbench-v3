import { useState } from 'react';

import { api, PageMatch } from '../../api/client';

interface Props {
  projectId: string;
  initialMatches: PageMatch[];
}

const CONFLICT_LABELS: Record<string, string> = {
  empty_page: '空白页',
  duplicate_page_content: '页面内容重复',
  title_conflict: '标题矛盾',
};

export function MatchingWorkspace({ projectId, initialMatches }: Props) {
  const [matches, setMatches] = useState(initialMatches);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [busyPage, setBusyPage] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);

  async function parseMaterials() {
    setParsing(true);
    try {
      const result = await api.parseMaterials(projectId);
      setMatches(result.matches);
      setMessage(result.cached ? '已复用上次解析结果' : '材料解析完成');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '材料解析失败');
    } finally {
      setParsing(false);
    }
  }

  async function save(match: PageMatch) {
    const outlineRef = choices[match.page_id] ?? match.selected_outline_ref;
    const reason = reasons[match.page_id]?.trim() ?? '';
    if (!outlineRef || !reason) {
      setMessage('请选择大纲候选并填写改绑原因');
      return;
    }
    setBusyPage(match.page_id);
    try {
      const changed = await api.changeMatch(projectId, match.page_id, outlineRef, reason);
      setMatches((current) =>
        current.map((item) => (item.page_id === changed.page_id ? changed : item)),
      );
      setMessage('人工匹配已保存');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '人工匹配保存失败');
    } finally {
      setBusyPage(null);
    }
  }

  return (
    <section className="matching-workspace">
      {message && <p role="status">{message}</p>}
      {!matches.length && (
        <div className="empty-matching">
          <p className="muted">导入材料后，系统将逐页提取文字并与 Word 大纲进行确定性匹配。</p>
          <button className="primary" disabled={parsing} onClick={() => void parseMaterials()}>
            {parsing ? '正在解析…' : '开始解析与匹配'}
          </button>
        </div>
      )}
      {matches.map((match) => (
        <article className="match-card" key={match.page_id}>
          <div className="match-evidence">
            <div className="eyebrow">页面 {match.page_order}</div>
            <h3>{match.page_title ?? '无页面标题'}</h3>
            <pre>{match.page_text || '本页没有可提取文字'}</pre>
            <div className="conflicts">
              {match.conflicts.map((conflict) => (
                <span key={conflict}>{CONFLICT_LABELS[conflict] ?? conflict}</span>
              ))}
            </div>
          </div>
          <div className="candidate-panel">
            <label>
              大纲候选
              <select
                aria-label="大纲候选"
                value={choices[match.page_id] ?? match.selected_outline_ref ?? ''}
                onChange={(event) =>
                  setChoices((current) => ({ ...current, [match.page_id]: event.target.value }))
                }
              >
                {match.candidates.map((candidate) => (
                  <option key={candidate.outline_ref} value={candidate.outline_ref}>
                    {candidate.outline_title} · {Math.round(candidate.score * 100)}%
                  </option>
                ))}
              </select>
            </label>
            <ul>
              {match.candidates.map((candidate) => (
                <li key={candidate.outline_ref}>
                  <strong>{candidate.outline_title}</strong>
                  <span>{Math.round(candidate.score * 100)}%</span>
                </li>
              ))}
            </ul>
            <label>
              改绑原因
              <input
                aria-label="改绑原因"
                value={reasons[match.page_id] ?? ''}
                onChange={(event) =>
                  setReasons((current) => ({ ...current, [match.page_id]: event.target.value }))
                }
              />
            </label>
            <button
              className="primary"
              disabled={busyPage === match.page_id}
              onClick={() => void save(match)}
            >
              保存人工匹配
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
