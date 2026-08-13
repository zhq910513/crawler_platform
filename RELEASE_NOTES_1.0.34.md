# crawler_platform 1.0.34

- 深度收敛控制端公网回调地址链路，删除旧 platformPublicUrl / platform.public_url / PLATFORM_PUBLIC_URL 兼容。
- CI 发布链路只接受 crawler_project.json.companyCode 和 CRAWLER_DISCOVERY_TOKEN，不再接受 companyId、serverCode/serverCodes 或旧平台链接变量。
- 执行节点接入命令改为 --control-plane-url，执行节点运行配置改为 AGENT_CONTROL_PLANE_URL。
- 服务器部署目标只在控制台选择，Git CI 只负责 build / push / register release。
