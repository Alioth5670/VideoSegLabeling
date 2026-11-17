import ChangePasswordDialog from "./ChangePasswordDialog";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";

import type { User } from "../types/account";
import ProjectManager from "./ProjectManager";

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : "操作失败，请检查输入（用户名仅限字母、数字、_.-，密码至少 6 位）";
}

export default function AccountGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [setup, setSetup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [manage, setManage] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  function clearReset() {
    setResetTarget(null); setNewPassword(""); setConfirmPassword("");
  }

  useEffect(() => {
    async function init() {
      try {
        const status = await api.get("/auth/status");
        setSetup(!status.data.initialized);
        if (status.data.initialized) {
          try { setUser((await api.get("/auth/me")).data.user); } catch { /* Login required. */ }
        }
      } catch { setMessage("无法连接服务器，请刷新重试"); }
      setReady(true);
    }
    void init();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (user) {
        await api.post("/auth/users", { username, password });
        setUsers((await api.get("/auth/users")).data.users);
        setMessage("账户已创建");
      } else {
        if (setup) { await api.post("/auth/setup", { username, password }); setSetup(false); }
        setUser((await api.post("/auth/login", { username, password })).data.user);
      }
      setUsername("");
      setPassword("");
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }

  async function toggleActive(item: User) {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      await api.patch(`/auth/users/${item.id}`, { active: !item.active });
      setUsers((await api.get("/auth/users")).data.users);
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }

  async function resetPassword(event: React.FormEvent) {
    event.preventDefault();
    if (!resetTarget || busy) return;
    if (newPassword !== confirmPassword) { setMessage("两次输入的密码不一致"); return; }
    setBusy(true); setMessage("");
    try {
      await api.post(`/auth/users/${resetTarget.id}/password`, { password: newPassword });
      const self = resetTarget.id === user?.id;
      clearReset();
      if (self) { window.location.reload(); return; }
      setMessage("密码已重置，该账户需使用新密码重新登录");
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }

  const form = <form onSubmit={submit} className="account-form">
    <label>用户名<input className="text-input" autoComplete="username" value={username} required maxLength={80} pattern="[a-zA-Z0-9_.-]+" onChange={e => setUsername(e.target.value)} /></label>
    <label>密码（至少 6 位）<input className="text-input" type="password" autoComplete={setup || user ? "new-password" : "current-password"} required minLength={6} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} /></label>
    <button className="primary" disabled={busy}>{busy ? "处理中…" : user ? "创建账户" : setup ? "创建管理员并登录" : "登录"}</button>
  </form>;

  if (!ready) return <div className="account-screen">正在连接…</div>;
  if (!user) return <div className="account-screen"><section className="panel account-card">
    <h2>{setup ? "初始化管理员账户" : "登录视频标注平台"}</h2>
    {setup && <p>首次创建的管理员将接管现有项目。其他账户由管理员创建，各自仅可访问自己的项目。</p>}
    {form}
    {message && <p role="status">{message}</p>}
  </section></div>;

  return <>
    <div className="account-bar"><span>{user.username}{user.admin ? " · 管理员" : ""}</span>
      <button className="command" onClick={() => { clearReset(); setPassword(""); setManage(false); setProjectsOpen(value => !value); }}>项目管理</button>
      {Boolean(user.admin) && <button className="command" onClick={async () => {
        try { setUsers((await api.get("/auth/users")).data.users); clearReset(); setPassword(""); setManage(!manage); setProjectsOpen(false); setMessage(""); }
        catch (error) { setMessage(errorMessage(error)); }
      }}>账户管理</button>}
      <button className="command" onClick={() => { clearReset(); setPassword(""); setManage(false); setProjectsOpen(false); setPasswordOpen(true); }}>修改密码</button>
      <button className="command" onClick={async () => { await api.post("/auth/logout"); window.location.reload(); }}>退出登录</button>
    </div>
    {manage && <div className="account-screen account-modal"><section className="panel account-card">
      <button className="command" disabled={busy} onClick={() => { clearReset(); setPassword(""); setManage(false); }}>关闭</button><h2>账户管理</h2>
      {message && <p role="status">{message}</p>}
      {users.map(item => <div className="account-user" key={item.id}><span>{item.username} {item.admin ? "（管理员）" : ""}{!item.active ? "（已停用）" : ""}</span>
        <div className="account-user-actions">
          <button className="command" disabled={busy} onClick={() => { clearReset(); setResetTarget(item); setMessage(""); }}>重置密码</button>
          <button className="command" disabled={busy || item.id === user.id} onClick={() => void toggleActive(item)}>{item.active ? "停用" : "启用"}</button>
        </div></div>)}
      {resetTarget && <form className="account-form account-reset" onSubmit={resetPassword}>
        <h3>重置 {resetTarget.username} 的密码</h3>
        <p>重置后，该账户在所有浏览器上需要重新登录。项目、标注和 SAM session 保留。</p>
        <label>新密码（至少 6 位）<input autoFocus className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
        <label>确认新密码<input className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></label>
        <button className="primary" disabled={busy}>{busy ? "处理中…" : "确认重置密码"}</button>
        <button className="command" type="button" disabled={busy} onClick={clearReset}>取消</button>
      </form>}
      <h3>新建普通账户</h3>{form}
    </section></div>}
    {children}
    {passwordOpen && <ChangePasswordDialog onClose={() => setPasswordOpen(false)} onSuccess={() => window.location.reload()} />}
    {projectsOpen && <ProjectManager user={user} onClose={() => setProjectsOpen(false)} />}
  </>;
}
