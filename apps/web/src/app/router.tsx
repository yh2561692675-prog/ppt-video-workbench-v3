import { Navigate, Route, Routes } from 'react-router-dom';

import { ProjectCenter } from '../features/projects/ProjectCenter';
import { DiagnosticCenter } from '../features/diagnostics/DiagnosticCenter';
import { WorkflowShell } from '../features/workflow/WorkflowShell';
import { LlmSettings } from '../features/settings/llm/LlmSettings';
import { HeyGenSettings } from '../features/settings/heygen/HeyGenSettings';
import { UpdatePanel } from '../features/settings/update/UpdatePanel';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<ProjectCenter />} />
      <Route path="/diagnostics" element={<DiagnosticCenter />} />
      <Route path="/projects/:projectId/step/:step" element={<WorkflowShell />} />
      <Route
        path="/settings/llm"
        element={
          <main className="page">
            <h1>模型接口设置</h1>
            <LlmSettings />
          </main>
        }
      />
      <Route
        path="/settings/heygen"
        element={
          <main className="page">
            <h1>HeyGen 声音设置</h1>
            <HeyGenSettings />
          </main>
        }
      />
      <Route
        path="/settings/update"
        element={
          <main className="page">
            <h1>更新与恢复</h1>
            <UpdatePanel />
          </main>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
