# ADMS production frontend image — multi-stage build.
# Stage 1: build the React/TypeScript SPA. VITE_API_BASE_URL is intentionally
# NOT set: the client defaults to http://192.168.1.248:8081 (the LAN API).
# Stage 2: serve the static build with nginx:alpine (SPA fallback configured
# in docker/nginx.conf).

FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
