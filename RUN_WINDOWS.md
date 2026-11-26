# Run Online Store on Windows (PowerShell)

## Quick start

```powershell
cd "C:\Users\ezeki\PycharmProjects\Online Store"
docker compose up -d --build
```

- Frontend: http://localhost:3000  
- Backend: http://localhost:8000  

## Local dev (no Docker)

```powershell
cd "C:\Users\ezeki\PycharmProjects\Online Store"
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Other terminal:

```powershell
cd "C:\Users\ezeki\PycharmProjects\Online Store\frontend"
npm run dev
```

## Notes

- Project root folder: `Online Store` (under `PycharmProjects`).
- Docker containers: `online-store-postgres`, `online-store-backend`, `online-store-frontend`.