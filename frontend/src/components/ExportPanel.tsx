import { Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { exportProject, getExportJob, type ExportJob } from "../api/export";
import { useProjectStore } from "../store/projectStore";

const terminal = (job: ExportJob) => ["completed", "failed", "cancelled"].includes(job.status);

function describeError(error: unknown): string {
  if (axios.isAxiosError(error) && typeof error.response?.data?.detail === "string") return error.response.data.detail;
  return error instanceof Error ? error.message : "导出失败，请重试";
}

export default function ExportPanel() {
  const project = useProjectStore(state => state.project);
  const key = project ? `export-job:${project.projectId}:${project.activeVideoId ?? "legacy"}` : undefined;
  const currentKey = useRef(key);
  currentKey.current = key;
  const [tracked, setTracked] = useState<{ key: string; id: string } | null>(null);
  const jobId = tracked?.key === key ? tracked?.id : null;
  const [job, setJob] = useState<ExportJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setJob(null);
    const saved = key ? localStorage.getItem(key) : null;
    setTracked(key && saved ? { key, id: saved } : null);
    setSubmitting(false);
    setError("");
  }, [key]);

  useEffect(() => {
    if (!project || !jobId) return;
    const projectId = project.projectId;
    const controller = new AbortController();
    let stopped = false;
    let timer: number | undefined;
    async function poll() {
      try {
        const fresh = await getExportJob(projectId, jobId!, controller.signal);
        if (stopped) return;
        setJob(fresh);
        setError("");
        if (!terminal(fresh)) timer = window.setTimeout(poll, 750);
      } catch (failure) {
        if (stopped) return;
        setError(`进度查询失败：${describeError(failure)}`);
        if (axios.isAxiosError(failure) && failure.response?.status === 404) {
          if (key) localStorage.removeItem(key);
          setTracked(null);
          setJob(null);
        } else {
          timer = window.setTimeout(poll, 2000);
        }
      }
    }
    void poll();
    return () => { stopped = true; controller.abort(); window.clearTimeout(timer); };
  }, [project?.projectId, jobId, key]);

  async function submit(format: string) {
    if (!project || !key || submitting) return;
    const submittedKey = key;
    setSubmitting(true);
    setError("");
    try {
      const created = await exportProject(project.projectId, format, project.activeVideoId);
      localStorage.setItem(submittedKey, created.job_id);
      if (currentKey.current !== submittedKey) return;
      setJob(created);
      setTracked({ key: submittedKey, id: created.job_id });
    } catch (failure) {
      if (currentKey.current === submittedKey) setError(describeError(failure));
    } finally {
      if (currentKey.current === submittedKey) setSubmitting(false);
    }
  }

  const active = submitting || Boolean(jobId && (!job || !terminal(job)));
  return <div className="export-panel">
    <div className={`export-select ${project ? "" : "disabled"}`}>
      <Download size={18} />
      <select disabled={!project || active} value="" onChange={event => { if (event.target.value) void submit(event.target.value); }}>
        <option value="">{active ? "导出处理中…" : "Export annotations"}</option>
        <option value="project_json">Project JSON</option>
        <option value="mask_png">Mask PNG</option>
        <option value="coco_video_json">COCO JSON</option>
        <option value="all_videos_zip">All Videos ZIP</option>
      </select>
    </div>
    {submitting && <span className="status-line">正在提交后台任务…</span>}
    {job && <div className="propagation-progress" aria-live="polite">
      <div className="propagation-progress-head"><span>{job.stage}</span><span>{Math.floor(job.progress)}%</span></div>
      <progress aria-label="导出进度" value={job.progress} max={100} />
      {job.status === "queued" && <span className="status-line">任务已排队，可以继续标注。</span>}
      {job.status === "completed" && job.download_url && <a className="command" href={job.download_url} download><Download size={16} />下载导出结果</a>}
      {job.error && <span className="status-line" role="alert">{job.error}</span>}
    </div>}
    {error && <span className="status-line" role="alert">{error}</span>}
  </div>;
}
