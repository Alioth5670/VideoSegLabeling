import { useEffect, useState, type FormEvent } from "react";
import { Cpu, RefreshCw, Save, Power } from "lucide-react";
import axios from "axios";
import { getGPUAdmin, saveGPUSettings, releaseGPUSession, type GPUSettings, type GPUSnapshot, type GPUSession } from "../api/gpu";
import { useAnnotationStore } from "../store/annotationStore";

function describeError(error: unknown) {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "配置格式不正确，请检查数值范围及显卡列表。";
  return error instanceof Error ? error.message : "操作失败，请重试。";
}

export default function GPUManager({ onClose }: { onClose: () => void }) {
  const [snapshot, setSnapshot] = useState<GPUSnapshot | null>(null);
  const [form, setForm] = useState<GPUSettings | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const value = await getGPUAdmin();
        if (active) { setSnapshot(value); setForm(previous => previous ?? value.settings); setLoadError(""); }
      } catch (failure) { if (active) setLoadError(describeError(failure)); }
    };
    void load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  async function refresh() {
    setRefreshing(true);
    try { setSnapshot(await getGPUAdmin()); setLoadError(""); }
    catch (failure) { setLoadError(describeError(failure)); }
    finally { setRefreshing(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await saveGPUSettings(form);
      setForm(saved);
      setNotice("配置已保存，重启后仍保留。分配规则用于新 session，空闲释放时间也应用于现有 session。");
      await refresh();
      window.dispatchEvent(new Event("sam-resources-changed"));
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  }

  async function release(session: GPUSession) {
    const detail = session.busy ? "将中止正在加载或运行的推理，尚未保存的结果会丢失。" : "将关闭推理 session 并释放显卡。";
    if (!window.confirm(`${session.username} · ${session.project_name}\n${detail}已保存的标注保留，继续吗？`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await releaseGPUSession(session.session_id, session.busy);
      if (useAnnotationStore.getState().sessionId === session.session_id) useAnnotationStore.getState().clearSession();
      setNotice("Session 已释放，已保存的标注保留。");
      await refresh();
      window.dispatchEvent(new Event("sam-resources-changed"));
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  }

  function numberField(name: keyof GPUSettings, label: string, min: number, max: number, divisor = 1) {
    if (!form) return null;
    return <label>{label}<input className="text-input" type="number" required min={min} max={max} step={divisor === 60 ? 0.5 : 1} value={Number(form[name]) / divisor} onChange={event => setForm({ ...form, [name]: event.target.valueAsNumber * divisor })} /></label>;
  }

  return <section className="project-manager gpu-manager" role="dialog" aria-modal="true" aria-labelledby="gpu-manager-title">
    <div className="project-manager-inner">
      <header className="project-manager-header"><div><h1 id="gpu-manager-title"><Cpu size={25} />GPU 管理</h1><p>配置显卡分配与自动释放，查看各账户正在使用的资源。</p></div><button className="command" onClick={onClose}>返回标注</button></header>
      {(loadError || error) && <p className="project-manager-error" role="alert">{error || loadError}</p>}
      {notice && <p className="project-manager-notice" role="status">{notice}</p>}
      {!form && !loadError && <p>正在读取配置…</p>}
      {form && <form className="gpu-settings" onSubmit={save}>
        <header><div><h2>分配策略</h2><p>每个账户最多一个 session，每张显卡最多一个推理进程。</p></div><button className="primary" disabled={busy}><Save size={16} />{busy ? "处理中…" : "保存配置"}</button></header>
        <fieldset disabled={busy}>
          <label>推理模型<select className="text-input" value={form.sam_backend} onChange={event => setForm({ ...form, sam_backend: event.target.value as GPUSettings["sam_backend"] })}><option value="sam3_multiplex_video">SAM3.1 多目标视频</option><option value="sam3_video">SAM3 视频</option><option value="mock">模拟模式（不占用 GPU）</option></select></label>
          <label className="gpu-pool-toggle"><span>按需 GPU 池</span><span><input type="checkbox" checked={form.sam_gpu_pool} onChange={event => setForm({ ...form, sam_gpu_pool: event.target.checked })} />启用多用户独立推理进程</span></label>
          <label>允许使用的显卡<input className="text-input" value={form.sam_gpu_devices} placeholder="留空允许全部；例如 0,1,3" onChange={event => setForm({ ...form, sam_gpu_devices: event.target.value })} /><small>填写下方物理编号或完整 GPU UUID，以逗号分隔。</small></label>
          {numberField("sam_gpu_min_free_mb", "最低空闲显存（MiB）", 1, 1048576)}
          {numberField("sam_gpu_max_used_mb", "允许已用显存上限（MiB）", 0, 1048576)}
          {numberField("sam_gpu_max_utilization", "允许利用率上限（%）", 0, 100)}
          {numberField("sam_session_idle_seconds", "空闲自动释放（分钟）", 0.5, 10080, 60)}
          {numberField("sam_worker_timeout_seconds", "推理进程响应超时（秒）", 30, 86400)}
        </fieldset>
        <p className="gpu-settings-note">修改白名单不终止已有 session。切换模型或 GPU 池模式需先释放所有 session；关闭 GPU 池会恢复旧单进程模式，无法提供独立进程和自动释放保障。</p>
      </form>}
      <div className="gpu-section-heading"><div><h2>显卡状态</h2><p>约每 10 秒刷新。其他程序占用的显卡不会被本系统强制释放。</p></div><button className="command" disabled={refreshing || busy} onClick={() => void refresh()}><RefreshCw size={16} />刷新</button></div>
      {snapshot?.discovery_error && <p className="project-manager-error" role="status">{snapshot.discovery_error} 配置仍可保存。</p>}
      <div className="gpu-device-grid">{snapshot?.devices.map(device => <article className="gpu-device" key={device.id}>
        <header><strong>{device.label}</strong><span className={`gpu-state ${device.available ? "free" : ""}`}>{device.reserved ? "已分配" : !device.allowed ? "未允许" : device.available ? "可分配" : "不可分配"}</span></header>
        <small title={device.id}>{device.id}</small>
        <dl><div><dt>空闲 / 总显存</dt><dd>{(device.free_memory_mb / 1024).toFixed(1)} / {(device.total_memory_mb / 1024).toFixed(1)} GiB</dd></div><div><dt>利用率</dt><dd>{device.utilization}%</dd></div></dl>
        <meter min={0} max={device.total_memory_mb} value={device.used_memory_mb} aria-label={`${device.label} 已用显存`} />
      </article>)}</div>
      <div className="gpu-section-heading"><div><h2>账户 Session</h2><p>{snapshot?.sessions.length ?? 0} 个 session · 强制释放会中止当前推理。</p></div></div>
      <div className="project-manager-table gpu-session-table"><table><thead><tr><th>账户</th><th>项目</th><th>设备</th><th>状态</th><th>操作</th></tr></thead><tbody>
        {snapshot?.sessions.map(session => <tr key={session.session_id}><td><strong>{session.username}</strong></td><td>{session.project_name}</td><td>{session.device}</td><td>{!session.ready ? "正在加载" : session.busy ? "推理中" : `空闲 ${Math.floor(session.idle_seconds / 60)} 分钟`}</td><td><button className={`command ${session.busy ? "danger" : ""}`} disabled={busy} onClick={() => void release(session)}><Power size={15} />{session.busy ? "强制释放" : "释放"}</button></td></tr>)}
        {snapshot && snapshot.sessions.length === 0 && <tr><td colSpan={5} className="gpu-empty">暂无 session，未加载任何 GPU 池模型。</td></tr>}
      </tbody></table></div>
    </div>
  </section>;
}
