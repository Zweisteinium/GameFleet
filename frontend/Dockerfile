# Build stage
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Use exactly the pnpm version pinned in package.json ("packageManager") so Docker and local installs agree.
RUN corepack enable && corepack install
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm prepare
RUN pnpm build

# Lightweight Node.js server option (default)
FROM node:22-alpine AS node-server

WORKDIR /app
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./
RUN npm install -g serve
EXPOSE 3000
CMD ["serve", "-s", "build", "-l", "3000"]

# Nginx server
FROM nginx:alpine AS nginx-server

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]