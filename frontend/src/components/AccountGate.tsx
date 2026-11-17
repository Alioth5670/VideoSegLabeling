import ChangePasswordDialog from "./ChangePasswordDialog";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";

import type { User } from "../types/account";
import ProjectManager from "./ProjectManager";
import GPUManager from "./GPUManager";
import AccountManager from "./AccountManager";

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
  const [page, setPage] = useState<"accounts" | "projects" | "gpu" | null>(null);
  const [passwordOpen, setPasswordOpen] = useState(false);

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
      if (setup) { await api.post("/auth/setup", { username, password }); setSetup(false); }
      setUser((await api.post("/auth/login", { username, password })).data.user);
      setUsername("");
      setPassword("");
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }

  const form = <form onSubmit={submit} className="account-form">
    <label>用户名<input className="text-input" autoComplete="username" value={username} required maxLength={80} pattern="[a-zA-Z0-9_.-]+" onChange={e => setUsername(e.target.value)} /></label>
    <label>密码（至少 6 位）<input className="text-input" type="password" autoComplete={setup ? "new-password" : "current-password"} required minLength={6} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} /></label>
    <button className="primary" disabled={busy}>{busy ? "处理中…" : setup ? "创建管理员并登录" : "登录"}</button>
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
      <button className="command" aria-pressed={page === "projects"} onClick={() => setPage(page === "projects" ? null : "projects")}>项目管理</button>
      {Boolean(user.admin) && <button className="command" aria-pressed={page === "accounts"} onClick={() => setPage(page === "accounts" ? null : "accounts")}>账户管理</button>}
      {Boolean(user.admin) && <button className="command" aria-pressed={page === "gpu"} onClick={() => setPage(page === "gpu" ? null : "gpu")}>GPU 管理</button>}
      <button className="command" onClick={() => { setPage(null); setPasswordOpen(true); }}>修改密码</button>
      <button className="command" onClick={async () => { await api.post("/auth/logout"); window.location.reload(); }}>退出登录</button>
    </div>
    {children}
    {passwordOpen && <ChangePasswordDialog onClose={() => setPasswordOpen(false)} onSuccess={() => window.location.reload()} />}
    {Boolean(user.admin) && page === "accounts" && <AccountManager user={user} onClose={() => setPage(null)} />}
    {Boolean(user.admin) && page === "gpu" && <GPUManager onClose={() => setPage(null)} />}
    {page === "projects" && <ProjectManager user={user} onClose={() => setPage(null)} />}
  </>;
}
