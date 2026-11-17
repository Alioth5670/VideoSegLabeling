import { isCurrentProject } from "../utils/project";
import { Repeat, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getProject } from "../api/project";
import ExportPanel from "./ExportPanel";
import { cancelPropagation, propagate } from "../api/sam";
import { invalidateFrameAnnotations } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

interface PropagationRun {
  projectId: string;
  videoId?: string;
  sessionId: string;
  label: string;
  controller: AbortController;
}

export default function PromptPanel() {
  const { project } = useProjectStore();
  const state = useAnnotationStore();
  const [direction, setDirection] = useState<"forward" | "backward" | "bidirectional">("forward");
  const [startFrame, setStartFrame] = useState(0);
  const [endFrame, setEndFrame] = useState(0);
  const [propagating, setPropagating] = useState(false);
  const [propagationProgress, setPropagationProgress] = useState<{ frameIndex: number; completed: number; total: number } | null>(null);
  const [message, setMessage] = useState("");
  const activeRunRef = useRef<PropagationRun | null>(null);
  const [activeRun, setActiveRun] = useState<PropagationRun | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    if (!project) return;
    setStartFrame(state.frameIndex);
    setEndFrame(project.frameCount > 0 ? project.frameCount - 1 : 0);
  }, [project?.projectId, project?.activeVideoId, project?.frameCount, state.frameIndex]);

  useEffect(() => () => {
    const run = activeRunRef.current;
    if (run) {
      void cancelPropagation(run.projectId, run.sessionId, run.videoId).catch(() => undefined);
      run.controller.abort();
    }
  }, []);

  async function onPropagate() {
    if (!project || !state.sessionId || state.sessionObjectIds.length === 0 || activeRunRef.current) return;
    const start = direction === "backward" ? Math.max(startFrame, endFrame) : Math.min(startFrame, endFrame);
    const end = direction === "backward" ? Math.min(startFrame, endFrame) : Math.max(startFrame, endFrame);
    const video = project.videos.find(item => item.videoId === project.activeVideoId);
    const run: PropagationRun = { projectId: project.projectId, videoId: project.activeVideoId,
      sessionId: state.sessionId, label: video?.name ?? project.name, controller: new AbortController() };
    activeRunRef.current = run;
    setActiveRun(run);
    const totalFrames = Math.abs(end - start) + 1;
    const completedFrames = new Set<number>();
    setPropagating(true);
    setStopping(false);
    setPropagationProgress({ frameIndex: start, completed: 0, total: totalFrames });
    setMessage("Propagating...");
    try {
      const result = await propagate(run.projectId, {
        session_id: run.sessionId, object_ids: [...state.sessionObjectIds],
        start_frame: start, end_frame: end, direction, mode: "auto"
      }, run.videoId, {
        signal: run.controller.signal,
        onFrame: (frame) => {
          if (activeRunRef.current !== run) return;
          const frameIndex = Number(frame.frame_index);
          completedFrames.add(frameIndex);
          setPropagationProgress({ frameIndex, completed: Math.min(completedFrames.size, totalFrames), total: totalFrames });
          invalidateFrameAnnotations(run.projectId, frameIndex, run.videoId);
          if (isCurrentProject(run.projectId, run.videoId)) {
            const annotationState = useAnnotationStore.getState();
            annotationState.addAnnotatedFrame(frameIndex);
            if (annotationState.frameIndex === frameIndex) annotationState.refreshOverlay();
          }
        }
      });
      if (isCurrentProject(run.projectId, run.videoId)) {
        const fresh = await getProject(run.projectId, run.videoId);
        if (isCurrentProject(run.projectId, run.videoId)) {
          state.setAnnotatedFrames(fresh.annotations.annotated_frames ?? Object.keys(fresh.annotations.frames ?? {}).map(Number));
          state.refreshOverlay();
        }
      }
      setMessage(result.cancelled ? "Propagation stopped." : "Propagation finished.");
    } catch (error) {
      if (isAbortError(error)) {
        if (isCurrentProject(run.projectId, run.videoId)) {
          const fresh = await getProject(run.projectId, run.videoId).catch(() => null);
          if (fresh && isCurrentProject(run.projectId, run.videoId)) {
            state.setAnnotatedFrames(fresh.annotations.annotated_frames ?? Object.keys(fresh.annotations.frames ?? {}).map(Number));
            state.refreshOverlay();
          }
        }
        setMessage("Propagation stopped.");
      } else {
        setMessage(error instanceof Error ? error.message : "Propagation failed.");
      }
    } finally {
      if (activeRunRef.current === run) {
        activeRunRef.current = null;
        setActiveRun(null);
        setPropagating(false);
        setStopping(false);
        setPropagationProgress(null);
      }
    }
  }

  async function onCancelPropagation() {
    const run = activeRunRef.current;
    if (!run || stopping) return;
    setStopping(true);
    setMessage("Stopping propagation...");
    try {
      const response = await cancelPropagation(run.projectId, run.sessionId, run.videoId);
      if (!response.cancelled) run.controller.abort();
    } catch {
      // Disconnecting also cancels the server stream when the stop request fails.
      run.controller.abort();
    }
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
        <button className="command danger" disabled={stopping} onClick={onCancelPropagation}>
          <Square size={18} /> {stopping ? "Stopping..." : "Stop Propagation"}
        </button>
      ) : (
        <button className="command" disabled={!project || !state.sessionId || state.sessionObjectIds.length === 0} onClick={onPropagate}>
          <Repeat size={18} /> Propagate {state.sessionObjectIds.length > 0 ? `(${state.sessionObjectIds.length})` : ""}
        </button>
      )}
      {activeRun && <span className="status-line" title={activeRun.label}>正在传播：{activeRun.label}</span>}
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
      <ExportPanel />
    </section>
  );
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
