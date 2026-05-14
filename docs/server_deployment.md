# 服务器迁移部署说明

本文档按 Linux 服务器部署整理，适用于当前 FastAPI 后端 + Vite/React 前端 + 本地 SAM3 权重的结构。

## 代码结构结论

当前仓库的关键目录如下：

```text
backend/                  FastAPI 后端
frontend/                 React + Vite 前端
projects/                 用户项目、视频、帧、mask、导出结果
sam3/                     本地 SAM3 官方仓库
sam3.pt                   SAM3 权重，约 3.3G
sam3.1_multiplex.pt       SAM3.1 multiplex 权重，约 3.3G
bpe_simple_vocab_16e6.txt.gz
```

不建议迁移这些目录：

```text
frontend/node_modules/
venv-server/
frontend/dist/            可在服务器重新构建；如果服务器不装 Node，也可以迁移
backend/app/**/__pycache__/
```

当前工作区里的 `frontend/node_modules/.bin/tsc` 和 `vite` 没有执行权限，直接复用这份 `node_modules` 会导致 `npm run build` 报 `Permission denied`。服务器上应使用 `npm ci` 重新安装前端依赖。

建议迁移这些内容：

```text
backend/
frontend/                 排除 node_modules
docs/
sam3/
sam3.pt
sam3.1_multiplex.pt
bpe_simple_vocab_16e6.txt.gz
projects/                 如果要保留已有项目数据
README.md
AGENT.md
```

## 推荐服务器目录

示例使用 `/opt/video-seg-labeling`：

```bash
sudo mkdir -p /opt/video-seg-labeling
sudo chown -R "$USER":"$USER" /opt/video-seg-labeling
```

如果使用下方 `systemd` 模板里的 `www-data` 运行后端，部署完成后需要给运行用户写入 `projects/` 的权限：

```bash
sudo chown -R www-data:www-data /opt/video-seg-labeling/projects
```

## 传输文件

从本机执行：

```bash
rsync -avh --progress \
  --exclude 'frontend/node_modules' \
  --exclude 'venv-server' \
  --exclude 'frontend/dist' \
  --exclude '__pycache__' \
  /YuHang/VideoSegLabeling/ user@server:/opt/video-seg-labeling/
```

如果服务器无法联网安装前端依赖，可以去掉 `--exclude 'frontend/dist'`，直接迁移已构建产物。

## 后端环境

服务器需要 Python 3.10+，当前环境已使用 Python 3.12。推荐在服务器重新创建虚拟环境：

```bash
cd /opt/video-seg-labeling/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果需要 GPU 推理，先按服务器 CUDA 版本安装匹配的 PyTorch，再安装其余依赖。例如：

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

当前后端默认 `SAM_BACKEND=mock`，不加载真实模型。要启用真实 SAM3：

```bash
export SAM_BACKEND=sam3_multiplex_video
```

如真实 SAM3 初始化失败，代码会回退到 mock。

## 后端环境变量

建议写入 `/etc/video-seg-labeling.env`：

```bash
BACKEND_PORT=8010
PROJECTS_DIR=/opt/video-seg-labeling/projects
SAM_REPO_PATH=/opt/video-seg-labeling/sam3
SAM_CHECKPOINT_PATH=/opt/video-seg-labeling/sam3.pt
SAM31_CHECKPOINT_PATH=/opt/video-seg-labeling/sam3.1_multiplex.pt
SAM_BACKEND=mock
SAM_PRECISION=bfloat16
```

确认后端可启动：

```bash
cd /opt/video-seg-labeling/backend
source .venv/bin/activate
python run_backend.py
```

健康检查：

```bash
curl http://127.0.0.1:8010/api/health
```

## systemd 后端服务

参考 [deploy/video-seg-labeling.service.example](../deploy/video-seg-labeling.service.example)。

安装：

```bash
sudo cp /opt/video-seg-labeling/deploy/video-seg-labeling.service.example /etc/systemd/system/video-seg-labeling.service
sudo systemctl daemon-reload
sudo systemctl enable --now video-seg-labeling
sudo systemctl status video-seg-labeling
```

查看日志：

```bash
journalctl -u video-seg-labeling -f
```

## 前端构建

服务器需要 Node.js 18+：

```bash
cd /opt/video-seg-labeling/frontend
npm ci
npm run build
```

构建产物在：

```text
/opt/video-seg-labeling/frontend/dist
```

前端 API 使用相对路径 `/api`，生产环境建议由 Nginx 同域反向代理，不需要改前端代码。

## Nginx

参考 [deploy/nginx.video-seg-labeling.conf.example](../deploy/nginx.video-seg-labeling.conf.example)。

安装：

```bash
sudo cp /opt/video-seg-labeling/deploy/nginx.video-seg-labeling.conf.example /etc/nginx/sites-available/video-seg-labeling
sudo ln -s /etc/nginx/sites-available/video-seg-labeling /etc/nginx/sites-enabled/video-seg-labeling
sudo nginx -t
sudo systemctl reload nginx
```

部署后访问：

```text
http://server_ip/
```

## 生产部署检查清单

1. `projects/` 已迁移，且运行服务的用户有读写权限。
2. `sam3/` 与两个 `.pt` 权重路径和环境变量一致。
3. 后端 `curl http://127.0.0.1:8010/api/health` 正常。
4. `frontend/dist/index.html` 存在。
5. Nginx `/api/` 与 `/projects/` 都代理到 `127.0.0.1:8010`。
6. 如果开启真实 SAM3，确认服务器显存足够，并用日志检查是否回退到了 mock。

## 常见问题

- 上传视频失败：检查 `projects/` 目录权限。
- 前端页面能打开但接口 404：检查 Nginx `/api/` 代理规则。
- 能创建项目但看不到帧图：检查 Nginx `/projects/` 代理规则。
- 真实 SAM3 变成 mock：检查 `SAM_REPO_PATH`、权重路径、CUDA/PyTorch 版本和后端日志。
- 首次构建慢：不要迁移 `node_modules` 和 `venv-server`，在服务器按环境重新安装更稳。
