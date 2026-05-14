# 🚀 快速开始

**[文档目录](README.md) | [English](../en/quick-start.md)**

## 发布方式

| 类型 | 描述 | 用途 |
|------|------|------|
| GitHub 源代码仓库 | 后端代码、前端源码、脚本、文档和 SAM3 子模块 | 开发和自定义扩展 |
| GitHub Release 包 | 包含预编译前端 (`frontend/dist`)，无需 Node.js | 快速部署和生产环境 |

本版本暂不包含 Docker 部署。

## 从 Release 包开始

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

默认使用 `SAM_BACKEND=mock`，适合先测试 UI 和工作流，无需 GPU 配置。

## 从源代码开始

```bash
git clone <your-repo-url>
cd VideoSegLabeling
cp .env.example .env
./install.sh
./start.sh
```

前端开发时可分离启动：

```bash
./start_backend.sh
./start_frontend.sh
```

打开 `http://localhost:5173`。

## 手动安装

### Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows 激活方式：

```bash
.venv\Scripts\activate
```

### SAM3 设置

从 Git 子模块获取：

```bash
git submodule update --init --recursive
```

Release 包用户也可以直接克隆：

```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```

### 前端构建

```bash
cd frontend
npm ci
npm run build
```
