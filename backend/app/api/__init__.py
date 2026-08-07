from app.api import account_status, agent_bootstrap, agents, alerts, companies, company_resources, cron_previews, dashboard, operations, projects, releases, runs, sessions, servers, system_settings, task_schedule_panels, tasks, users

routers = [
    sessions.router,
    users.router,
    companies.router,
    company_resources.router,
    servers.router,
    agents.router,
    account_status.router,
    agent_bootstrap.router,
    projects.router,
    tasks.router,
    task_schedule_panels.router,
    runs.router,
    cron_previews.router,
    releases.router,
    alerts.channel_router,
    alerts.alert_router,
    system_settings.router,
    dashboard.router,
    operations.router,
]
