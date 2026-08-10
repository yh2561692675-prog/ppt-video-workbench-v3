import { PageExtraction, PageMatch, NarrationPage } from '../../../api/client';
import { NarrationEditor } from './NarrationEditor';
import { ConfirmationPanel } from './ConfirmationPanel';

interface Props {
  projectId: string;
  pages: NarrationPage[];
  extractions: PageExtraction[];
  matches: PageMatch[];
}

export function NarrationWorkspace({ projectId, pages, extractions, matches }: Props) {
  if (!pages.length) return <p className="muted">请先完成材料解析与页面匹配。</p>;
  const conflictsByPage = Object.fromEntries(
    matches.map((match) => [match.page_id, match.conflicts]),
  );
  return (
    <div className="narration-workspace">
      <ConfirmationPanel projectId={projectId} pages={pages} conflictsByPage={conflictsByPage} />
      {[...pages]
        .sort((left, right) => left.order - right.order)
        .map((page) => {
          const extraction = extractions.find((item) => item.id === page.id);
          const match = matches.find((item) => item.page_id === page.id);
          return (
            <div id={`narration-page-${page.id}`} key={page.id}>
              <NarrationEditor
                projectId={projectId}
                page={page}
                pageText={extraction?.text ?? match?.page_text ?? ''}
                outlineText={
                  match?.candidates.find(
                    (candidate) => candidate.outline_ref === match.selected_outline_ref,
                  )?.outline_text ?? ''
                }
              />
            </div>
          );
        })}
    </div>
  );
}
