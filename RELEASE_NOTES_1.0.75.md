# crawler_platform v1.0.75 发布说明

## 版本定位

v1.0.75 是前端发布链路稳定性修复版，针对 GitHub Actions 商业发布门禁中 `npm ci` 依赖源 404 导致前端镜像构建失败的问题进行收口。

## 核心修复

1. **前端 Docker 构建增加 npm 源回退**
   - 默认先使用 `NPM_REGISTRY`。
   - 失败后自动切换 `NPM_FALLBACK_REGISTRY`，默认 `https://registry.npmjs.org`。
   - 发布门禁不再依赖单一 npm 镜像源。

2. **package-lock resolved 源治理**
   - 仓库中的 `frontend/package-lock.json` 使用官方 npm registry 作为 canonical resolved 源。
   - Docker 构建时按当前 registry 临时规范化 lockfile，不污染源码。

3. **发布门禁失败归因优化**
   - 前端镜像构建失败后，跳过 `/version.json` 连带检查。
   - 失败信息明确指向前端依赖安装、npm registry 或 tarball 下载阶段，避免制造第二个噪音失败。

4. **版本递增但 Agent 不变**
   - 平台版本升级到 `1.0.75`。
   - Agent 独立版本仍为 `1.1.2`，本版不触碰 Agent 生命周期。

## 验收重点

- `package-lock.json` 不再固化 `registry.npmmirror.com` 或 `cdn.npmmirror.com` resolved URL。
- `frontend/Dockerfile` 具备 npm fallback 构建路径。
- `commercial-release-gate.sh` 不再在前端构建失败后继续检查 `/version.json`。
- 平台 patch 不改变 Agent 独立版本。
