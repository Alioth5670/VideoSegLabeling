import { Download, Repeat, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getProject } from "../api/project";
import { exportProject } from "../api/export";
import { cancelPropagation, propagate } from "../api/sam";
import { invalidateFrameAnnotations } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

export default function PromptPanel() {
  const { project } = useProjectStore();
  const state = useAnnotationStore();
  const [direction, setDirection] = useState<"forward" | "backward" | "bidirectional">("forward");
  const [startFrame, setStartFrame] = useState(0);
  const [endFrame, setEndFrame] = useState(0);
  const [propagating, setPropagating] = useState(false);
  const [propagationProgress, setPropagationProgress] = useState<{ frameIndex: number; completed: number; total: number } | null>(null);
  const [message, setMessage] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!project) return;
    setStartFrame(state.frameIndex);
    setEndFrame(project.frameCount > 0 ? project.frameCount - 1 : 0);
  }, [project?.projectId, project?.activeVideoId, project?.frameCount, state.frameIndex]);

  async function onPropagate() {
    if (!project || !state.sessionId || state.sessionObjectIds.length === 0 || propagating) return;
    const start = direction === "backward" ? Math.max(startFrame, endFrame) : Math.min(startFrame, endFrame);
    const end = direction === "backward" ? Math.min(startFrame, endFrame) : Math.max(startFrame, endFrame);
    const controller = new AbortController();
    abortRef.current = controller;
    const totalFrames = Math.abs(end - start) + 1;
    setPropagating(true);
    setPropagationProgress({ frameIndex: start, completed: 0, total: totalFrames });
    setMessage("Propagating...");
    try {
      const result = await propagate(project.projectId, {
        session_id: state.sessionId,
        object_ids: state.sessionObjectIds,
        start_frame: start,
        end_frame: end,
        direction,
        mode: "auto"
      }, project.activeVideoId, {
        signal: controller.signal,
        onFrame: (frame) => {
          const frameIndex = Number(frame.frame_index);
          const annotationState = useAnnotationStore.getState();
          invalidateFrameAnnotations(project.projectId, frameIndex, project.activeVideoId);
          annotationState.addAnnotatedFrame(frameIndex);
          setPropagationProgress((current) => ({
            frameIndex,
            completed: Math.min((current?.completed ?? 0) + 1, current?.total ?? totalFrames),
            total: current?.total ?? totalFrames
          }));
          if (annotationState.frameIndex === frameIndex) {
            annotationState.refreshOverlay();
          }
        }
      });
      for (const frame of result.frames ?? []) {
        invalidateFrameAnnotations(project.projectId, Number(frame.frame_index), project.activeVideoId);
      }
      const fresh = await getProject(project.projectId, project.activeVideoId);
      state.setAnnotatedFrames(Object.keys(fresh.annotations.frames).map(Number));
      state.refreshOverlay();
      setMessage(result.cancelled ? "Propagation stopped." : "Propagation finished.");
    } catch (error) {
      if (isAbortError(error)) {
        const fresh = await getProject(project.projectId, project.activeVideoId).catch(() => null);
        if (fresh) {
          state.setAnnotatedFrames(Object.keys(fresh.annotations.frames).map(Number));
          state.refreshOverlay();
        }
        setMessage("Propagation stopped.");
      } else {
        setMessage(error instanceof Error ? error.message : "Propagation failed.");
      }
    } finally {
      abortRef.current = null;
      setPropagating(false);
      setPropagationProgress(null);
    }
  }

  async function onCancelPropagation() {
    if (!project || !state.sessionId) return;
    setMessage("Stopping propagation...");
    await cancelPropagation(project.projectId, state.sessionId, project.activeVideoId).catch(() => undefined);
    abortRef.current?.abort();
  }

  async function onExport(format: string) {
    if (!project) return;
    const result = await exportProject(project.projectId, format);
    window.open(result.download_url, "_blank");
  }

  return (
    <section className="panel">
      <div className="panel-title">Actions</div>
      <div className="field-row">
        <input className="text-input" type="number" min={0} max={project?.frameCount ? project.frameCount - 1 : 0} value={startFrame} onChange={(e) => setStartFrame(Number(e.target.value))} />
        <input className="text-input" type="number" min={0} max={project?.frameCount ? project.frameCount - 1 : 0} value={endFrame} onChange={(e) => setEndFrame(Number(e.target.value))} />
      </div>
      <select className="text-input" value={direction} onChange={(e) => setDirection(e.target.value as "forward" | "backward" | "bidirectional")}>
        <option value="forward">forward</option>
        <option value="backward">backward</option>
        <option value="bidirectional">bidirectional</option>
      </select>
      {propagating ? (
        <button className="command danger" disabled={!project || !state.sessionId} onClick={onCancelPropagation}>
          <Square size={18} /> Stop Propagation
        </button>
      ) : (
        <button className="command" disabled={!project || !state.sessionId || state.sessionObjectIds.length === 0} onClick={onPropagate}>
          <Repeat size={18} /> Propagate {state.sessionObjectIds.length > 0 ? `(${state.sessionObjectIds.length})` : ""}
        </button>
      )}
      {propagating && propagationProgress && (
        <div className="propagation-progress">
          <div className="propagation-progress-head">
            <span>Frame {propagationProgress.frameIndex}</span>
            <span>{propagationProgress.completed}/{propagationProgress.total}</span>
          </div>
          <progress value={propagationProgress.completed} max={propagationProgress.total} />
        </div>
      )}
      {message && <span className="status-line">{message}</span>}
      <span className="empty-prompts">
        {state.sessionId
          ? `${state.sessionObjectIds.length} current-session object${state.sessionObjectIds.length === 1 ? "" : "s"} can propagate`
          : "Start a SAM session, then segment objects before propagating"}
      </span>
      <div className={`export-select ${project ? "" : "disabled"}`}>
        <Download size={18} />
        <select
          disabled={!project}
          value=""
          onChange={(event) => {
            const format = event.target.value;
            if (!format) return;
            onExport(format);
          }}
        >
          <option value="">Export annotations</option>
          <option value="project_json">Project JSON</option>
          <option value="mask_png">Mask PNG</option>
          <option value="coco_video_json">COCO JSON</option>
          <option value="all_videos_zip">All Videos ZIP</option>
        </select>
      </div>
    </section>
  );
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
