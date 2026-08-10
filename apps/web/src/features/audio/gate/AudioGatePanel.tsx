import { AudioGateResult } from '../../../api/client';

interface AudioGatePanelProps {
  gate: AudioGateResult | null;
  pageLabels?: Record<string, string>;
}

export function AudioGatePanel({ gate, pageLabels = {} }: AudioGatePanelProps) {
  if (gate === null) return <p className="muted">正在检查音频门禁……</p>;
  if (gate.allowed) return <p className="success">音频门禁已通过，可进入字幕步骤。</p>;
  return (
    <section className="audio-gate" aria-label="音频门禁">
      <h3>音频门禁未通过</h3>
      <ul>
        {gate.reasons.map((reason) => (
          <li key={`${reason.code}-${reason.page_id}`}>
            <strong>{pageLabels[reason.page_id] ?? `页面 ${reason.page_id}`}：</strong>
            {reason.message}
            <small>{reason.action}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}
