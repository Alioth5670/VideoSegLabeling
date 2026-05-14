import { BoxSelect, CircleMinus, CirclePlus, MousePointer2, PencilLine, Play, RectangleHorizontal, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import axios from "axios";
import { getHealth } from "../api/health";
import { resetSession, startSession } from "../api/sam";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

export default function TopControls() {
  const { project } = useProjectStore();
  const state = useAnnotationStore();
  const [busy, setBusy] = useState<"session" | "reset" | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    getHealth()
      .then((health) => {
        state.setBackend(health.sam_backend);
        state.setSamDevice(health.sam_device);
        if (health.sam_fallback_error) setMessage(health.sam_fallback_error);
      })
      .catch(() => state.setBackend("unreachable"));
  }, []);

  async function onSession() {
    if (!project) return;
    setBusy("session");
    setMessage("Loading SAM session...");
    try {
      const session = await startSession(project.projectId, project.activeVideoId);
      state.setSession(session.session_id, session.backend);
      state.setSamDevice(session.device);
      setMessage(session.fallback_error ?? `Session ready: ${session.backend} on ${session.device}`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function onResetSession() {
    if (!project || !state.sessionId) return;
    const confirmed = window.confirm("Reset the current SAM session? Project objects and annotations will be kept, but tracked objects and session prompts will be cleared.");
    if (!confirmed) return;
    setBusy("reset");
    setMessage("Resetting SAM session...");
    try {
      await resetSession(project.projectId, state.sessionId, project.activeVideoId);
      state.resetSessionObjects();
      setMessage("Session reset. Existing annotations are kept; add prompts again to track objects.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <header className="top-controls">
      <div className="segmented top-prompt-tools">
        <button className={state.tool === "view" ? "active" : ""} onClick={() => state.setTool("view")} title="Edit annotations"><MousePointer2 size={18} /></button>
        <button className={state.tool === "box" ? "active" : ""} onClick={() => state.setTool("box")} title="Box prompt"><BoxSelect size={18} /></button>
        <button className={state.tool === "point-positive" ? "active" : ""} onClick={() => state.setTool("point-positive")} title="Positive point"><CirclePlus size={18} /></button>
        <button className={state.tool === "point-negative" ? "active" : ""} onClick={() => state.setTool("point-negative")} title="Negative point"><CircleMinus size={18} /></button>
        <button className={state.tool === "manual-bbox" ? "active" : ""} onClick={() => state.setTool("manual-bbox")} title="Manual bbox mask"><RectangleHorizontal size={18} /></button>
        <button className={state.tool === "manual-polygon" ? "active" : ""} onClick={() => state.setTool("manual-polygon")} title="Manual polygon mask"><PencilLine size={18} /></button>
      </div>
      <input className="text-input top-text-prompt" value={state.textPrompt} onChange={(e) => state.setTextPrompt(e.target.value)} placeholder="text prompt" />
      <div className="top-session-actions">
        <button className="command top-session" disabled={!project || busy !== null} onClick={onSession}>
          <Play size={18} /> {busy === "session" ? "Starting..." : "Start Session"}
        </button>
        <button className="command top-session reset" disabled={!project || !state.sessionId || busy !== null} onClick={onResetSession} title="Reset current SAM session">
          <RotateCcw size={18} /> {busy === "reset" ? "Resetting..." : "Reset"}
        </button>
      </div>
      <div className="top-status" title={message}>
        <span>{formatBackendName(state.backend)} · {state.samDevice}</span>
        <span>Session: {state.sessionId ? state.sessionId.slice(0, 8) : "未启动"}</span>
        {message && <span>{message}</span>}
      </div>
    </header>
  );
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

function formatBackendName(backend: string): string {
  if (backend === "mock") return "模拟模式";
  if (backend === "sam3_multiplex_video") return "SAM3.1 多目标视频";
  if (backend === "sam3_video") return "SAM3 视频";
  if (backend === "unreachable") return "后端未连接";
  return backend;
}
