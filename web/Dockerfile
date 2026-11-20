# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmjs.org
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine
ENV NGINX_ENVSUBST_FILTER=TOOLPLANNER_.*
ENV TOOLPLANNER_API_UPSTREAM=tool-planner-api:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=0755 05-toolplanner-resolver.envsh /docker-entrypoint.d/05-toolplanner-resolver.envsh
COPY --from=build /app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
