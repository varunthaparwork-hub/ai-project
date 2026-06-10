# Multi-stage build: compile React/Vite to static assets, then serve via nginx.
# nginx also proxies /api → api:8000 (preserving SSE streaming) so the browser
# only ever talks to a single origin.

# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: serve ───────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Replace default config with one that proxies /api and /health to the FastAPI
# service, with SSE-safe settings (no buffering, no caching, http/1.1).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
