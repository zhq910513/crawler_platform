# v1.0.87 发布说明

## 目标

明确项目发布在平台构建中心未就绪时的正确边界：未登记 Release 继续阻断，已通过外部 CI 注册的 Release 可以继续部署到执行节点。

## 变更

- 平台发布流水线的构建阻断结果增加机器可读字段：
  - `mode=EXTERNAL_RELEASE_REQUIRED`
  - `supportedReleasePath=EXTERNAL_CI_RELEASE_REGISTRATION`
  - `blockedReasonCode=PLATFORM_BUILD_CENTER_NOT_READY`
  - `cicdGuideEndpoint=/api/v1/cicd/spider-projects/one-click-guide`
  - `registerEndpoint=/api/v1/discovered-projects`
  - `nextActions[]`
- 项目发布页在构建中心未就绪且未登记 Release 时，展示外部 CI 注册路径。
- 项目发布页增加“查看外部 CI 接入指引”入口，直接展示初始化命令、必须配置的密钥和注册后回到发布页的操作步骤。
- 保持强阻断：未登记 Release 不能绕过平台构建中心状态直接发布。

## 测试

- Python 编译检查通过。
- Shell `bash -n` 检查通过。
- 项目发布外部 CI 阻断路径回归测试通过。
- CI/CD 指引接口回归测试通过。
- 版本一致性检查通过。
- ZIP 解压 manifest 校验通过。

## 注意

v1.0.87 没有实现平台内构建执行器，也没有新增代码仓库读取凭据或镜像仓库推送凭据。当前推荐部署测试路径仍是：爬虫项目仓库外部 CI 构建镜像并注册 Release，然后平台发布页部署已登记版本。
