# ─────────────── build stage ───────────────
FROM node:20-alpine AS build

WORKDIR /app

# Install deps first for better caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build-time API base URL. Empty default = same-origin (nginx proxies /api).
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY tsconfig.json tsconfig.node.json vite.config.ts ./
COPY tailwind.config.ts postcss.config.js ./
COPY index.html ./
COPY public ./public
COPY src ./src

RUN npm run build

# ─────────────── runtime stage ───────────────
FROM nginx:alpine AS runtime

# SSE-friendly nginx config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Default nginx CMD already runs nginx in foreground.
