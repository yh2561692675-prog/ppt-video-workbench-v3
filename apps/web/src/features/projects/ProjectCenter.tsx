import { useMutation, useQuery } from '@tanstack/react-query';
import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api } from '../../api/client';
import { StoragePanel } from './storage/StoragePanel';

export function ProjectCenter() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects });
  const disk = useQuery({ queryKey: ['disk'], queryFn: api.disk });
  const createProject = useMutation({
    mutationFn: api.createProject,
    onSuccess: (project) => {
      setName('');
      navigate(`/projects/${project.id}/step/${project.current_step}`);
    },
  });

  useEffect(() => {
    function warnAboutUnsavedName(event: BeforeUnloadEvent) {
      if (!name.trim()) return;
      event.preventDefault();
      event.returnValue = '';
    }

    window.addEventListener('beforeunload', warnAboutUnsavedName);
    return () => window.removeEventListener('beforeunload', warnAboutUnsavedName);
  }, [name]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) createProject.mutate(name.trim());
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <div className="eyebrow">PPT VIDEO WORKBENCH</div>
          <h1>项目中心</h1>
        </div>
        <div className="status-row">
          <Link className="secondary settings-link" to="/diagnostics">
            一键健康检查
          </Link>
          <Link className="secondary settings-link" to="/settings/llm">
            模型接口设置
          </Link>
          <Link className="secondary settings-link" to="/settings/heygen">
            HeyGen 声音设置
          </Link>
          <span className="muted">
            {disk.data ? `可用磁盘 ${formatBytes(disk.data.free)}` : '磁盘检测中'}
          </span>
        </div>
      </header>

      <section className="panel">
        <h2>新建视频项目</h2>
        <form className="create-form" onSubmit={submit}>
          <label>
            项目名称
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <button
            className="primary"
            type="submit"
            disabled={!name.trim() || createProject.isPending}
          >
            创建项目
          </button>
        </form>
        {createProject.error ? <p className="error">{createProject.error.message}</p> : null}
      </section>

      <section className="panel">
        <h2>最近项目</h2>
        <div className="project-list">
          {projects.data?.map((project) => (
            <div className="project-card" key={project.id}>
              <button
                className="project-open"
                onClick={() => navigate(`/projects/${project.id}/step/${project.current_step}`)}
              >
                <span>{project.name}</span>
                <span className="muted">第 {project.current_step} 步</span>
              </button>
              <StoragePanel projectId={project.id} />
            </div>
          ))}
          {projects.data?.length === 0 ? <p className="muted">还没有项目，请先创建一个。</p> : null}
        </div>
      </section>
    </main>
  );
}

function formatBytes(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}
