# Compila Angular y sirve el resultado como archivos estáticos
FROM node:22-alpine AS construccion
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=construccion /app/dist/frontend/browser /usr/share/nginx/html
