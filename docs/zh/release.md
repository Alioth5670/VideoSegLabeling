# 💾 发布指南

**[文档目录](README.md) | [English](../en/release.md)**

## 构建 Release 包

```bash
./build_release.sh
./build_release.sh 1.0.1
```

生成结果：

```text
release/VideoSegLabeling-x.x.x/
release/VideoSegLabeling-x.x.x.tar.gz
```

Release 包用户只需要 Python，不需要 Node.js/npm/Vite/TypeScript。

## 发布检查

```bash
git status
git submodule status
npm --prefix frontend run build
python -m py_compile backend/app/main.py backend/run_backend.py
git status --porcelain
```

## 发布流程

```bash
git tag vx.x.x
./build_release.sh x.x.x
git push origin main
git push origin vx.x.x
```

然后在 GitHub 创建 Release，并上传 `release/VideoSegLabeling-x.x.x.tar.gz`。
