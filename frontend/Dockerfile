FROM node:22-alpine AS build
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_FALLBACK_REGISTRY=https://registry.npmjs.org
ARG APP_VERSION=unknown
ARG APP_GIT_COMMIT=unknown
ARG APP_BUILD_TIME=unknown
ENV VITE_APP_VERSION=${APP_VERSION}
ENV VITE_APP_GIT_COMMIT=${APP_GIT_COMMIT}
ENV VITE_APP_BUILD_TIME=${APP_BUILD_TIME}
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN set -eu; \
    cp package-lock.json package-lock.original.json; \
    npm_install_with_registry() { \
      registry="$1"; \
      cp package-lock.original.json package-lock.json; \
      npm config set registry "$registry"; \
      node scripts/normalize-package-lock-registry.cjs "$registry"; \
      npm ci --no-audit --no-fund; \
    }; \
    if npm_install_with_registry "$NPM_REGISTRY"; then \
      echo "npm ci succeeded with primary registry: $NPM_REGISTRY"; \
    else \
      echo "WARN: npm ci failed with primary registry: $NPM_REGISTRY; retrying with fallback registry: $NPM_FALLBACK_REGISTRY" >&2; \
      npm cache clean --force >/dev/null 2>&1 || true; \
      npm_install_with_registry "$NPM_FALLBACK_REGISTRY"; \
    fi
COPY . .
RUN if echo "$APP_VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then npm version "$APP_VERSION" --no-git-tag-version --allow-same-version; fi \
    && npm run build \
    && node -e "const fs=require('fs'); const data={appName:'crawler_platform_web',version:process.env.VITE_APP_VERSION||'unknown',gitCommit:process.env.VITE_APP_GIT_COMMIT||'unknown',buildTime:process.env.VITE_APP_BUILD_TIME||'unknown'}; fs.writeFileSync('/app/dist/version.json', JSON.stringify(data, null, 2));"

FROM nginx:1.27-alpine
ARG APK_MIRROR=mirrors.aliyun.com
RUN if [ -n "$APK_MIRROR" ]; then sed -i "s#dl-cdn.alpinelinux.org#${APK_MIRROR}#g" /etc/apk/repositories; fi
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
