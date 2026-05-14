import { FolderPlus, Search, Upload } from "lucide-react";
import { activateVideo, createProject, getProject, listProjects, uploadVideo, uploadVideoFolder } from "../api/project";
import { useProjectStore } from "../store/projectStore";
import { useAnnotationStore } from "../store/annotationStore";
import type { ProjectInfo } from "../types/project";
import { useEffect, useMemo, useState } from "react";

function normalizeProject(data: any) {
  const videos = (data.videos ?? []).map((video: any) => ({
    videoId: video.video_id,
    name: video.name ?? "video",
    relativePath: video.relative_path,
    fps: video.fps ?? 0,
    width: video.width ?? 0,
    height: video.height ?? 0,
    frameCount: video.frame_count ?? 0,
    duration: video.duration ?? 0
  }));
  return {
    projectId: data.project_id,
    name: data.name ?? "Untitled",
    videos,
    activeVideoId: data.active_video_id ?? videos[0]?.videoId,
    paths: data.paths ?? {},
    fps: data.fps ?? 0,
    width: data.width ?? 0,
    height: data.height ?? 0,
    frameCount: data.frame_count ?? 0,
    duration: data.duration ?? 0
  };
}

export default function ProjectPanel() {
  const { project, setProject, setObjects } = useProjectStore();
  const { setAnnotatedFrames, setFrameIndex } = useAnnotationStore();
  const [projects, setProjects] = useState<Array<{ project_id: string; name: string }>>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newProjectName, setNewProjectName] = useState("demo");
  const [projectRoot, setProjectRoot] = useState(() => localStorage.getItem("projectRoot") ?? "");
  const [projectFolder, setProjectFolder] = useState("demo");
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
    listProjects().then((data) => setProjects(data.projects)).catch(() => setProjects([]));
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

  function applyProjectPayload(data: any) {
    setProject(normalizeProject(data.project));
    setObjects(Object.values(data.annotations?.objects ?? {}).map((obj: any) => ({
      objectId: obj.object_id,
      trackId: obj.track_id,
      category: obj.category,
      color: obj.color,
      visible: obj.visible,
      locked: obj.locked,
      createdFrame: obj.created_frame
    })));
    setAnnotatedFrames(Object.keys(data.annotations?.frames ?? {}).map(Number));
    setFrameIndex(0);
  }

  async function onCreate() {
    const name = newProjectName.trim() || "demo";
    const root = projectRoot.trim();
    const folder = projectFolder.trim() || safeFolderName(name);
    const projectDir = root ? joinPath(root, folder) : undefined;
    setCreateMessage("Creating project...");
    try {
      const created = await createProject(name, projectDir);
      if (root) localStorage.setItem("projectRoot", root);
      setProject(normalizeProject(created));
      setObjects([]);
      setAnnotatedFrames([]);
      setProjects((current) => [{ project_id: created.project_id, name: created.name }, ...current]);
      setShowCreate(false);
      setCreateMessage("");
    } catch (error) {
      setCreateMessage(error instanceof Error ? error.message : "Failed to create project.");
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
      <button className="command" onClick={() => setShowCreate((value) => !value)} title="Create project">
        <FolderPlus size={18} /> New
      </button>
      {showCreate && (
        <div className="create-project-panel">
          <label>
            <span>Name</span>
            <input
              className="text-input"
              value={newProjectName}
              onChange={(event) => {
                setNewProjectName(event.target.value);
                setProjectFolder(safeFolderName(event.target.value || "demo"));
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
          <div className="path-preview" title={projectRoot ? joinPath(projectRoot, projectFolder || safeFolderName(newProjectName || "demo")) : "Default projects folder"}>
            {projectRoot ? joinPath(projectRoot, projectFolder || safeFolderName(newProjectName || "demo")) : "Default projects folder"}
          </div>
          <div className="create-actions">
            <button className="primary" onClick={onCreate}>Create</button>
            <button className="command" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
          {createMessage && <span className="status-line">{createMessage}</span>}
        </div>
      )}
      <select className="text-input" value={project?.projectId ?? ""} onChange={(e) => openProject(e.target.value)}>
        <option value="">Open project</option>
        {projects.map((item) => <option value={item.project_id} key={item.project_id}>{item.name}</option>)}
      </select>
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
  return (value.trim() || "demo").replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "_").slice(0, 80);
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
