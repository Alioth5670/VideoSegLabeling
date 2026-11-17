import { useState } from "react";
import axios from "axios";
import { api } from "../api/client";

export default function ChangePasswordDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (newPassword !== confirmation) { setMessage("两次输入的新密码不一致"); return; }
    setBusy(true); setMessage("");
    try {
      await api.post("/auth/password", { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(""); setNewPassword(""); setConfirmation("");
      onSuccess();
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setMessage(typeof detail === "string" ? detail : "修改失败，请重试");
    } finally { setBusy(false); }
  }

  return <div className="account-screen account-modal" role="dialog" aria-modal="true" aria-labelledby="change-password-title">
    <section className="panel account-card">
      <h2 id="change-password-title">修改自己的密码</h2>
      <p>修改后需要使用新密码重新登录。项目、标注和 SAM session 保留。</p>
      <form className="account-form" onSubmit={submit}>
        <label>当前密码<input autoFocus className="text-input" type="password" autoComplete="current-password" required maxLength={256} value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /></label>
        <label>新密码（至少 6 位）<input className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
        <label>确认新密码<input className="text-input" type="password" autoComplete="new-password" required minLength={6} maxLength={256} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
        {message && <p role="alert">{message}</p>}
        <button className="primary" disabled={busy}>{busy ? "正在修改…" : "确认修改并重新登录"}</button>
        <button className="command" type="button" disabled={busy} onClick={onClose}>取消</button>
      </form>
    </section>
  </div>;
}
