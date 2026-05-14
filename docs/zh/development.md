# 📚 开发指南

**[文档目录](README.md) | [English](../en/development.md)**

## 前端开发流程

```bash
./start_backend.sh
./start_frontend.sh
```

打开 `http://localhost:5173`。

## 后端开发流程

```bash
source .venv/bin/activate
python backend/run_backend.py --reload
```

## 添加依赖

Python：

```bash
pip install <package-name>
pip freeze > requirements.txt
```

前端：

```bash
cd frontend
npm install <package-name>
git add package.json package-lock.json
```
