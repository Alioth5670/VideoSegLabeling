import { isCurrentProject } from "../utils/project";
import { BoxSelect, CircleMinus, CirclePlus, MousePointer2, PencilLine, Play, RectangleHorizontal, RotateCcw, Power } from "lucide-react";
import { useEffect, useState } from "react";
import axios from "axios";
import { getHealth } from "../api/health";
import { getVideoSession, resetSession, startSession, closeSession, getGPUResources } from "../api/sam";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

export default function TopControls() {
  const { project } = useProjectStore();
  const state = useAnnotationStore();
  const [busy, setBusy] = useState<"session" | "reset" | "release" | null>(null);
  const [message, setMessage] = useState("");
  const [resources, setResources] = useState<{ pool: boolean; free: number } | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = () => getGPUResources().then(value => { if (active) setResources(value); }).catch(() => {});
    refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("sam-resources-changed", refresh);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener("sam-resources-changed", refresh); };
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => getHealth().then(health => {
      if (!active) return;
      const store = useAnnotationStore.getState();
      if (!store.sessionId) {
        store.setBackend(health.sam_backend);
        store.setSamDevice(health.sam_device);
      }
      if (health.sam_fallback_error) setMessage(health.sam_fallback_error);
    }).catch(() => { if (active && !useAnnotationStore.getState().sessionId) useAnnotationStore.getState().setBackend("unreachable"); });
    void refresh();
    window.addEventListener("sam-resources-changed", refresh);
    return () => { active = false; window.removeEventListener("sam-resources-changed", refresh); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const annotation = useAnnotationStore.getState();
    annotation.clearSession();
    setMessage("");
    if (!project) return;
    const current = project;
    getVideoSession(current.projectId, current.activeVideoId, controller.signal).then(result => {
      if (controller.signal.aborted || !isCurrentProject(current.projectId, current.activeVideoId)) return;
      if (result.session) {
        const store = useAnnotationStore.getState();
        if (store.sessionId && store.sessionId !== result.session.session_id) return;
        store.setSession(result.session.session_id, result.backend);
        store.addSessionObjectIds(result.session.object_ids);
        store.setSamDevice(result.device);
        setMessage("已恢复当前视频的 session");
      }
    }).catch(error => {
      if (!controller.signal.aborted && isCurrentProject(current.projectId, current.activeVideoId)) setMessage(errorMessage(error));
    });
    return () => controller.abort();
  }, [project?.projectId, project?.activeVideoId]);

  useEffect(() => {
    if (!project) return;
    let active = true;
    const timer = window.setInterval(async () => {
      const expected = useAnnotationStore.getState().sessionId;
      if (!expected) return;
      try {
        const result = await getVideoSession(project.projectId, project.activeVideoId);
        if (!active || !isCurrentProject(project.projectId, project.activeVideoId) || useAnnotationStore.getState().sessionId !== expected) return;
        if (result.session?.session_id !== expected) {
          useAnnotationStore.getState().clearSession();
          setMessage("Session 已释放，请点击 Start Session 重新申请 GPU。");
        }
      } catch { /* Keep the session display during temporary network failures. */ }
    }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [project?.projectId, project?.activeVideoId]);

  async function onSession() {
    if (!project) return;
    setBusy("session");
    setMessage("Loading SAM session...");
    try {
      const session = await startSession(project.projectId, project.activeVideoId);
      if (!isCurrentProject(project.projectId, project.activeVideoId)) return;
      state.setSession(session.session_id, session.backend);
      state.resetSessionObjects();
      state.addSessionObjectIds(session.object_ids);
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
      if (!isCurrentProject(project.projectId, project.activeVideoId)) return;
      state.resetSessionObjects();
      setMessage("Session reset. Existing annotations are kept; add prompts again to track objects.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function onRelease() {
    if (!project || !state.sessionId) return;
    setBusy("release");
    try {
      await closeSession(project.projectId, state.sessionId);
      if (isCurrentProject(project.projectId, project.activeVideoId)) {
        state.clearSession();
        setMessage("Session 已关闭，GPU 已释放；已保存的标注保留。");
      }
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
        <button className="command top-session" disabled={!project || !state.sessionId || busy !== null} onClick={onRelease} title="关闭 session 并释放 GPU，已保存的标注保留">
          <Power size={18} /> {busy === "release" ? "释放中..." : "释放 GPU"}
        </button>
      </div>
      <div className="top-status" title={message}>
        <span>{formatBackendName(state.backend)} · {state.samDevice}{resources?.pool ? ` · 空闲 GPU ${resources.free}` : ""}</span>
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
