# crawler_platform 1.0.23 发布说明

## 类型

前端构建阻断修复 / 发布门禁增强。

## 修复内容

- 修复 `frontend/src/utils/dictionaries.ts` 中 `AVAILABLE` 重复定义导致 `vue-tsc` 报错 TS1117 的问题。
- 新增 `deploy/scripts/check-frontend-dictionary-duplicates.py`，在商业发布门禁阶段提前检查前端字典重复键。
- `commercial-release-gate.sh` 已接入前端字典重复键检查，避免同类问题再次等到前端镜像构建阶段才暴露。
- 版本统一递增到 1.0.23。

## 版本递增

- crawler_platform：1.0.22 → 1.0.23
- crawler_platform_spiders：保持 1.0.12，本轮未改动。
