# Stage 1: build the Vue 3 + Element Plus frontend (dist is NOT committed;
# it is built here so the repository stays free of node_modules and bundles).
FROM node:24-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: Python backend, serving web/dist when present.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY --from=webbuild /web/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.seed; uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
