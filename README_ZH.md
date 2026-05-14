# 🎬 VideoSegLabeling

**[English](README.md) | 中文**

> 一个强大的浏览器视频分割标注工具，支持 AI 辅助标注、实时掩码传播和灵活的项目管理。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.1.0-green.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react)

## ✨ 核心特性

- 🎥 **视频与多媒体支持** - 上传和管理多个视频项目
- 🖱️ **灵活的标注方式** - 点击、矩形框、文本提示和多边形编辑
- 🤖 **AI 驱动的分割** - 集成 SAM3/SAM3.1 进行智能分割
- 📊 **掩码传播** - 自动在视频帧间传播分割结果
- 📁 **项目管理** - 完整的项目创建、编辑、删除和导出工作流
- 🔄 **批量操作** - 高效的批量删除和编辑功能
- 🖥️ **Web 界面** - 现代化的 React + TypeScript 前端

## 📦 发布版本说明

该项目提供两种获取方式：

| 类型 | 描述 | 用途 |
|------|------|------|
| **GitHub 源代码仓库** | 包含后端代码、前端源码、脚本、文档和 SAM3 子模块 | 开发、自定义扩展 |
| **GitHub Release 包** | 包含预编译的前端 (`frontend/dist`)，无需 Node.js | 快速部署、生产环境 |

> ℹ️ 本版本暂不支持 Docker 部署。

## 📜 许可证

此项目采用 **Apache 2.0** 许可证。详见 [LICENSE](LICENSE)。

### ⚖️ SAM3 许可证注意

SAM3 作为 Git 子模块引用，受 Meta 的 SAM License 管控。SAM3 模型权重、检查点和其他 SAM 材料**不包含**在此仓库或发布包中。需要通过以下环境变量配置本地 SAM3 路径：

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

---

## 🚀 快速开始

### 方式一：从 Release 包开始（推荐新用户）

1. **下载并解压**
   ```bash
   tar -xzf VideoSegLabeling-x.x.x.tar.gz
   cd VideoSegLabeling-x.x.x
   ```

2. **安装依赖**
   ```bash
   ./install.sh
   # 选择选项 1：仅安装 Python 依赖（前端已预构建）
   ```

3. **启动应用**
   ```bash
   ./start.sh
   ```

4. **打开浏览器**
   ```
   http://127.0.0.1:8010
   ```

   > 默认使用 `SAM_BACKEND=mock`，适合先测试 UI 和工作流，无需 GPU 配置。

---

### 方式二：从源代码开始（开发者）

1. **克隆仓库**
   ```bash
   git clone <your-repo-url>
   cd VideoSegLabeling
   cp .env.example .env
   ```

2. **安装依赖**
   ```bash
   ./install.sh
   # 选择选项 2：安装 Python 依赖并获取 SAM3
   # 选择选项 3：同时构建前端（推荐用于一体化部署）
   ```

3. **启动应用**
   
   **选项 A：一体化启动**（前后端共用一个 FastAPI 服务器）
   ```bash
   ./start.sh
   # 访问 http://127.0.0.1:8010
   ```

   **选项 B：分离启动**（适合前端开发调试）
   ```bash
   # 终端 1：启动后端
   ./start_backend.sh
   
   # 终端 2：启动前端开发服务器
   ./start_frontend.sh
   # 访问 http://localhost:5173
   ```

---

## 📖 手动安装（高级用户）

### Python 虚拟环境设置

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# 或在 Windows 上：
# .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

### SAM3 设置（可选）

**从 Git 子模块获取：**
```bash
git submodule update --init --recursive
```

**或直接克隆（Release 包用户）：**
```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```

### 前端构建（可选，仅源代码用户）

```bash
cd frontend
npm ci
npm run build
```

### 启动应用

```bash
./start.sh
```

---

## ⚙️ 配置说明

### 环境变量配置

1. **复制配置模板**
   ```bash
   cp .env.example .env
   ```

2. **编辑 `.env` 文件**

### 常见配置变量

```env
# 服务器配置
BACKEND_PORT=8010
PROJECTS_DIR=./projects

# SAM 模型后端
SAM_BACKEND=mock                           # 选项：mock, sam3_video, sam3_multiplex_video
SAM_DEVICE=cuda:0
CUDA_VISIBLE_DEVICES=0

# SAM3 路径配置
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

### 后端模型选项对比

| 后端 | 描述 | 要求 | 场景 |
|------|------|------|------|
| **mock** | 模拟后端，无需模型 | 无 | 测试 UI、演示 |
| **sam3_video** | SAM3 视频预测器 | GPU + SAM3.pt | 视频分割任务 |
| **sam3_multiplex_video** | SAM3.1 多路视频预测器 | GPU + SAM3.1_multiplex.pt | 高性能视频分割 |

### GPU 多卡配置

在多 GPU 服务器上，建议仅暴露一张物理 GPU：

```bash
CUDA_VISIBLE_DEVICES=0 SAM_DEVICE=cuda:0 ./start.sh
```

---

## 📁 项目数据结构

项目默认存储在 `projects/` 目录：

```
projects/
├── {project_id}/
│   ├── project.json          # 项目元数据
│   ├── annotations.json      # 标注数据
│   ├── videos/               # 上传的视频文件
│   ├── frames/               # 提取的视频帧
│   ├── masks/                # 分割掩码
│   └── overlays/             # 掩码叠加图像
└── .gitkeep
```

**特点：**
- 上传的文件夹保留相对路径结构
- 可将相关的视频和标签保存在同一项目内
- `projects/*` 被 Git 忽略，仅保留 `.gitkeep`

---

## 💾 构建发布版本

### 创建新版本

```bash
./build_release.sh
```

生成文件：
```
release/VideoSegLabeling-x.x.x/
release/VideoSegLabeling-x.x.x.tar.gz
```

### 发布特定版本

```bash
./build_release.sh 1.0.1
```

### 发布流程

1. ✅ 脚本自动构建前端
2. ✅ 自动打包后端代码
3. ✅ 生成 `.tar.gz` 文件
4. 📤 上传至 GitHub Releases

> 最终用户仅需 Python，无需 Node.js/npm/Vite/TypeScript。

---

## 🗂️ 仓库结构说明

```
VideoSegLabeling/
├── backend/                    # FastAPI 后端服务
│   ├── run_backend.py          # 启动脚本
│   └── app/
│       ├── main.py             # 主应用
│       ├── config.py           # 配置管理
│       ├── api/                # API 路由
│       ├── schemas/            # 数据模型
│       ├── services/           # 业务逻辑
│       └── utils/              # 工具函数
│
├── frontend/                   # React + Vite 前端
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── api/                # API 客户端
│       ├── components/         # React 组件
│       ├── store/              # 状态管理
│       ├── types/              # TypeScript 类型
│       └── utils/              # 工具函数
│
├── sam3/                       # SAM3 模型（Git 子模块）
│   └── [Meta 官方代码]
│
├── checkpoints/                # 模型检查点目录
│   ├── sam3.pt                 # SAM3 权重 (需下载)
│   └── sam3.1_multiplex.pt     # SAM3.1 权重 (需下载)
│
├── projects/                   # 项目数据目录
│   └── [各项目的视频和标注]
│
├── docs/                       # 文档和部署指南
├── deploy/                     # 部署配置示例
├── requirements.txt            # Python 依赖清单
├── install.sh                  # 交互式安装脚本
├── start.sh                    # 启动脚本
├── start_backend.sh            # 后端启动脚本
├── start_frontend.sh           # 前端启动脚本
├── build_release.sh            # 构建发布版本
├── stop.sh                     # 停止脚本
├── LICENSE                     # Apache 2.0 许可证
└── README.md                   # 本文件
```

---

## 🎮 使用指南

### 创建新项目

1. **打开应用** → 首页
2. **点击** "Create Project" 按钮
3. **输入** 项目名称和描述
4. **确认** 创建

### 上传视频

1. **进入项目** → "Videos" 标签页
2. **点击** "Upload" 按钮
3. **选择** 视频文件或文件夹
4. **等待** 上传和处理完成
5. **预览** 上传的视频列表

### 标注视频

#### 基础标注工作流

1. **选择视频** 并点击进入标注编辑器
2. **浏览帧** 使用左侧时间线或键盘快捷键
3. **创建标注**：
   - 🖱️ **点击提示**：点击对象位置
   - 📦 **矩形框**：拖拽创建边界框
   - ✏️ **多边形**：连续点击绘制形状
   - 💬 **文本标签**：为对象添加文字描述

4. **传播掩码**：
   - 标注完成后，点击 "Propagate" 按钮
   - AI 自动将掩码应用到后续帧（若配置了 SAM 后端）

5. **编辑和调整**：
   - 双击掩码进入编辑模式
   - 调整边界、添加或删除区域
   - 点击 "Save" 保存更改

#### 快捷键速查

| 快捷键 | 功能 |
|--------|------|
| `←` / `→` | 上一帧 / 下一帧 |
| `Spacebar` | 播放 / 暂停 |
| `Delete` | 删除选中标注 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+Y` | 重做 |
| `Escape` | 取消当前操作 |

### 导出项目

1. **进入项目** → "Export" 标签页
2. **选择** 导出格式：
   - 📸 **Frames + Masks**：图像和掩码
   - 📊 **JSON**：标注元数据
   - 🎥 **Video**：带掩码叠加的视频
3. **点击** "Export" 开始导出
4. **下载** 生成的文件

### 管理对象

1. **在标注面板** 查看所有对象
2. **为每个对象**：
   - ✏️ 编辑名称和属性
   - 🎨 修改颜色
   - 🗑️ 删除单个对象
3. **批量删除**：选择多个对象后点击 "Delete Selected"

---

## 🐛 故障排除

### 问题：启动后显示空白页面

**解决方案：**
```bash
# 清空浏览器缓存
# 或在 Chrome DevTools 中：
# Settings → Network conditions → Disable cache (勾选)
# 然后刷新页面
```

### 问题：后端无法连接

**检查步骤：**
```bash
# 1. 确保后端正在运行
ps aux | grep start_backend.sh

# 2. 检查端口是否被占用
lsof -i :8010

# 3. 查看后端日志
tail -f logs/backend.log
```

### 问题：模型加载失败 (SAM 后端)

**检查清单：**
- ✅ SAM3 子模块已初始化：`git submodule update --init --recursive`
- ✅ 检查点文件存在：
  ```bash
  ls -lh checkpoints/
  ```
- ✅ `.env` 中路径正确
- ✅ GPU 内存充足（建议 ≥ 8GB）

### 问题：前端开发模式中样式不加载

**解决方案：**
```bash
# 重启前端开发服务器
./start_frontend.sh

# 清除 Vite 缓存
rm -rf frontend/node_modules/.vite
```

### 问题：项目导出速度缓慢

**优化建议：**
- 减小视频分辨率
- 降低视频帧率
- 仅导出必要的帧范围

---

## 🔗 相关资源

| 资源 | 链接 |
|------|------|
| **SAM3 官方** | [facebookresearch/sam3](https://github.com/facebookresearch/sam3) |
| **SAM License** | [Meta Research](https://github.com/facebookresearch/sam/blob/main/LICENSE) |
| **部署指南** | [docs/server_deployment.md](docs/server_deployment.md) |
| **报告问题** | [GitHub Issues](https://github.com/your-repo/issues) |

---

## 🚢 GitHub 发布检查清单

### 发布前准备

在推送代码和创建 Release 前，请执行以下检查：

```bash
# 1. 检查 Git 状态
git status

# 2. 检查子模块状态
git submodule status

# 3. 构建前端
npm --prefix frontend run build

# 4. 验证 Python 代码语法
python -m py_compile backend/app/main.py backend/run_backend.py

# 5. 运行测试（如果有）
# pytest tests/

# 6. 检查是否有未追踪的文件
git status --porcelain
```

### 发布流程

1. **创建版本标签**
   ```bash
   git tag vx.x.x
   ```

2. **构建 Release 包**
   ```bash
   ./build_release.sh x.x.x
   ```

3. **推送到 GitHub**
   ```bash
   git push origin main
   git push origin vx.x.x
   ```

4. **创建 GitHub Release**
   - 前往 GitHub → Releases → "Create a new release"
   - 选择 `vx.x.x` 标签
   - 填写发布说明
   - 上传 `release/VideoSegLabeling-x.x.x.tar.gz` 文件
   - 点击 "Publish release"

### 发布清单

- [ ] 测试功能正常
- [ ] 前后端都能正常启动
- [ ] README 文档已更新
- [ ] 版本号已更新
- [ ] 子模块指向正确分支
- [ ] 无 Git 冲突或未提交的更改
- [ ] 前端已构建
- [ ] Release 包已生成
- [ ] GitHub Release 已创建

---

## 📚 开发指南

### 前端开发工作流

```bash
# 1. 启动后端
./start_backend.sh

# 2. 在另一个终端启动前端开发服务器
./start_frontend.sh

# 3. 打开 http://localhost:5173
# 前端修改会自动热重载
```

### 后端开发工作流

```bash
# 进入虚拟环境
source .venv/bin/activate

# 启动开发服务器（带自动重载）
python backend/run_backend.py --reload

# 或使用 uvicorn 直接运行
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 添加新依赖

```bash
# Python 包
pip install <package-name>
pip freeze > requirements.txt

# 前端包
cd frontend
npm install <package-name>
git add package.json package-lock.json
```

---

## ❓ 常见问题

**Q：为什么要使用 Git 子模块？**
> A：SAM3 项目很大，作为子模块可以降低克隆时间，同时保持代码独立。用户可以选择是否需要完整的 SAM3 源代码。

**Q：模型权重在哪里下载？**
> A：SAM3 和 SAM3.1 的权重需要从 [Meta SAM3 官方仓库](https://github.com/facebookresearch/sam3) 单独下载，放入 `checkpoints/` 目录。

**Q：可以在 CPU 上运行吗？**
> A：可以，但推荐使用 GPU 获得更好的性能。使用 `SAM_DEVICE=cpu` 配置即可。

**Q：Release 包是否包含所有功能？**
> A：是的，Release 包包含所有功能。唯一的区别是已预构建前端，无需 Node.js。

**Q：如何升级到新版本？**
> A：下载新版本的 Release 包，覆盖旧版本即可。项目数据保存在 `projects/` 目录，会自动保留。

**Q：支持多语言吗？**
> A：目前主要支持中文和英文。欢迎贡献其他语言翻译！

---

## 🤝 贡献指南

欢迎贡献代码、报告 Bug 和建议功能！

### 报告 Bug

1. 查看 [现有 Issue](https://github.com/your-repo/issues)
2. 创建新 Issue，包含：
   - 操作系统和 Python 版本
   - 详细的复现步骤
   - 错误日志
   - 预期行为 vs 实际行为

### 提交 PR

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

### 编码规范

- **Python**: 遵循 PEP 8
- **TypeScript**: 使用 Prettier 格式化
- **提交信息**: 使用有意义的、清晰的描述

---

## 📝 更新日志

### v0.1.0 (当前版本)

**新功能：**
- ✨ 完整的视频分割标注工具
- 🤖 SAM3/SAM3.1 集成
- 📊 掩码传播功能
- 💾 灵活的项目导出

**已知限制：**
- 暂不支持 Docker 部署
- SAM3 权重需要单独下载

---

## 📧 联系方式

- 📖 详细文档：查看 `docs/` 目录
- 🐛 问题反馈：[GitHub Issues](https://github.com/your-repo/issues)
- 💬 讨论：[GitHub Discussions](https://github.com/your-repo/discussions)

---

**祝您使用愉快！如有任何问题，欢迎提出反馈。** 🌟
