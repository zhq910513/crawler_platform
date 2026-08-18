# crawler_platform v1.0.76 发布说明

v1.0.76 是前端依赖锁定完整性修复版，针对 v1.0.75 GitHub Actions 商业发布门禁中 `npm ci` fallback 到官方 npm 后仍因 `picocolors@1.1.2` 不存在而失败的问题进行收口。

## 修复点

1. **修复 package-lock 中错误的 picocolors 版本**
   - `picocolors` 从错误的 `1.1.2` 修正为可发布的 `1.1.1`。
   - `postcss` 对 `picocolors` 的依赖约束从 `^1.1.2` 修正为 `^1.1.1`。
   - `package-lock.json` 继续保持官方 `registry.npmjs.org` resolved 源，构建期由 Dockerfile 按 registry 参数临时规范化。

2. **新增前端 lockfile 完整性门禁**
   - 新增 `deploy/scripts/check-frontend-lockfile-integrity.py`。
   - 检查 `package-lock.json` 是否固化 `npmmirror/cdn.npmmirror`。
   - 检查已知不可下载版本，例如 `picocolors@1.1.2`。
   - 检查简单 npm semver 约束，避免 lockfile 中依赖约束与锁定版本不匹配。
   - 检查 resolved tarball 与锁定版本基本一致。

3. **商业发布门禁前置失败定位**
   - `commercial-release-gate.sh` 在前端 Docker build 之前先运行 lockfile 完整性检查。
   - 以后类似 lockfile 错误会在轻量门禁阶段失败，不再等到 Docker build 的 `npm ci` 阶段才暴露。

4. **版本策略**
   - 平台版本升级到 `1.0.76`。
   - Agent 独立版本保持 `1.1.2`。
   - 本版不触碰 Agent 生命周期和节点接入协议。

## 验证重点

- 后端契约测试新增前端 lockfile 完整性断言。
- `package-lock.json` 不再包含 `picocolors/-/picocolors-1.1.2.tgz`。
- `commercial-release-gate.sh` 已接入 `check-frontend-lockfile-integrity.py`。
- 本版修复的是发布依赖锁定错误，不改变运行时业务逻辑。
