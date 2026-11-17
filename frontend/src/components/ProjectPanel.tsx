import axios from "axios";
import { normalizeProject, applyProjectPayload, defaultProjectName } from "../utils/project";
import { FolderPlus, Search, Upload } from "lucide-react";
import { activateVideo, createProject, getProject, listProjects, uploadVideo, uploadVideoFolder, type ProjectSummary } from "../api/project";
import { useProjectStore } from "../store/projectStore";
import { useAnnotationStore } from "../store/annotationStore";
import type { ProjectInfo } from "../types/project";
import { useEffect, useMemo, useState } from "react";


export default function ProjectPanel() {
  const { project, setProject, setObjects } = useProjectStore();
  const { setAnnotatedFrames, setFrameIndex } = useAnnotationStore();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [projectOffset, setProjectOffset] = useState(0);
  const [projectTotal, setProjectTotal] = useState(0);
  const [projectRevision, setProjectRevision] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [newProjectName, setNewProjectName] = useState(defaultProjectName);
  const [projectRoot, setProjectRoot] = useState(() => localStorage.getItem("projectRoot") ?? "");
  const [projectFolder, setProjectFolder] = useState(() => safeFolderName(newProjectName));
  const [creating, setCreating] = useState(false);
  const [createMessage, setCreateMessage] = useState("");
  const [videoFilter, setVideoFilter] = useState("");
  const [uploadProgress, setUploadProgress] = useState<{ completed: number; total: number } | null>(null);

  const filteredVideos = useMemo(() => {
    const videos = project?.videos ?? [];
    const indexedVideos = videos.map((video, index) => ({ video, index }));
    const query = videoFilter.trim().toLowerCase();
    if (!query) return indexedVideos;
    return indexedVideos.filter(({ video }) => videoDisplayLabel(video).toLowerCase().includes(query));
  }, [project?.videos, videoFilter]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      listProjects(projectFilter, projectOffset).then(data => {
        if (active) { setProjects(data.projects); setProjectTotal(data.total); }
      }).catch(() => { if (active) setCreateMessage("项目列表加载失败"); });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [projectFilter, projectOffset, projectRevision]);

  useEffect(() => {
    const refresh = () => setProjectRevision(value => value + 1);
    window.addEventListener("projects-changed", refresh);
    return () => window.removeEventListener("projects-changed", refresh);
  }, []);

  async function openProject(projectId: string) {
    if (!projectId) return;
    const data = await getProject(projectId);
    applyProjectPayload(data);
  }

  async function openVideo(videoId: string) {
    if (!project || !videoId) return;
    const data = await activateVideo(project.projectId, videoId);
    applyProjectPayload(data);
  }


  async function onCreate() {
    if (creating) return;
    const name = newProjectName.trim();
    if (!name) { setCreateMessage("请输入项目名称"); return; }
    const root = projectRoot.trim();
    const folder = projectFolder.trim() || safeFolderName(name);
    const projectDir = root ? joinPath(root, folder) : undefined;
    setCreating(true);
    setCreateMessage("Creating project...");
    try {
      const created = await createProject(name, projectDir);
      if (root) localStorage.setItem("projectRoot", root);
      setProject(normalizeProject(created));
      setObjects([]);
      setAnnotatedFrames([]);
      setProjectOffset(0);
      setProjectFilter("");
      setProjectRevision(value => value + 1);
      setShowCreate(false);
      setCreateMessage("");
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setCreateMessage(typeof detail === "string" ? detail : error instanceof Error ? error.message : "Failed to create project.");
    } finally {
      setCreating(false);
    }
  }

  async function onUpload(file?: File) {
    if (!project || !file) return;
    const info = await uploadVideo(project.projectId, file);
    setProject(normalizeProject(info.project ?? { ...info, name: project.name }));
    setObjects([]);
    setFrameIndex(0);
    setAnnotatedFrames([]);
  }

  async function onUploadFolder(files?: FileList | null) {
    if (!project || !files?.length) return;
    const videoFiles: File[] = [];
    for (const file of Array.from(files)) {
      if (isVideoFile(file)) videoFiles.push(file);
    }
    if (videoFiles.length === 0) {
      setCreateMessage("No video files found in selected folder.");
      return;
    }
    setCreateMessage(`Uploading ${videoFiles.length} videos...`);
    setUploadProgress({ completed: 0, total: videoFiles.length });
    try {
      const data = await uploadVideoFolder(project.projectId, videoFiles, {
        onProgress: (completed, total) => setUploadProgress({ completed, total })
      });
      setProject(normalizeProject(data.project));
      setObjects([]);
      setFrameIndex(0);
      setAnnotatedFrames([]);
      setCreateMessage("");
      setUploadProgress(null);
    } catch (error) {
      setCreateMessage(error instanceof Error ? error.message : "Failed to upload folder.");
      setUploadProgress(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-title">Project</div>
      <button className="command" disabled={creating} onClick={() => {
        if (!showCreate) {
          const name = defaultProjectName();
          setNewProjectName(name);
          setProjectFolder(safeFolderName(name));
          setCreateMessage("");
        }
        setShowCreate(!showCreate);
      }} title="Create project">
        <FolderPlus size={18} /> New
      </button>
      {showCreate && (
        <div className="create-project-panel">
          <label>
            <span>Name</span>
            <input
              className="text-input"
              maxLength={120}
              value={newProjectName}
              onChange={(event) => {
                setNewProjectName(event.target.value);
                setProjectFolder(safeFolderName(event.target.value));
              }}
            />
          </label>
          <label>
            <span>Root Directory</span>
            <input
              className="text-input"
              placeholder="blank = default projects folder"
              value={projectRoot}
              onChange={(event) => setProjectRoot(event.target.value)}
            />
          </label>
          <label>
            <span>Folder</span>
            <input className="text-input" value={projectFolder} onChange={(event) => setProjectFolder(event.target.value)} />
          </label>
          <div className="path-preview" title={projectRoot ? joinPath(projectRoot, projectFolder || safeFolderName(newProjectName)) : "Default projects folder"}>
            {projectRoot ? joinPath(projectRoot, projectFolder || safeFolderName(newProjectName)) : "Default projects folder"}
          </div>
          <div className="create-actions">
            <button className="primary" disabled={creating || !newProjectName.trim()} onClick={onCreate}>{creating ? "Creating..." : "Create"}</button>
            <button className="command" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
          {createMessage && <span className="status-line">{createMessage}</span>}
        </div>
      )}
      <input className="text-input" placeholder="搜索我的项目" value={projectFilter} onChange={e => { setProjectFilter(e.target.value); setProjectOffset(0); }} />
      <select className="text-input" value={project?.projectId ?? ""} onChange={(e) => openProject(e.target.value)}>
        <option value="">Open project</option>
        {project && !projects.some(item => item.project_id === project.projectId) && <option value={project.projectId}>{project.name}</option>}
        {projects.map((item) => <option value={item.project_id} key={item.project_id} disabled={item.data_status === "missing"}>{item.name}{item.data_status === "missing" ? "（文件缺失）" : ""}</option>)}
      </select>
      <div className="project-pagination">
        <button className="command" disabled={projectOffset === 0} onClick={() => setProjectOffset(value => Math.max(0, value - 50))}>上一页</button>
        <span>{projectTotal} 个项目</span>
        <button className="command" disabled={projectOffset + 50 >= projectTotal} onClick={() => setProjectOffset(value => value + 50)}>下一页</button>
      </div>
      <div className="upload-actions">
        <label className={`command ${project && !uploadProgress ? "" : "disabled"}`} title="Upload video">
          <Upload size={18} /> Upload
          <input disabled={!project || Boolean(uploadProgress)} hidden type="file" accept="video/*" onChange={(e) => onUpload(e.target.files?.[0])} />
        </label>
        <label className={`command ${project && !uploadProgress ? "" : "disabled"}`} title="Upload folder">
          <Upload size={18} /> Folder
          <input
            disabled={!project || Boolean(uploadProgress)}
            hidden
            type="file"
            accept="video/*"
            multiple
            {...{ webkitdirectory: "", directory: "" }}
            onChange={(e) => onUploadFolder(e.target.files)}
          />
        </label>
      </div>
      {createMessage && !showCreate && <span className="status-line">{createMessage}</span>}
      {uploadProgress && (
        <div className="upload-progress">
          <div className="upload-progress-head">
            <span>Uploading</span>
            <span>{uploadProgress.completed}/{uploadProgress.total}</span>
          </div>
          <progress value={uploadProgress.completed} max={uploadProgress.total} />
        </div>
      )}
      {project && (
        <div className="meta project-meta">
          <strong>{project.name}</strong>
          {project.videos.length === 0 && <span>No videos uploaded</span>}
        </div>
      )}
      {project && project.videos.length > 0 && (
        <div className="video-picker">
          <div className="video-picker-title">
            <span>Videos</span>
            <span>{project.videos.length}</span>
          </div>
          {project.videos.length > 5 && (
            <label className="video-search">
              <Search size={15} />
              <input value={videoFilter} onChange={(event) => setVideoFilter(event.target.value)} placeholder="Search videos" />
            </label>
          )}
          <div className="video-list">
            {filteredVideos.map(({ video, index }) => {
              const active = video.videoId === project.activeVideoId;
              const label = videoDisplayLabel(video);
              return (
                <button
                  className={`video-item ${active ? "selected" : ""}`}
                  key={video.videoId}
                  onClick={() => video.videoId && openVideo(video.videoId)}
                  title={label}
                >
                  <span className="video-name-row">
                    <span className="video-index">#{index + 1}</span>
                    <span className="video-name">{video.name}</span>
                  </span>
                  <span className="video-path">{video.relativePath ?? video.videoId}</span>
                  <span className="video-meta">{video.frameCount} frames · {video.fps.toFixed(2)} fps</span>
                </button>
              );
            })}
            {filteredVideos.length === 0 && <span className="empty-prompts">No matching videos</span>}
          </div>
        </div>
      )}
      {project && (
        <details className="path-manager">
          <summary>Project Paths</summary>
          <PathRow label="Project Directory" value={project.paths.project_dir} />
          <PathRow label="Frames" value={project.paths.active_frames_dir} />
          <PathRow label="Masks" value={project.paths.active_masks_dir} />
          <PathRow label="Exports" value={project.paths.active_exports_dir} />
        </details>
      )}
    </section>
  );
}

function safeFolderName(value: string) {
  return (value.trim() || "project").replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "_").slice(0, 80);
}

function joinPath(root: string, folder: string) {
  const cleanedRoot = root.replace(/[\\/]+$/, "");
  const cleanedFolder = folder.replace(/^[\\/]+/, "");
  return `${cleanedRoot}/${cleanedFolder}`;
}

function isVideoFile(file: File) {
  const name = file.name.toLowerCase();
  return file.type.startsWith("video/") || /\.(avi|m4v|mkv|mov|mp4|mpeg|mpg|webm)$/.test(name);
}

function videoDisplayLabel(video: ProjectInfo["videos"][number]) {
  return [video.name, video.relativePath, video.videoId].filter(Boolean).join(" ");
}

function PathRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="path-row" title={value}>
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}
