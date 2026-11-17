import { Pencil, ChevronDown, Check, X, FolderOpen, Trash2, Search, RotateCw, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import axios from "axios";
import { api } from "../api/client";
import { createProject, getProject, listProjects, renameProject, recycleProject, restoreProject, transferProject, permanentlyDeleteProject, type ProjectSummary } from "../api/project";
import { applyProjectPayload, clearWorkspace, defaultProjectName } from "../utils/project";
import { useProjectStore } from "../store/projectStore";
import { useAnnotationStore } from "../store/annotationStore";
import type { User } from "../types/account";

function describeError(error: unknown) {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
  return typeof detail === "string" ? detail : error instanceof Error ? error.message : "操作失败，请重试";
}

export default function ProjectManager({ user, onClose }: { user: User; onClose: () => void }) {
  const [users, setUsers] = useState<User[]>([user]);
  const [owner, setOwner] = useState("");
  const [query, setQuery] = useState("");
  const [deleted, setDeleted] = useState(false);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<ProjectSummary[]>([]);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState(defaultProjectName);
  const [newOwner, setNewOwner] = useState(user.id);
  const [editing, setEditing] = useState<ProjectSummary | null>(null);
  const [editName, setEditName] = useState("");
  const [transferring, setTransferring] = useState<ProjectSummary | null>(null);
  const [target, setTarget] = useState("");
  const [purging, setPurging] = useState<ProjectSummary | null>(null);
  const [confirmationName, setConfirmationName] = useState("");
  const pageSize = 20;

  useEffect(() => { useAnnotationStore.getState().setPlaying(false); }, []);

  useEffect(() => {
    if (user.admin) api.get<{ users: User[] }>("/auth/users").then(result => setUsers(result.data.users)).catch(failure => setError(describeError(failure)));
  }, [user.admin]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      listProjects(query, offset, pageSize, { all_accounts: Boolean(user.admin), owner_id: owner || undefined, deleted })
        .then(result => {
          if (!active) return;
          if (offset > 0 && offset >= result.total) { setOffset(Math.max(0, offset - pageSize)); return; }
          setRows(result.projects); setTotal(result.total);
        }).catch(failure => { if (active) { setRows([]); setError(describeError(failure)); } })
        .finally(() => { if (active) setLoading(false); });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query, owner, offset, deleted, revision, user.admin]);

  useEffect(() => { setEditing(null); setTransferring(null); }, [owner, query, offset, deleted]);

  async function act(operation: () => Promise<void>, message: string) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await operation();
      setNotice(message); setRevision(value => value + 1);
      window.dispatchEvent(new Event("projects-changed"));
    } catch (failure) { setError(describeError(failure)); }
    finally { setBusy(false); }
  }

  function changeTab(value: boolean) {
    setPurging(null); setConfirmationName(""); setDeleted(value); setOffset(0); setEditing(null); setTransferring(null); setError(""); setNotice(""); setShowCreate(false);
  }

  return <section className="project-manager" role="dialog" aria-modal="true" aria-labelledby="project-manager-title" data-project-management>
    <div className="project-manager-inner">
      <header className="project-manager-header"><div><h1 id="project-manager-title">项目管理</h1>
        <p>{user.admin ? "查看和管理各账户的项目，或调整项目归属。" : "查看和管理自己的视频标注项目。"}</p></div>
        <button className="command" onClick={onClose}>返回标注</button></header>
      <div className="project-manager-toolbar">
        <div className="project-view-switch" role="group" aria-label="项目列表类型"><button className={!deleted ? "active" : ""} aria-pressed={!deleted} onClick={() => changeTab(false)}><FolderOpen size={16} />正常项目</button><button className={deleted ? "active" : ""} aria-pressed={deleted} onClick={() => changeTab(true)}><Trash2 size={16} />回收站</button></div>
        {Boolean(user.admin) && <label className="project-owner-filter"><span>账户</span><select className="text-input" value={owner} onChange={event => { setOwner(event.target.value); setOffset(0); }}>
          <option value="">全部账户</option>{users.map(item => <option key={item.id} value={item.id}>{item.username}{!item.active ? "（已停用）" : ""}</option>)}
        </select></label>}
        <div className="project-search-field"><Search size={17} aria-hidden="true" /><input aria-label="搜索项目名称" placeholder="搜索项目名称…" value={query} onChange={event => { setQuery(event.target.value); setOffset(0); }} />{query && <button type="button" title="清空搜索" aria-label="清空搜索" onClick={() => { setQuery(""); setOffset(0); }}><X size={15} /></button>}</div>
        <button className="command project-refresh" disabled={busy || loading} onClick={() => { setError(""); setRevision(value => value + 1); }}><RotateCw size={16} className={loading ? "project-refresh-spinning" : ""} />刷新</button>
        {!deleted && <button className="primary" disabled={busy} onClick={() => { setNewName(defaultProjectName()); setNewOwner(users.some(item => item.id === owner && item.active) ? owner : user.id); setShowCreate(!showCreate); }}><Plus size={17} />新建项目</button>}
      </div>
      {showCreate && <form className="project-manager-editor" onSubmit={event => { event.preventDefault(); void act(async () => {
        await createProject(newName.trim(), undefined, user.admin ? newOwner : undefined);
        if (user.admin) setOwner(newOwner);
        setQuery(""); setShowCreate(false); setOffset(0);
      }, "项目已创建"); }}>
        <label>项目名称<input className="text-input" required maxLength={120} value={newName} onChange={event => setNewName(event.target.value)} /></label>
        {Boolean(user.admin) && <label>所属账户<select className="text-input" value={newOwner} onChange={event => setNewOwner(event.target.value)}>{users.filter(item => item.active).map(item => <option value={item.id} key={item.id}>{item.username}</option>)}</select></label>}
        <button className="primary" disabled={busy || !newName.trim()}>创建</button><button className="command" type="button" onClick={() => setShowCreate(false)}>取消</button>
      </form>}
      {purging && <form className="project-manager-editor project-manager-delete" onSubmit={event => { event.preventDefault(); void act(async () => {
        await permanentlyDeleteProject(purging.project_id, confirmationName);
        if (useProjectStore.getState().project?.projectId === purging.project_id) clearWorkspace();
        setPurging(null); setConfirmationName("");
      }, "项目及其文件已彻底删除"); }}>
        <div><strong>彻底删除“{purging.name}”</strong><p>将永久删除项目的视频、标注、导出文件和索引，此操作无法恢复。目录已不存在时，仅清理残留索引。</p></div>
        <label>输入项目名称确认<input autoFocus className="text-input" required maxLength={256} autoComplete="off" placeholder={purging.name} value={confirmationName} onChange={event => setConfirmationName(event.target.value)} /></label>
        <button className="command danger" disabled={busy || confirmationName !== purging.name}>{busy ? "正在删除…" : "确认彻底删除"}</button>
        <button className="command" type="button" disabled={busy} onClick={() => { setPurging(null); setConfirmationName(""); }}>取消</button>
      </form>}
      {error && <p className="project-manager-error" role="alert">{error}</p>}
      {notice && <p className="project-manager-notice" role="status">{notice}</p>}
      {deleted && <p className="project-manager-hint">回收站中的项目保留视频、标注和导出文件，恢复后可继续标注。</p>}
      <div className="project-manager-table" aria-busy={loading}>
        <table className={user.admin ? "project-table-admin" : "project-table-own"}>
          <colgroup><col className="project-col-name" />{Boolean(user.admin) && <col className="project-col-owner" />}<col className="project-col-status" /><col className="project-col-updated" /><col className="project-col-actions" /></colgroup>
          <thead><tr><th>项目名称</th>{Boolean(user.admin) && <th>所属账户</th>}<th>数据状态</th><th>更新时间</th><th>操作</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.project_id}><td>
            {editing?.project_id === row.project_id ? <form className="project-cell-editor" onSubmit={event => {
              event.preventDefault();
              void act(async () => {
                const updated = await renameProject(row.project_id, editName.trim());
                const current = useProjectStore.getState().project;
                if (current?.projectId === row.project_id) useProjectStore.getState().setProject({ ...current, name: updated.name });
                setEditing(null);
              }, "项目已重命名");
            }} onKeyDown={event => { if (event.key === "Escape" && !busy) { event.preventDefault(); setEditing(null); } }}>
              <input autoFocus className="text-input" aria-label={`重命名 ${row.name}`} required maxLength={120} disabled={busy} value={editName} onChange={event => setEditName(event.target.value)} />
              <div className="project-cell-editor-actions"><button className="project-cell-control confirm" type="submit" title="保存名称" aria-label="保存名称" disabled={busy || !editName.trim()}><Check size={15} /></button><button className="project-cell-control" type="button" title="取消重命名" aria-label="取消重命名" disabled={busy} onClick={() => setEditing(null)}><X size={15} /></button></div>
            </form> : deleted ? <strong>{row.name}</strong> : <button className="project-cell-trigger project-name-trigger" title="点击重命名项目" aria-label={`重命名 ${row.name}`} disabled={busy || row.data_status === "missing"} onClick={() => { setEditing(row); setEditName(row.name); setTransferring(null); setError(""); setNotice(""); }}><strong>{row.name}</strong><Pencil size={14} /></button>}
            <small>{row.project_id}</small></td>
            {Boolean(user.admin) && <td>
              {transferring?.project_id === row.project_id ? <form className="project-cell-editor" onSubmit={event => {
                event.preventDefault();
                void act(async () => { await transferProject(row.project_id, target); setTransferring(null); }, "项目归属已更新");
              }} onKeyDown={event => { if (event.key === "Escape" && !busy) { event.preventDefault(); setTransferring(null); } }}>
                <select autoFocus className="text-input" aria-label={`转移 ${row.name} 的所属账户`} required disabled={busy} value={target} onChange={event => setTarget(event.target.value)}>
                  <option value={row.owner_id}>{row.owner_username}</option>
                  {users.filter(item => item.active && item.id !== row.owner_id).map(item => <option key={item.id} value={item.id}>{item.username}</option>)}
                </select>
                <div className="project-cell-editor-actions"><button className="project-cell-control confirm" type="submit" title="确认转移" aria-label="确认转移账户" disabled={busy || !target || target === row.owner_id}><Check size={15} /></button><button className="project-cell-control" type="button" title="取消转移" aria-label="取消转移账户" disabled={busy} onClick={() => setTransferring(null)}><X size={15} /></button></div>
              </form> : deleted ? row.owner_username : <button className="project-cell-trigger" title="点击转移所属账户" aria-label={`转移 ${row.name} 的所属账户`} disabled={busy || row.data_status === "missing"} onClick={() => { setTransferring(row); setTarget(row.owner_id); setEditing(null); setError(""); setNotice(""); }}>{row.owner_username}<ChevronDown size={14} /></button>}
            </td>}
            <td><span className={`project-data-status ${row.data_status === "missing" ? "missing" : ""}`} title={row.missing_reason ?? ""}>{row.data_status === "missing" ? "文件缺失" : "正常"}</span>
</td>
            <td className="project-updated"><time dateTime={row.updated_at}>{formatUpdatedTime(row.updated_at)}</time></td>
            <td><div className="project-manager-actions">{deleted ? <><button className="command" disabled={busy || row.data_status === "missing"} title={row.data_status === "missing" ? "请先恢复项目目录和 project.json，再刷新并恢复项目" : ""} onClick={() => void act(async () => { await restoreProject(row.project_id); }, "项目已恢复")}>恢复项目</button>
              <button className="command danger" disabled={busy} onClick={() => { setPurging(row); setConfirmationName(""); setError(""); setNotice(""); }}>彻底删除</button></> : <>
              <button className="command" disabled={busy || row.data_status === "missing"} onClick={() => void act(async () => { applyProjectPayload(await getProject(row.project_id)); onClose(); }, "")}>打开标注</button>
              <button className="command danger" disabled={busy} onClick={() => {
                if (window.confirm(`将“${row.name}”移入回收站？视频和标注文件会保留，可在回收站恢复。`)) void act(async () => {
                  await recycleProject(row.project_id);
                  if (useProjectStore.getState().project?.projectId === row.project_id) clearWorkspace();
                  setEditing(null); setTransferring(null);
                }, "项目已移入回收站");
              }}>移入回收站</button>
            </>}</div></td></tr>)}
            {!rows.length && <tr><td colSpan={user.admin ? 5 : 4} className="project-manager-empty">{loading ? "正在加载项目…" : deleted ? "回收站为空" : "暂无项目，点击新建项目开始。"}</td></tr>}
          </tbody></table>
      </div>
      <footer className="project-manager-footer"><span>共 {total} 个项目{loading ? " · 加载中…" : ""}</span><div className="project-pagination">
        <button className="command" disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>上一页</button>
        <span>{Math.floor(offset / pageSize) + 1} / {Math.max(1, Math.ceil(total / pageSize))}</span>
        <button className="command" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(value => value + pageSize)}>下一页</button>
      </div></footer>
    </div>
  </section>;
}


function formatUpdatedTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
