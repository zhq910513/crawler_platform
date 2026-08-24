# CI 失败复盘与整改记录 v1.0.80

## CI 日志暴露的问题

1. 后端发布包卫生测试失败：`tests/test_release_package_hygiene_1079.py::test_release_tree_does_not_contain_local_database_files` 检出 `crawler_platform_dev.db`。
2. 前端镜像构建失败：`CompanyResourcesPage.vue` 第 28 行模板使用 `testStatusOptions`，但 `<script setup>` 中没有定义该变量，`vue-tsc --noEmit` 报 `TS2339`。

## 本轮整改

1. v1.0.80 发布包继续排除本地数据库文件，并保留 `.gitignore` 的 `*.db` / `*.sqlite` / `*.sqlite3` 规则。
2. 修复 `frontend/src/views/CompanyResourcesPage.vue`，新增 `testStatusOptions` 常量，取值与现有 `testText()` 状态文案保持一致。
3. 新增前端页面静态契约测试，确保模板引用的测试状态选项在脚本中定义。
4. 版本号统一提升到 `1.0.80`。

## 注意事项

如果远端 Git 仓库中已经跟踪过 `crawler_platform_dev.db`，仅有 `.gitignore` 不会自动删除历史跟踪文件。提交本轮代码时必须确认该文件处于删除状态，可用以下命令检查：

```bash
git status --short crawler_platform_dev.db
git ls-files crawler_platform_dev.db
```

若仍被跟踪，应执行：

```bash
git rm crawler_platform_dev.db
```
