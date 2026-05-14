import { Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { getHealth } from "../api/health";
import { getProject } from "../api/project";
import { segmentFrame } from "../api/sam";
import { invalidateFrameAnnotations } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

export default function ToolPanel() {
  const { project, objects, selectedObjectId } = useProjectStore();
  const state = useAnnotationStore();
  const selectedObject = objects.find((obj) => obj.objectId === selectedObjectId);
  const [busy, setBusy] = useState<"segment" | null>(null);
  const [message, setMessage] = useState("");
  const boxRowRef = useRef<HTMLDivElement>(null);
  const pointRowRefs = useRef(new Map<number, HTMLDivElement>());
  const statusMessage = message || state.manualMessage;

  useEffect(() => {
    function onFocusPromptRow(event: Event) {
      const detail = (event as CustomEvent<{ type: "box" | "point"; index?: number }>).detail;
      if (!detail) return;
      const row = detail.type === "box" ? boxRowRef.current : pointRowRefs.current.get(detail.index ?? -1);
      row?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    window.addEventListener("focus-prompt-row", onFocusPromptRow);
    return () => window.removeEventListener("focus-prompt-row", onFocusPromptRow);
  }, []);

  async function onSegment() {
    if (!project) return;
    if (!state.sessionId && state.backend !== "mock") {
      setMessage("Start Session first when using a real SAM backend.");
      return;
    }
    if (!state.box && state.points.length === 0 && !state.textPrompt.trim()) {
      setMessage("Add a box, point, or text prompt before segmenting.");
      return;
    }
    setBusy("segment");
    setMessage("Segmenting current frame...");
    try {
      const prompt = activePromptPayload(state, selectedObjectId, selectedObject?.category);
      let resultObjectId: number | undefined;
      const sessionObjectIds: number[] = [];
      const response = await segmentFrame(project.projectId, {
        session_id: state.sessionId,
        frame_index: state.frameIndex,
        object_id: prompt.objectId,
        category: prompt.category,
        box: prompt.box,
        points: prompt.points,
        text: prompt.text
      }, project.activeVideoId);
      if (Object.keys(response.objects ?? {}).length === 0) {
        throw new Error("SAM returned no masks for the prompt.");
      }
      const responseObjectIds = Object.keys(response.objects ?? {}).map(Number);
      sessionObjectIds.push(...responseObjectIds);
      resultObjectId = responseObjectIds[0];
      const fresh = await getProject(project.projectId, project.activeVideoId);
      const projectStore = useProjectStore.getState();
      projectStore.setObjects(Object.values(fresh.annotations.objects).map((obj: any) => ({
        objectId: obj.object_id,
        trackId: obj.track_id,
        category: obj.category,
        color: obj.color,
        visible: obj.visible,
        locked: obj.locked,
        createdFrame: obj.created_frame
      })));
      if (resultObjectId !== undefined) {
        projectStore.setSelectedObjectId(resultObjectId);
      }
      invalidateFrameAnnotations(project.projectId, state.frameIndex, project.activeVideoId);
      state.setAnnotatedFrames(Object.keys(fresh.annotations.frames).map(Number));
      state.addSessionObjectIds(sessionObjectIds);
      state.clearPrompts();
      state.refreshOverlay();
      const health = await getHealth();
      state.setBackend(health.sam_backend);
      setMessage("Segmentation saved.");
    } catch (error) {
      const health = await getHealth().catch(() => null);
      if (health) state.setBackend(health.sam_backend);
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel tool-panel">
      <div className="panel-title">Tools</div>
      <div className="prompt-list">
        <div className="prompt-list-title">
          <span>Current Frame Prompts</span>
          {(state.box || state.points.length > 0 || state.textPrompt) && (
            <button title="Clear all prompts" onClick={() => state.clearPrompts()}><Trash2 size={15} /></button>
          )}
        </div>
        <div className="prompt-scroll-list">
          {state.box && (
            <div
              ref={boxRowRef}
              className={`prompt-row ${state.selectedPrompt?.type === "box" ? "selected" : ""}`}
              onClick={() => {
                state.selectPrompt({ type: "box" });
                focusPrompt((state.box![0] + state.box![2]) / 2, (state.box![1] + state.box![3]) / 2);
              }}
            >
              <span>Box [{state.box.map((value) => Math.round(value)).join(", ")}]</span>
              <button title="Delete box prompt" onClick={(event) => { event.stopPropagation(); state.clearBox(); }}><X size={15} /></button>
            </div>
          )}
          {state.points.map((point, index) => (
            <div
              ref={(node) => {
                if (node) pointRowRefs.current.set(index, node);
                else pointRowRefs.current.delete(index);
              }}
              className={`prompt-row ${state.selectedPrompt?.type === "point" && state.selectedPrompt.index === index ? "selected" : ""}`}
              key={`${point.x}-${point.y}-${index}`}
              onClick={() => {
                state.selectPrompt({ type: "point", index });
                focusPrompt(point.x, point.y);
              }}
            >
              <span>{point.label === 1 ? "Positive" : "Negative"} point [{Math.round(point.x)}, {Math.round(point.y)}]</span>
              <button title="Delete point prompt" onClick={(event) => { event.stopPropagation(); state.removePoint(index); }}><X size={15} /></button>
            </div>
          ))}
          {state.textPrompt && (
            <div className="prompt-row">
              <span>Text "{state.textPrompt}"</span>
              <button title="Delete text prompt" onClick={(event) => { event.stopPropagation(); state.setTextPrompt(""); }}><X size={15} /></button>
            </div>
          )}
          {!state.box && state.points.length === 0 && !state.textPrompt && <span className="empty-prompts">No pending prompts</span>}
        </div>
      </div>
      <button className="primary" disabled={!project || busy !== null} onClick={onSegment}><Sparkles size={18} /> {busy === "segment" ? "Segmenting..." : "Segment Frame"}</button>
      {statusMessage && <span className="status-line">{statusMessage}</span>}
    </section>
  );
}

function activePromptPayload(state: ReturnType<typeof useAnnotationStore.getState>, objectId?: number, category?: string) {
  if (state.selectedPrompt?.type === "box" && state.box) {
    return { objectId, category, box: state.box, points: [], text: state.textPrompt.trim() || undefined };
  }
  if (state.selectedPrompt?.type === "point" && state.points.length > 0) {
    return { objectId, category, box: undefined, points: state.points, text: undefined };
  }
  if (state.points.length > 0) {
    return { objectId, category, box: undefined, points: state.points, text: undefined };
  }
  if (state.box) {
    return { objectId, category, box: state.box, points: [], text: state.textPrompt.trim() || undefined };
  }
  return { objectId, category, box: undefined, points: [], text: state.textPrompt.trim() || undefined };
}

function focusPrompt(x: number, y: number) {
  window.dispatchEvent(new CustomEvent("focus-video-prompt", { detail: { x, y } }));
}

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Request failed.";
}
