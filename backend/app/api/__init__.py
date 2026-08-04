from app.api import agents, alerts, companies, cron_previews, dashboard, operations, projects, releases, runs, sessions, servers, task_schedule_panels, tasks, users

routers = [
    sessions.router,
    users.router,
    companies.router,
    servers.router,
    agents.router,
    projects.router,
    tasks.router,
    task_schedule_panels.router,
    runs.router,
    cron_previews.router,
    releases.router,
    alerts.channel_router,
    alerts.alert_router,
    dashboard.router,
    operations.router,
]
