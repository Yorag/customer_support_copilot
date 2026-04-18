# Frontend Control Plane

This directory contains the standalone frontend control-plane scaffold introduced in `FE-00`.

## Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run test:run`

## Environment

Create `frontend/.env` when you need to override the backend origin:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The backend defaults to `http://127.0.0.1:8000`, which matches `python serve_api.py`.
