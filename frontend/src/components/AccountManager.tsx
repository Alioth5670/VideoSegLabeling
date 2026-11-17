import { useEffect, useState, type FormEvent } from "react";
import { KeyRound, Plus, RefreshCw, Search, X } from "lucide-react";
import axios from "axios";
import { api } from "../api/client";
import type { User } from "../types/account";

function describeError(error: unknown) {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
  return typeof detail === "string" ? detail : "操作失败，请检查输入后重试。";
}

export default function AccountManager({ user, onClose }: { user: User; onClose: () => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<User | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    api.get<{ users: User[] }>("/auth/users")
      .then(result => { if (active) setUsers(result.data.users); })
      .catch(failure => { if (active) setError(describeError(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function refresh() {
    setLoading(true);
    try { setUsers((await api.get<{ users: User[] }>("/auth/users")).data.users); }
    finally { setLoading(false); }
  }

  function clearEditor() {
    setCreating(false); setTarget(null); setUsername(""); setPassword(""); setConfirmation("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || (!creating && !target)) return;
    if (password !== confirmation) { setError("两次输入的密码不一致"); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      if (target) {
        await api.post(`/auth/users/${target.id}/password`, { password });
        if (target.id === user.id) { clearEditor(); window.location.reload(); return; }
        setNotice(`${target.username} 的密码已重置，该账户需要重新登录。`);
      } else {
        await api.post("/auth/users", { username, password });
        setQuery(""); setStatus("all");
        setNotice(`账户 ${username} 已创建。`);
      }
      clearEditor();
      await refresh();
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  }

  async function toggleActive(item: User) {
    if (busy || item.id === user.id) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api.patch(`/auth/users/${item.id}`, { active: !item.active });
      setNotice(item.active ? `${item.username} 已停用，旧登录已失效。` : `${item.username} 已启用。`);
      await refresh();
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  }

  const rows = users.filter(item => item.username.toLowerCase().includes(query.trim().toLowerCase()) &&
    (status === "all" || item.active === (status === "active")));

  return <section className="project-manager account-manager" role="dialog" aria-modal="true" aria-labelledby="account-manager-title">
    <div className="project-manager-inner">
      <header className="project-manager-header"><div><h1 id="account-manager-title">账户管理</h1><p>创建账户、管理启用状态，或为账户重置密码。</p></div><button className="command" onClick={onClose}>返回标注</button></header>
      <div className="project-manager-toolbar">
        <label className="project-owner-filter"><span>状态</span><select className="text-input" value={status} onChange={event => setStatus(event.target.value)}><option value="all">全部账户</option><option value="active">已启用</option><option value="disabled">已停用</option></select></label>
        <div className="project-search-field"><Search size={17} aria-hidden="true" /><input aria-label="搜索账户名称" placeholder="搜索账户名称…" value={query} onChange={event => setQuery(event.target.value)} />{query && <button type="button" aria-label="清空搜索" onClick={() => setQuery("")}><X size={15} /></button>}</div>
        <button className="command project-refresh" disabled={busy || loading} onClick={() => { setError(""); void refresh().catch(failure => setError(describeError(failure))); }}><RefreshCw size={16} className={loading ? "project-refresh-spinning" : ""} />刷新</button>
        <button className="primary" disabled={busy} onClick={() => { const open = !creating; clearEditor(); setCreating(open); setError(""); setNotice(""); }}><Plus size={17} />新建账户</button>
      </div>
      {error && <p className="project-manager-error" role="alert">{error}</p>}
      {notice && <p className="project-manager-notice" role="status">{notice}</p>}
      {(creating || target) && <form className="project-manager-editor account-manager-editor" onSubmit={submit}>
        <div className="account-editor-heading"><h2>{target ? `重置 ${target.username} 的密码` : "新建普通账户"}</h2><p>{target ? "重置后该账户需重新登录，项目、标注和 SAM session 保留。" : "普通账户仅能访问自己的项目，用户名支持字母、数字、下划线、点和连字符。"}</p></div>
        <fieldset disabled={busy}>
          {creating && <label>用户名<input autoFocus className="text-input" autoComplete="off" required maxLength={80} pattern="[a-zA-Z0-9_.-]+" value={username} onChange={event => setUsername(event.target.value)} /></label>}
          <label>{target ? "新密码" : "密码"}（至少 6 位）<input autoFocus={Boolean(target)} className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={password} onChange={event => setPassword(event.target.value)} /></label>
          <label>确认密码<input className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
        </fieldset>
        <div className="account-editor-actions"><button className="primary" disabled={busy}>{busy ? "处理中…" : target ? target.id === user.id ? "重置并重新登录" : "确认重置" : "创建账户"}</button><button type="button" className="command" disabled={busy} onClick={clearEditor}>取消</button></div>
      </form>}
      <div className="project-manager-table account-manager-table" aria-busy={loading}><table><colgroup><col className="account-col-name" /><col /><col /><col className="account-col-actions" /></colgroup><thead><tr><th>账户名称</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>
        {rows.map(item => <tr key={item.id}><td><strong>{item.username}</strong>{item.id === user.id && <span className="account-self-tag">当前账户</span>}</td><td>{item.admin ? "管理员" : "普通账户"}</td><td><span className={`account-status ${item.active ? "enabled" : "disabled"}`}><i />{item.active ? "已启用" : "已停用"}</span></td><td><div className="project-manager-actions"><button className="command" disabled={busy} onClick={() => { clearEditor(); setTarget(item); setError(""); setNotice(""); }}><KeyRound size={15} />重置密码</button><button className={`command ${item.active ? "danger" : ""}`} disabled={busy || item.id === user.id} title={item.id === user.id ? "不能停用当前账户" : undefined} onClick={() => void toggleActive(item)}>{item.active ? "停用" : "启用"}</button></div></td></tr>)}
        {rows.length === 0 && <tr><td colSpan={4} className="project-manager-empty">{loading ? "正在加载账户…" : "没有符合条件的账户"}</td></tr>}
      </tbody></table></div>
      <footer className="project-manager-footer"><span>共 {users.length} 个账户{query || status !== "all" ? `，当前显示 ${rows.length} 个` : ""}</span><span className="account-manager-hint">停用账户会立即撤销该账户的旧登录。</span></footer>
    </div>
  </section>;
}
