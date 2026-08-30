# Build context is the REPO ROOT, not apps/web — the pnpm lockfile and
# workspace manifest live there:  docker build -f apps/web/Dockerfile .
FROM node:24-alpine AS build
RUN corepack enable
WORKDIR /app

# Manifests first so dependency layers cache independently of source changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web apps/web
RUN pnpm --filter web build

FROM node:24-alpine AS runtime
RUN corepack enable
WORKDIR /app
ENV NODE_ENV=production PORT=3000

# Copied wholesale to keep pnpm's symlinked store layout intact.
COPY --from=build /app /app

WORKDIR /app/apps/web
EXPOSE 3000
CMD ["pnpm", "start"]
