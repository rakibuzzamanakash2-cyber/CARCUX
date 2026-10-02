# CARCUX frontend: Next.js standalone server.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Run as an unprivileged user.
RUN addgroup -S carcux && adduser -S carcux -G carcux
COPY --from=build --chown=carcux:carcux /app/.next/standalone ./
COPY --from=build --chown=carcux:carcux /app/.next/static ./.next/static
COPY --from=build --chown=carcux:carcux /app/public ./public
USER carcux
EXPOSE 3000
CMD ["node", "server.js"]
