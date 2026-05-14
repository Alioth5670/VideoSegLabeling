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
