SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;


CREATE TABLE crawler_project (
	project_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_code VARCHAR(100) NOT NULL, 
	project_name VARCHAR(150) NOT NULL, 
	registry VARCHAR(255) NOT NULL, 
	repository VARCHAR(255) NOT NULL, 
	default_branch VARCHAR(100) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_crawler_project_status ON crawler_project (status);

CREATE UNIQUE INDEX ix_crawler_project_project_code ON crawler_project (project_code);


CREATE TABLE crawler_server (
	server_id BIGINT NOT NULL AUTO_INCREMENT, 
	server_code VARCHAR(100) NOT NULL, 
	server_name VARCHAR(100) NOT NULL, 
	server_ip VARCHAR(128) NOT NULL, 
	environment VARCHAR(30) NOT NULL, 
	max_container_slots INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE UNIQUE INDEX ix_crawler_server_server_code ON crawler_server (server_code);

CREATE INDEX ix_crawler_server_environment ON crawler_server (environment);

CREATE INDEX ix_crawler_server_status ON crawler_server (status);


CREATE TABLE sys_config (
	config_id BIGINT NOT NULL AUTO_INCREMENT, 
	config_key VARCHAR(100) NOT NULL, 
	config_name VARCHAR(100) NOT NULL, 
	config_value TEXT NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (config_id), 
	UNIQUE (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE sys_secret (
	secret_id BIGINT NOT NULL AUTO_INCREMENT, 
	secret_code VARCHAR(100) NOT NULL, 
	secret_name VARCHAR(100) NOT NULL, 
	encrypted_value TEXT NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	enabled BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (secret_id), 
	UNIQUE (secret_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE sys_user (
	user_id BIGINT NOT NULL AUTO_INCREMENT, 
	user_name VARCHAR(50) NOT NULL, 
	nick_name VARCHAR(50) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role_type VARCHAR(20) NOT NULL, 
	status BOOL NOT NULL, 
	last_login_ip VARCHAR(128), 
	last_login_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_sys_user_role_type ON sys_user (role_type);

CREATE INDEX ix_sys_user_status ON sys_user (status);

CREATE UNIQUE INDEX ix_sys_user_user_name ON sys_user (user_name);


CREATE TABLE crawler_agent (
	agent_id BIGINT NOT NULL AUTO_INCREMENT, 
	server_id BIGINT NOT NULL, 
	agent_code VARCHAR(100) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	agent_version VARCHAR(50) NOT NULL, 
	hostname VARCHAR(255) NOT NULL, 
	os_name VARCHAR(255) NOT NULL, 
	python_version VARCHAR(100) NOT NULL, 
	docker_version VARCHAR(100) NOT NULL, 
	cpu_count INTEGER NOT NULL, 
	memory_total_bytes BIGINT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	last_ip VARCHAR(128) NOT NULL, 
	started_at DATETIME, 
	last_heartbeat_at DATETIME, 
	last_error TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (agent_id), 
	UNIQUE (server_id), 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id) ON DELETE CASCADE, 
	UNIQUE (agent_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_crawler_agent_status ON crawler_agent (status);

CREATE INDEX ix_crawler_agent_last_heartbeat_at ON crawler_agent (last_heartbeat_at);


CREATE TABLE crawler_image_version (
	image_version_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	image_tag VARCHAR(255) NOT NULL, 
	image_digest VARCHAR(255) NOT NULL, 
	git_branch VARCHAR(100) NOT NULL, 
	git_commit VARCHAR(100) NOT NULL, 
	pipeline_id VARCHAR(100) NOT NULL, 
	build_status VARCHAR(20) NOT NULL, 
	build_url VARCHAR(500) NOT NULL, 
	built_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (image_version_id), 
	CONSTRAINT uk_project_image_digest UNIQUE (project_id, image_digest), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_image_project_built ON crawler_image_version (project_id, built_at);

CREATE INDEX ix_crawler_image_version_build_status ON crawler_image_version (build_status);


CREATE TABLE crawler_server_metric (
	metric_id BIGINT NOT NULL AUTO_INCREMENT, 
	server_id BIGINT NOT NULL, 
	cpu_percent NUMERIC(6, 2) NOT NULL, 
	memory_percent NUMERIC(6, 2) NOT NULL, 
	disk_percent NUMERIC(6, 2) NOT NULL, 
	load_1m NUMERIC(10, 2) NOT NULL, 
	load_5m NUMERIC(10, 2) NOT NULL, 
	network_sent_bytes BIGINT NOT NULL, 
	network_received_bytes BIGINT NOT NULL, 
	running_task_count INTEGER NOT NULL, 
	process_count INTEGER NOT NULL, 
	docker_image_bytes BIGINT NOT NULL, 
	recorded_at DATETIME NOT NULL, 
	PRIMARY KEY (metric_id), 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_crawler_server_metric_recorded_at ON crawler_server_metric (recorded_at);

CREATE INDEX idx_metric_server_time ON crawler_server_metric (server_id, recorded_at);


CREATE TABLE crawler_task (
	task_id BIGINT NOT NULL AUTO_INCREMENT, 
	task_code VARCHAR(120) NOT NULL, 
	task_name VARCHAR(200) NOT NULL, 
	project_id BIGINT NOT NULL, 
	platform VARCHAR(100) NOT NULL, 
	task_group VARCHAR(100) NOT NULL, 
	developer VARCHAR(100) NOT NULL, 
	executor_type VARCHAR(30) NOT NULL, 
	entrypoint VARCHAR(500) NOT NULL, 
	arguments JSON NOT NULL, 
	keyword_arguments JSON NOT NULL, 
	related_tables JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description VARCHAR(1000) NOT NULL, 
	created_by BIGINT, 
	updated_by BIGINT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (task_id), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id), 
	FOREIGN KEY(created_by) REFERENCES sys_user (user_id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by) REFERENCES sys_user (user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE UNIQUE INDEX ix_crawler_task_task_code ON crawler_task (task_code);

CREATE INDEX ix_crawler_task_task_group ON crawler_task (task_group);

CREATE INDEX ix_crawler_task_status ON crawler_task (status);

CREATE INDEX ix_crawler_task_platform ON crawler_task (platform);


CREATE TABLE sys_login_log (
	login_id BIGINT NOT NULL AUTO_INCREMENT, 
	user_id BIGINT, 
	user_name VARCHAR(50) NOT NULL, 
	ip_address VARCHAR(128) NOT NULL, 
	user_agent VARCHAR(500) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	message VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (login_id), 
	FOREIGN KEY(user_id) REFERENCES sys_user (user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_sys_login_log_status ON sys_login_log (status);

CREATE INDEX ix_sys_login_log_created_at ON sys_login_log (created_at);


CREATE TABLE sys_operation_log (
	operation_id BIGINT NOT NULL AUTO_INCREMENT, 
	user_id BIGINT, 
	user_name VARCHAR(50) NOT NULL, 
	operation_type VARCHAR(50) NOT NULL, 
	resource_type VARCHAR(50) NOT NULL, 
	resource_id VARCHAR(100) NOT NULL, 
	request_method VARCHAR(10) NOT NULL, 
	request_path VARCHAR(500) NOT NULL, 
	before_data JSON, 
	after_data JSON, 
	ip_address VARCHAR(128) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	error_message TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (operation_id), 
	FOREIGN KEY(user_id) REFERENCES sys_user (user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_sys_operation_log_operation_type ON sys_operation_log (operation_type);

CREATE INDEX ix_sys_operation_log_resource_type ON sys_operation_log (resource_type);

CREATE INDEX ix_sys_operation_log_status ON sys_operation_log (status);

CREATE INDEX ix_sys_operation_log_created_at ON sys_operation_log (created_at);


CREATE TABLE crawler_release_channel (
	channel_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	channel_name VARCHAR(50) NOT NULL, 
	image_version_id BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (channel_id), 
	CONSTRAINT uk_project_channel UNIQUE (project_id, channel_name), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	FOREIGN KEY(image_version_id) REFERENCES crawler_image_version (image_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE crawler_task_runtime (
	runtime_id BIGINT NOT NULL AUTO_INCREMENT, 
	task_id BIGINT NOT NULL, 
	image_policy VARCHAR(30) NOT NULL, 
	fixed_image_version_id BIGINT, 
	release_channel VARCHAR(50) NOT NULL, 
	pull_policy VARCHAR(30) NOT NULL, 
	container_command JSON NOT NULL, 
	container_working_dir VARCHAR(500) NOT NULL, 
	environment_variables JSON NOT NULL, 
	secret_refs JSON NOT NULL, 
	volume_mounts JSON NOT NULL, 
	network_mode VARCHAR(100) NOT NULL, 
	cpu_limit NUMERIC(6, 2) NOT NULL, 
	memory_limit_mb INTEGER NOT NULL, 
	shm_size_mb INTEGER NOT NULL, 
	pids_limit INTEGER NOT NULL, 
	stop_grace_seconds INTEGER NOT NULL, 
	auto_remove BOOL NOT NULL, 
	keep_failed_container BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (runtime_id), 
	UNIQUE (task_id), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id) ON DELETE CASCADE, 
	FOREIGN KEY(fixed_image_version_id) REFERENCES crawler_image_version (image_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE crawler_task_schedule (
	schedule_id BIGINT NOT NULL AUTO_INCREMENT, 
	task_id BIGINT NOT NULL, 
	schedule_type VARCHAR(20) NOT NULL, 
	cron_expression VARCHAR(100) NOT NULL, 
	timezone VARCHAR(100) NOT NULL, 
	misfire_policy VARCHAR(30) NOT NULL, 
	max_concurrency INTEGER NOT NULL, 
	overlap_policy VARCHAR(20) NOT NULL, 
	timeout_seconds INTEGER NOT NULL, 
	max_retry_count INTEGER NOT NULL, 
	retry_interval_seconds INTEGER NOT NULL, 
	retry_backoff VARCHAR(20) NOT NULL, 
	enabled BOOL NOT NULL, 
	next_run_at DATETIME, 
	last_triggered_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (schedule_id), 
	UNIQUE (task_id), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_crawler_task_schedule_enabled ON crawler_task_schedule (enabled);

CREATE INDEX ix_crawler_task_schedule_next_run_at ON crawler_task_schedule (next_run_at);


CREATE TABLE crawler_task_target (
	target_id BIGINT NOT NULL AUTO_INCREMENT, 
	task_id BIGINT NOT NULL, 
	server_id BIGINT NOT NULL, 
	priority INTEGER NOT NULL, 
	enabled BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (target_id), 
	CONSTRAINT uk_task_server UNIQUE (task_id, server_id), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id) ON DELETE CASCADE, 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE crawler_task_run (
	run_id BIGINT NOT NULL AUTO_INCREMENT, 
	run_no VARCHAR(50) NOT NULL, 
	task_id BIGINT NOT NULL, 
	schedule_id BIGINT, 
	server_id BIGINT NOT NULL, 
	agent_id BIGINT, 
	trigger_type VARCHAR(20) NOT NULL, 
	triggered_by BIGINT, 
	scheduled_at DATETIME NOT NULL, 
	queued_at DATETIME, 
	claimed_at DATETIME, 
	started_at DATETIME, 
	finished_at DATETIME, 
	status VARCHAR(30) NOT NULL, 
	desired_action VARCHAR(20) NOT NULL, 
	attempt INTEGER NOT NULL, 
	parent_run_id BIGINT, 
	container_id VARCHAR(100) NOT NULL, 
	container_name VARCHAR(255) NOT NULL, 
	image_name VARCHAR(500) NOT NULL, 
	image_tag VARCHAR(255) NOT NULL, 
	image_digest VARCHAR(255) NOT NULL, 
	git_commit VARCHAR(100) NOT NULL, 
	exit_code INTEGER, 
	duration_ms BIGINT, 
	error_type VARCHAR(100) NOT NULL, 
	error_message TEXT NOT NULL, 
	log_path VARCHAR(1000) NOT NULL, 
	log_size_bytes BIGINT NOT NULL, 
	last_log_at DATETIME, 
	heartbeat_at DATETIME, 
	lease_expires_at DATETIME, 
	inspect_summary JSON, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (run_id), 
	CONSTRAINT uk_schedule_time_attempt UNIQUE (schedule_id, scheduled_at, attempt), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id), 
	FOREIGN KEY(schedule_id) REFERENCES crawler_task_schedule (schedule_id), 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id), 
	FOREIGN KEY(agent_id) REFERENCES crawler_agent (agent_id), 
	FOREIGN KEY(triggered_by) REFERENCES sys_user (user_id) ON DELETE SET NULL, 
	FOREIGN KEY(parent_run_id) REFERENCES crawler_task_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_run_task_created ON crawler_task_run (task_id, created_at);

CREATE INDEX idx_run_status_lease ON crawler_task_run (status, lease_expires_at);

CREATE INDEX ix_crawler_task_run_status ON crawler_task_run (status);

CREATE INDEX idx_run_server_status ON crawler_task_run (server_id, status);

CREATE INDEX ix_crawler_task_run_scheduled_at ON crawler_task_run (scheduled_at);

CREATE UNIQUE INDEX ix_crawler_task_run_run_no ON crawler_task_run (run_no);


CREATE TABLE crawler_container_event (
	event_id BIGINT NOT NULL AUTO_INCREMENT, 
	run_id BIGINT NOT NULL, 
	server_id BIGINT NOT NULL, 
	container_id VARCHAR(100) NOT NULL, 
	container_name VARCHAR(255) NOT NULL, 
	event_type VARCHAR(50) NOT NULL, 
	event_action VARCHAR(50) NOT NULL, 
	exit_code INTEGER, 
	event_message TEXT NOT NULL, 
	occurred_at DATETIME NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(run_id) REFERENCES crawler_task_run (run_id) ON DELETE CASCADE, 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_container_event_run_time ON crawler_container_event (run_id, occurred_at);

SET FOREIGN_KEY_CHECKS = 1;