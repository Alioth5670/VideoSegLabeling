# 🎬 VideoSegLabeling

**[English](README.md) | 中文**

基于浏览器的视频分割标注工具，支持 AI 辅助标注、掩码传播和项目导出工作流。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.1.0-green.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react)

## ✨ 核心特性

- 🎥 视频项目上传、管理、标注和导出
- 🖱️ 点击、矩形框、多边形和文本提示标注工具
- 🤖 集成 SAM3/SAM3.1，并提供 mock 后端用于 UI 测试
- 📊 支持视频帧间掩码传播
- 🖥️ React + TypeScript 前端和 FastAPI 后端

## 🚀 快速开始

### Release 包

```bash
tar -xzf VideoSegLabeling-x.x.x.tar.gz
cd VideoSegLabeling-x.x.x
./install.sh
./start.sh
```

打开：

```text
http://127.0.0.1:8010
```

### 源代码

```bash
git clone <your-repo-url>
cd VideoSegLabeling
cp .env.example .env
./install.sh
./start.sh
```

前端开发模式：

```bash
./start_backend.sh
./start_frontend.sh
```

然后打开 `http://localhost:5173`。

## 升级现有部署

在仓库根目录执行（沿用 `venv-server` 环境）：

```bash
venv-server/bin/python -m pip install -r requirements.txt
(cd frontend && npm ci && npm run build)
./start.sh
```

先停止旧后端，再启动更新后的服务。`./start.sh` 检测到 `frontend/dist` 时由后端统一提供页面；`./start.sh --dev` 使用 tmux 启动前后端开发服务。访问地址以启动日志和 `.env` 中的 `BACKEND_PORT` 为准，示例配置为 8010。当前本地启动脚本会激活 `venv-server`；首次安装可用 `VENV_DIR="$PWD/venv-server" ./install.sh --build-frontend` 创建该环境并构建前端。

升级前停止服务并备份整个 `PROJECTS_DIR` 和登记的自定义项目目录，包括隐藏的 `.accounts.sqlite3`、各视频的 `annotations.sqlite3`、视频及 masks。仅备份旧 `annotations.json` 无法保留升级后的新增标注。账户与标注数据库自动迁移；内存中的 SAM session 不跨后端重启保留。

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 📚 文档

- [完整中文文档](docs/zh/README.md)
- [Full English documentation](docs/en/README.md)
- [许可证](LICENSE)
- [第三方声明](THIRD_PARTY_NOTICES.md)

## ⚖️ SAM3 说明

SAM3 作为 Git 子模块引用，受 Meta 的 SAM License 管控。SAM3 权重和检查点不包含在此仓库或 Release 包中。通过以下环境变量配置本地路径：

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

## 📜 许可证

此项目采用 Apache 2.0 许可证。详见 [LICENSE](LICENSE)。


## 账户与项目隔离

更新后需要重启后端并重新构建前端（`cd frontend && npm run build`）。首次访问页面时创建管理员账户，用户名支持字母、数字、下划线、点和连字符，密码至少 6 位。初始化会一次性扫描现有项目（包括注册的自定义目录），将其归入该管理员名下，原有视频和标注文件保留。

管理员在页面顶部的“账户管理”中创建普通账户，并可停用或重新启用账户。停用会立即撤销现有登录会话。普通账户只能查看和操作自己的项目；管理员可通过“项目管理”查看所有账户的项目，并转移项目归属。仅管理员可指定自定义项目存储目录或切换共享 SAM 模型和设备。

项目列表改为 SQLite 索引查询，支持名称搜索和分页（每页 50 个项目）；上传、标注和导出接口均检查项目归属。原 `/projects/` 静态目录入口已关闭，图像、mask 和下载需通过登录后的 `/api/projects/...` 接口访问。账户、会话和项目索引保存在 `PROJECTS_DIR/.accounts.sqlite3`，备份时需要与项目数据一同备份。标注元数据现使用下述 SQLite 增量存储，mask 继续保存为 PNG。

登录有效期为 24 小时，密码使用 scrypt 哈希，浏览器通过 HttpOnly、SameSite Cookie 保存会话。HTTPS 部署时配置 `AUTH_COOKIE_SECURE=true`。首次初始化应由部署者在开放服务给其他用户前完成。

权限回归测试（仅使用临时项目目录）：

```bash
PYTHONPATH=backend venv-server/bin/python -m unittest discover -s backend/tests -v
```


## 标注、导出与推理性能

标注元数据按视频存放于 `annotations.sqlite3`，首次访问时事务性导入同目录的旧 `annotations.json`。旧 JSON 保留，但后续不再更新；SQLite 是标注数据的主存储。备份或迁移项目时需要包含 SQLite 文件和 masks 目录。需要最新 JSON 时，请使用 Project JSON 导出或完整标注 API，导出结构保持兼容。帧查询、目标创建和更新、标注写入、prompt 写入均使用增量 SQL；传播每帧的多个目标在同一事务中保存。项目打开及分割后的刷新使用对象和已标注帧号摘要，不再传输整段标注。

COCO RLE 改用 NumPy 向量计算；ZIP 中的 PNG 直接打包，JSON 使用快速压缩。内容未变化时复用导出归档，每种格式最多保留最近两个缓存版本。导出完成后才发布下载地址，前端显示任务进度并防止重复提交。

SAM3 与 SAM3.1 都通过本地官方 `init_state` 初始化，保留其 tracker 和交互状态，仅在初始化期间替换帧来源。图片按需解码，默认最多缓存 8 张 CPU 帧，不再同步解码整段视频，也不会启动后台线程加载所有帧。官方模型仍需创建逐帧的轻量元数据，因此启动时间仍会随帧数增长；首次加载 checkpoint 也仍需时间。

真实模型共用一个视频 session：重复启动当前视频会复用 session。仅浏览、切换视频或项目不会关闭 session，切回原视频时会自动恢复其 session 和可传播目标；只有显式启动另一个视频的 session、关闭 session 或更换模型/设备时才释放旧状态。重置会保留 session 编号并清空模型中的目标。分割、传播与模型切换互斥，避免请求同时占用显存。默认通过官方 tracker 的 `offload_state_to_cpu` 参数把跟踪状态保存在 CPU，保留至多 4 帧近期 backbone 特征。传播通过回调及时保存，后端不再持有全视频的 mask 数组；事件队列有容量限制，客户端断开会取消任务并关闭模型传播生成器。CUDA OOM 会释放 session 并提示重新启动，不会把本次推理静默替换为 mock。

可配置 `SAM_FRAME_CACHE_SIZE`、`SAM_FEATURE_CACHE_SIZE` 和 `SAM_OFFLOAD_STATE_TO_CPU`（见 `.env.example`）。默认关闭逐帧 mask 诊断日志，避免为日志额外复制和同步 GPU 数据；调试时可设置 `SAM_DEBUG_LOGGING=true`。CPU offload 会降低部分传播速度，但能减少显存占用。这些控制不能保证任意分辨率、任意目标数量都不会 OOM；大模型本身、当前帧和目标数量仍需容纳于显存。当前仅支持单个后端进程持有共享 GPU 模型。

更新后重启后端并刷新前端，前端源码部署需运行 `cd frontend && npm run build`。旧标注自动按访问迁移，无需批量转换。


## 后台导出与进度

导出已改为任务模式：`POST /api/projects/{project_id}/export` 接收 `{"format":"coco_video_json","video_id":"可选的视频 ID"}`，立即返回 HTTP 202 和任务信息（`job_id`、`status`、`progress`、`stage`），不再同步返回可用下载地址。通过 `GET /api/projects/{project_id}/export/{job_id}` 查询任务，`status=completed` 时 `download_url` 才可使用。调用旧同步接口的脚本需要改为轮询任务。

编码和 ZIP 打包在独立 Python 子进程中执行，不加载 SAM 或 CUDA。默认同时只运行一个导出任务，最多容纳 8 个运行中或等待中的任务；相同项目、视频和格式的未完成任务会复用，队列满时返回 HTTP 429。导出子进程限制数值库线程数量，避免抢占所有 CPU 核。导出期间仍可浏览和标注；CPU、内存与磁盘资源仍由同一台机器共享。

进度条按读取标注、逐 mask 编码、打包文件、合并 JSON 等实际阶段更新，不表示精确剩余时间。页面每 750ms 查询一次状态，完成后显示下载按钮，失败时显示错误。任务状态保存在项目的 `exports/jobs/` 下，浏览器保存当前任务编号，因此刷新页面或切换回对应视频后可继续查看。任务捕获提交时选中的视频，后续切换视频不会改变该任务的导出对象；标注内容由子进程执行时读取。后端停止会终止未完成任务，重启后需重新提交；已完成任务仍可查询。


## 项目管理

页面顶部的“项目管理”对所有登录账户开放，支持按名称搜索、分页、创建、打开标注、重命名、移入回收站和恢复。普通账户只能管理自己的项目，无法通过 API 参数或项目 ID 访问其他账户的数据。

管理员可选择“全部账户”或指定账户查看项目，为启用的账户创建项目，并将项目转移给其他启用的账户。管理员也可打开和编辑其他账户的标注。侧边栏默认项目列表仍只展示自己的项目，跨账户管理使用项目管理页。

项目名称在同一账户的正常项目中不可重复（忽略大小写及首尾空格）；重命名、转移、恢复均会检查重名。转移成功后，原账户失去项目访问权限，目标账户获得权限。停用账户的已有项目仍可由管理员管理或转移。

“移入回收站”不会删除视频、标注或导出文件；项目从正常列表隐藏，常规标注和下载 API 拒绝访问，恢复后重新开放。恢复遇到重名时需先重命名当前同名项目。移入回收站或转移项目时会释放该项目的空闲 SAM session；正在推理时返回提示，需停止任务后再操作。后台启动时自动升级项目索引，已有数据无需手动迁移。


切换视频不会自动停止正在进行的传播。传播进度和“Stop Propagation”按钮绑定任务启动时的项目、视频和 session，即使当前查看的视频没有 session，仍可停止原任务。后台帧结果只写入原视频，界面仅在查看对应视频时刷新标注。后端重启或显式创建新的 session 后，旧 session 不再保留。

管理员可在“账户管理”中为账户重置密码（至少 6 位，支持重置自己的密码）。重置使该账户的旧登录失效，需要使用新密码重新登录；项目、标注、SAM session 和账户启用状态不变。普通账户无权重置密码。

所有账户（包括普通账户）均可点击顶部“修改密码”，输入当前密码、新密码和确认新密码；新密码至少 6 位。修改成功后该账户的旧登录失效，需要重新登录，项目、标注和 SAM session 保持不变。忘记当前密码时可联系管理员重置。

项目列表会检查当前页项目的 `project.json` 是否存在，并在管理页和侧边栏标记“文件缺失”。索引残留仍可移入回收站，此操作仅更新索引，不依赖或删除项目文件。系统不会自动清除缺失记录，临时离线的自定义存储恢复后，刷新即可重新识别；回收站中的项目需先恢复文件，才能恢复为正常项目。


## 回收站彻底删除

回收站每个项目提供“彻底删除”。输入完整项目名称确认后，会删除项目目录中的视频、标注、导出文件，同时移除账户索引和项目路径登记，无法恢复。普通账户只能删除自己的回收站项目，管理员可删除所有账户的回收站项目；正常项目需先移入回收站。

目录已经不存在的项目可直接清理残留索引。如果目录仍在，但缺少 `project.json` 或项目编号不匹配，则拒绝删除，避免误删不属于该项目的文件。公共目录、符号链接、与其他项目重叠的目录也不能删除；自定义目录含有非项目文件时需先单独处理。存在等待中或运行中的导出任务时，需等待任务结束后再删除。

SAM3.1 交互传播增加了缓存一致性适配：清理提示帧附近的普通传播缓存时，保留 `consolidated_frame_inds` 对应的人工修正输出及各目标视图，避免帧仍标记为已修正但结果已被删除而导致 `KeyError`。修复位于后端适配层，不修改 SAM3 子模块；已在 CPU 上使用本地模型实际方法复现并验证正向、反向及重复传播。升级后需重启后端并重新创建推理 session，已保存的标注文件保留。

## SAM3.1 设备兼容与诊断

多目标状态拆分、合并时，后端适配层会将 `mux/demux` 转换矩阵对齐到输入缓存的设备和数据类型，运算后恢复原矩阵，保留 CPU 转存缓存。分割失败会在后端记录完整 Traceback，并包含项目、视频、session、帧和目标编号，方便定位首次点击失败。此修复通过 CPU 回归测试，尚未在本机验证真实 CUDA 推理。
