# 📚 Development

**[Documentation](README.md) | [中文](../zh/development.md)**

## Frontend Workflow

```bash
./start_backend.sh
./start_frontend.sh
```

Open `http://localhost:5173`.

## Backend Workflow

```bash
source .venv/bin/activate
python backend/run_backend.py --reload
```

## Add Dependencies

Python:

```bash
pip install <package-name>
pip freeze > requirements.txt
```

Frontend:

```bash
cd frontend
npm install <package-name>
git add package.json package-lock.json
```
