# ⚙️ 配置说明

**[文档目录](README.md) | [English](../en/configuration.md)**

复制配置模板：

```bash
cp .env.example .env
```

常见变量：

```env
BACKEND_PORT=8010
PROJECTS_DIR=./projects

SAM_BACKEND=mock
SAM_DEVICE=cuda:0
CUDA_VISIBLE_DEVICES=0

SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

## 后端选项

| 后端 | 描述 | 要求 | 场景 |
|------|------|------|------|
| `mock` | 模拟后端，无需模型 | 无 | UI 测试和演示 |
| `sam3_video` | SAM3 视频预测器 | GPU + SAM3 检查点 | 视频分割 |
| `sam3_multiplex_video` | SAM3.1 多路视频预测器 | GPU + SAM3.1 检查点 | 高性能视频分割 |

多 GPU 服务器建议只暴露一张物理 GPU：

```bash
CUDA_VISIBLE_DEVICES=0 SAM_DEVICE=cuda:0 ./start.sh
```

## 项目数据结构

项目默认保存在 `projects/`：

```text
projects/
├── {project_id}/
│   ├── project.json
│   ├── annotations.json
│   ├── videos/
│   ├── frames/
│   ├── masks/
│   └── overlays/
└── .gitkeep
```

上传的文件夹会保留相对路径结构。`projects/*` 被 Git 忽略，仅提交 `.gitkeep`。

## 仓库结构

```text
VideoSegLabeling/
├── backend/
├── frontend/
├── sam3/
├── checkpoints/
├── projects/
├── docs/
├── deploy/
├── requirements.txt
├── install.sh
├── start.sh
├── start_backend.sh
├── start_frontend.sh
├── build_release.sh
├── stop.sh
├── LICENSE
└── README.md
```
