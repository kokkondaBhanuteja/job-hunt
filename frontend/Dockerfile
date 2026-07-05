# Stage 1: build the React/Vite app
FROM node:20-alpine AS build

WORKDIR /app

# Install deps first for layer cache
COPY package.json package-lock.json ./
RUN npm ci

# Vite build-time env var: empty string → same-origin relative base → nginx proxies /api/*
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}

COPY . .
RUN npm run build

# Stage 2: serve the static bundle with nginx
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
# Template (not a static conf): the nginx image runs envsubst on it at startup to
# inject ${API_TOKEN} into the /api/ proxy, so the browser never holds the token.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
