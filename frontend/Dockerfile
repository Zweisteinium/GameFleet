# Build stage
FROM node:24-alpine AS build

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Use exactly the pnpm version pinned in package.json ("packageManager") so Docker and local installs agree.
RUN corepack enable && corepack install
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm prepare
RUN pnpm build

# Runtime: the adapter-node server serves the app and proxies /api to BACKEND_URL (set by docker-compose.yml).
FROM node:24-alpine AS node-server

WORKDIR /app
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["node", "build"]
