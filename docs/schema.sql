-- Auto-generated from SQLAlchemy models for documentation. Use Alembic migrations for production upgrades.


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
)

;

CREATE INDEX ix_crawler_server_environment ON crawler_server (environment);

CREATE UNIQUE INDEX ix_crawler_server_server_code ON crawler_server (server_code);

CREATE INDEX ix_crawler_server_status ON crawler_server (status);


CREATE TABLE crawler_spider_release (
	release_id BIGINT NOT NULL AUTO_INCREMENT, 
	app_name VARCHAR(100) NOT NULL, 
	version VARCHAR(50) NOT NULL, 
	image_repository VARCHAR(500) NOT NULL, 
	image_tag VARCHAR(255) NOT NULL, 
	image_digest VARCHAR(255) NOT NULL, 
	git_commit VARCHAR(100) NOT NULL, 
	manifest_json JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	published_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (release_id), 
	CONSTRAINT uk_spider_app_version UNIQUE (app_name, version), 
	CONSTRAINT uk_spider_image_digest UNIQUE (image_repository, image_digest)
)

;

CREATE INDEX ix_crawler_spider_release_app_name ON crawler_spider_release (app_name);

CREATE INDEX ix_crawler_spider_release_status ON crawler_spider_release (status);


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
)

;


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
)

;

CREATE INDEX ix_sys_user_role_type ON sys_user (role_type);

CREATE INDEX ix_sys_user_status ON sys_user (status);

CREATE UNIQUE INDEX ix_sys_user_user_name ON sys_user (user_name);


CREATE TABLE crawler_agent (
	agent_id BIGINT NOT NULL AUTO_INCREMENT, 
	server_id BIGINT NOT NULL, 
	agent_code VARCHAR(100) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	protocol_version VARCHAR(20) NOT NULL, 
	instance_id VARCHAR(100) NOT NULL, 
	agent_version VARCHAR(50) NOT NULL, 
	hostname VARCHAR(255) NOT NULL, 
	os_name VARCHAR(255) NOT NULL, 
	python_version VARCHAR(100) NOT NULL, 
	docker_version VARCHAR(100) NOT NULL, 
	cpu_count INTEGER NOT NULL, 
	memory_total_bytes BIGINT NOT NULL, 
	capabilities_json JSON NOT NULL, 
	labels_json JSON NOT NULL, 
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
)

;

CREATE INDEX ix_crawler_agent_last_heartbeat_at ON crawler_agent (last_heartbeat_at);

CREATE INDEX ix_crawler_agent_status ON crawler_agent (status);


CREATE TABLE crawler_company (
	company_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_code VARCHAR(100) NOT NULL, 
	company_name VARCHAR(150) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	created_by BIGINT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (company_id), 
	FOREIGN KEY(created_by) REFERENCES sys_user (user_id) ON DELETE SET NULL
)

;

CREATE UNIQUE INDEX ix_crawler_company_company_code ON crawler_company (company_code);

CREATE INDEX ix_crawler_company_status ON crawler_company (status);


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
)

;

CREATE INDEX idx_metric_server_time ON crawler_server_metric (server_id, recorded_at);

CREATE INDEX ix_crawler_server_metric_recorded_at ON crawler_server_metric (recorded_at);


CREATE TABLE crawler_spider_entry (
	entry_id BIGINT NOT NULL AUTO_INCREMENT, 
	release_id BIGINT NOT NULL, 
	task_name VARCHAR(200) NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	description VARCHAR(1000) NOT NULL, 
	image_profile VARCHAR(20) NOT NULL, 
	parameter_schema JSON NOT NULL, 
	required_resources JSON NOT NULL, 
	default_timeout_seconds INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (entry_id), 
	CONSTRAINT uk_release_task_name UNIQUE (release_id, task_name), 
	FOREIGN KEY(release_id) REFERENCES crawler_spider_release (release_id) ON DELETE CASCADE
)

;

CREATE INDEX ix_crawler_spider_entry_task_name ON crawler_spider_entry (task_name);


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
)

;

CREATE INDEX ix_sys_login_log_created_at ON sys_login_log (created_at);

CREATE INDEX ix_sys_login_log_status ON sys_login_log (status);


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
)

;

CREATE INDEX ix_sys_operation_log_created_at ON sys_operation_log (created_at);

CREATE INDEX ix_sys_operation_log_operation_type ON sys_operation_log (operation_type);

CREATE INDEX ix_sys_operation_log_resource_type ON sys_operation_log (resource_type);

CREATE INDEX ix_sys_operation_log_status ON sys_operation_log (status);


CREATE TABLE crawler_company_member (
	member_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (member_id), 
	CONSTRAINT uk_company_user UNIQUE (company_id, user_id), 
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES sys_user (user_id) ON DELETE CASCADE
)

;

CREATE INDEX ix_crawler_company_member_role ON crawler_company_member (`role`);


CREATE TABLE crawler_project (
	project_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_id BIGINT NOT NULL, 
	project_code VARCHAR(100) NOT NULL, 
	project_name VARCHAR(150) NOT NULL, 
	registry VARCHAR(255) NOT NULL, 
	repository VARCHAR(255) NOT NULL, 
	default_branch VARCHAR(100) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	created_by BIGINT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (project_id), 
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(created_by) REFERENCES sys_user (user_id) ON DELETE SET NULL
)

;

CREATE INDEX ix_crawler_project_company_id ON crawler_project (company_id);

CREATE UNIQUE INDEX ix_crawler_project_project_code ON crawler_project (project_code);

CREATE INDEX ix_crawler_project_status ON crawler_project (status);


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
)

;

CREATE INDEX ix_crawler_image_version_build_status ON crawler_image_version (build_status);


CREATE TABLE crawler_project_member (
	member_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (member_id), 
	CONSTRAINT uk_project_user UNIQUE (project_id, user_id), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES sys_user (user_id) ON DELETE CASCADE
)

;

CREATE INDEX ix_crawler_project_member_role ON crawler_project_member (`role`);


CREATE TABLE crawler_resource_connection (
	connection_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_id BIGINT NOT NULL, 
	project_id BIGINT, 
	connection_code VARCHAR(100) NOT NULL, 
	connection_name VARCHAR(150) NOT NULL, 
	resource_type VARCHAR(20) NOT NULL, 
	config_json JSON NOT NULL, 
	enabled BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (connection_id), 
	CONSTRAINT uk_resource_connection_scope UNIQUE (company_id, project_id, connection_code), 
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id) ON DELETE CASCADE, 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE
)

;


CREATE TABLE crawler_task (
	task_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_id BIGINT NOT NULL, 
	task_code VARCHAR(120) NOT NULL, 
	task_name VARCHAR(200) NOT NULL, 
	project_id BIGINT NOT NULL, 
	spider_task_name VARCHAR(200) NOT NULL, 
	platform VARCHAR(100) NOT NULL, 
	task_group VARCHAR(100) NOT NULL, 
	developer VARCHAR(100) NOT NULL, 
	parameters JSON NOT NULL, 
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
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id), 
	FOREIGN KEY(created_by) REFERENCES sys_user (user_id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by) REFERENCES sys_user (user_id) ON DELETE SET NULL
)

;

CREATE INDEX ix_crawler_task_company_id ON crawler_task (company_id);

CREATE INDEX ix_crawler_task_platform ON crawler_task (platform);

CREATE INDEX ix_crawler_task_spider_task_name ON crawler_task (spider_task_name);

CREATE INDEX ix_crawler_task_status ON crawler_task (status);

CREATE UNIQUE INDEX ix_crawler_task_task_code ON crawler_task (task_code);

CREATE INDEX ix_crawler_task_task_group ON crawler_task (task_group);


CREATE TABLE sys_secret (
	secret_id BIGINT NOT NULL AUTO_INCREMENT, 
	company_id BIGINT, 
	project_id BIGINT, 
	secret_code VARCHAR(100) NOT NULL, 
	secret_name VARCHAR(100) NOT NULL, 
	encrypted_value TEXT NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	enabled BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (secret_id), 
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id) ON DELETE CASCADE, 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	UNIQUE (secret_code)
)

;

CREATE INDEX ix_sys_secret_company_id ON sys_secret (company_id);

CREATE INDEX ix_sys_secret_project_id ON sys_secret (project_id);


CREATE TABLE crawler_project_secret_binding (
	binding_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	logical_name VARCHAR(200) NOT NULL, 
	secret_id BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (binding_id), 
	CONSTRAINT uk_project_secret_logical UNIQUE (project_id, logical_name), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	FOREIGN KEY(secret_id) REFERENCES sys_secret (secret_id) ON DELETE CASCADE
)

;


CREATE TABLE crawler_release_channel (
	channel_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	channel_name VARCHAR(50) NOT NULL, 
	image_version_id BIGINT, 
	spider_release_id BIGINT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (channel_id), 
	CONSTRAINT uk_project_channel UNIQUE (project_id, channel_name), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	FOREIGN KEY(image_version_id) REFERENCES crawler_image_version (image_version_id), 
	FOREIGN KEY(spider_release_id) REFERENCES crawler_spider_release (release_id)
)

;


CREATE TABLE crawler_resource_database (
	database_id BIGINT NOT NULL AUTO_INCREMENT, 
	connection_id BIGINT NOT NULL, 
	database_code VARCHAR(100) NOT NULL, 
	database_name VARCHAR(200) NOT NULL, 
	config_json JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (database_id), 
	CONSTRAINT uk_resource_database UNIQUE (connection_id, database_code), 
	FOREIGN KEY(connection_id) REFERENCES crawler_resource_connection (connection_id) ON DELETE CASCADE
)

;


CREATE TABLE crawler_task_runtime (
	runtime_id BIGINT NOT NULL AUTO_INCREMENT, 
	task_id BIGINT NOT NULL, 
	image_policy VARCHAR(30) NOT NULL, 
	fixed_image_version_id BIGINT, 
	fixed_spider_release_id BIGINT, 
	release_channel VARCHAR(50) NOT NULL, 
	pull_policy VARCHAR(30) NOT NULL, 
	cpu_limit NUMERIC(6, 2) NOT NULL, 
	memory_limit_mb INTEGER NOT NULL, 
	shm_size_mb INTEGER NOT NULL, 
	pids_limit INTEGER NOT NULL, 
	stop_grace_seconds INTEGER NOT NULL, 
	auto_remove BOOL NOT NULL, 
	keep_failed_container BOOL NOT NULL, 
	container_command JSON NOT NULL, 
	container_working_dir VARCHAR(500) NOT NULL, 
	environment_variables JSON NOT NULL, 
	secret_refs JSON NOT NULL, 
	volume_mounts JSON NOT NULL, 
	network_mode VARCHAR(100) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (runtime_id), 
	UNIQUE (task_id), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id) ON DELETE CASCADE, 
	FOREIGN KEY(fixed_image_version_id) REFERENCES crawler_image_version (image_version_id), 
	FOREIGN KEY(fixed_spider_release_id) REFERENCES crawler_spider_release (release_id)
)

;


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
)

;

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
)

;


CREATE TABLE crawler_resource_object (
	object_id BIGINT NOT NULL AUTO_INCREMENT, 
	database_id BIGINT NOT NULL, 
	object_code VARCHAR(120) NOT NULL, 
	object_name VARCHAR(200) NOT NULL, 
	object_type VARCHAR(30) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (object_id), 
	CONSTRAINT uk_resource_object UNIQUE (database_id, object_code), 
	FOREIGN KEY(database_id) REFERENCES crawler_resource_database (database_id) ON DELETE CASCADE
)

;


CREATE TABLE crawler_task_run (
	run_id BIGINT NOT NULL AUTO_INCREMENT, 
	run_no VARCHAR(50) NOT NULL, 
	company_id BIGINT NOT NULL, 
	project_id BIGINT NOT NULL, 
	task_id BIGINT NOT NULL, 
	schedule_id BIGINT, 
	server_id BIGINT NOT NULL, 
	agent_id BIGINT, 
	spider_release_id BIGINT, 
	spider_entry_id BIGINT, 
	trigger_type VARCHAR(20) NOT NULL, 
	triggered_by BIGINT, 
	scheduled_at DATETIME NOT NULL, 
	queued_at DATETIME, 
	assigned_at DATETIME, 
	starting_at DATETIME, 
	started_at DATETIME, 
	cancel_requested_at DATETIME, 
	finished_at DATETIME, 
	lost_at DATETIME, 
	status VARCHAR(30) NOT NULL, 
	desired_action VARCHAR(20) NOT NULL, 
	attempt INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	parent_run_id BIGINT, 
	root_run_id BIGINT, 
	lease_token VARCHAR(128) NOT NULL, 
	lease_expires_at DATETIME, 
	heartbeat_at DATETIME, 
	container_id VARCHAR(100) NOT NULL, 
	container_name VARCHAR(255) NOT NULL, 
	image_name VARCHAR(500) NOT NULL, 
	image_tag VARCHAR(255) NOT NULL, 
	image_digest VARCHAR(255) NOT NULL, 
	git_commit VARCHAR(100) NOT NULL, 
	exit_code INTEGER, 
	oom_killed BOOL NOT NULL, 
	duration_ms BIGINT, 
	error_type VARCHAR(100) NOT NULL, 
	error_message TEXT NOT NULL, 
	last_error_event_id VARCHAR(100) NOT NULL, 
	last_error_code VARCHAR(200) NOT NULL, 
	last_error_type VARCHAR(200) NOT NULL, 
	last_error_message TEXT NOT NULL, 
	last_error_at DATETIME, 
	last_error_log_seq BIGINT, 
	terminal_error_code VARCHAR(200) NOT NULL, 
	terminal_error_type VARCHAR(200) NOT NULL, 
	terminal_error_message TEXT NOT NULL, 
	terminal_error_retryable BOOL NOT NULL, 
	terminal_error_json JSON, 
	result_json JSON, 
	metrics_json JSON, 
	task_spec_json JSON, 
	resource_manifest_json JSON, 
	runtime_json JSON, 
	log_path VARCHAR(1000) NOT NULL, 
	log_size_bytes BIGINT NOT NULL, 
	last_log_at DATETIME, 
	stdout_ack_seq BIGINT NOT NULL, 
	stderr_ack_seq BIGINT NOT NULL, 
	inspect_summary JSON, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (run_id), 
	CONSTRAINT uk_schedule_time_attempt UNIQUE (schedule_id, scheduled_at, attempt), 
	CONSTRAINT uk_run_parent_retry UNIQUE (parent_run_id), 
	FOREIGN KEY(company_id) REFERENCES crawler_company (company_id), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id), 
	FOREIGN KEY(task_id) REFERENCES crawler_task (task_id), 
	FOREIGN KEY(schedule_id) REFERENCES crawler_task_schedule (schedule_id), 
	FOREIGN KEY(server_id) REFERENCES crawler_server (server_id), 
	FOREIGN KEY(agent_id) REFERENCES crawler_agent (agent_id), 
	FOREIGN KEY(spider_release_id) REFERENCES crawler_spider_release (release_id), 
	FOREIGN KEY(spider_entry_id) REFERENCES crawler_spider_entry (entry_id), 
	FOREIGN KEY(triggered_by) REFERENCES sys_user (user_id) ON DELETE SET NULL, 
	FOREIGN KEY(parent_run_id) REFERENCES crawler_task_run (run_id), 
	FOREIGN KEY(root_run_id) REFERENCES crawler_task_run (run_id)
)

;

CREATE INDEX idx_run_project_created ON crawler_task_run (project_id, created_at);

CREATE INDEX idx_run_server_status ON crawler_task_run (server_id, status);

CREATE INDEX idx_run_status_lease ON crawler_task_run (status, lease_expires_at);

CREATE INDEX ix_crawler_task_run_company_id ON crawler_task_run (company_id);

CREATE INDEX ix_crawler_task_run_project_id ON crawler_task_run (project_id);

CREATE UNIQUE INDEX ix_crawler_task_run_run_no ON crawler_task_run (run_no);

CREATE INDEX ix_crawler_task_run_scheduled_at ON crawler_task_run (scheduled_at);

CREATE INDEX ix_crawler_task_run_status ON crawler_task_run (status);


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
)

;

CREATE INDEX idx_container_event_run_time ON crawler_container_event (run_id, occurred_at);


CREATE TABLE crawler_project_resource_binding (
	binding_id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	logical_name VARCHAR(200) NOT NULL, 
	resource_kind VARCHAR(30) NOT NULL, 
	connection_id BIGINT, 
	database_id BIGINT, 
	object_id BIGINT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (binding_id), 
	CONSTRAINT uk_project_resource_logical UNIQUE (project_id, logical_name), 
	FOREIGN KEY(project_id) REFERENCES crawler_project (project_id) ON DELETE CASCADE, 
	FOREIGN KEY(connection_id) REFERENCES crawler_resource_connection (connection_id) ON DELETE CASCADE, 
	FOREIGN KEY(database_id) REFERENCES crawler_resource_database (database_id) ON DELETE CASCADE, 
	FOREIGN KEY(object_id) REFERENCES crawler_resource_object (object_id) ON DELETE CASCADE
)

;


CREATE TABLE crawler_task_run_event (
	event_id BIGINT NOT NULL AUTO_INCREMENT, 
	run_id BIGINT NOT NULL, 
	event_uid VARCHAR(100) NOT NULL, 
	stream VARCHAR(20) NOT NULL, 
	seq BIGINT, 
	level VARCHAR(20) NOT NULL, 
	event_name VARCHAR(100) NOT NULL, 
	message TEXT NOT NULL, 
	error_code VARCHAR(200) NOT NULL, 
	error_type VARCHAR(200) NOT NULL, 
	retryable BOOL NOT NULL, 
	context_json JSON, 
	payload_json JSON, 
	occurred_at DATETIME NOT NULL, 
	received_at DATETIME NOT NULL, 
	PRIMARY KEY (event_id), 
	CONSTRAINT uk_run_event_uid UNIQUE (run_id, event_uid), 
	CONSTRAINT uk_run_stream_seq UNIQUE (run_id, stream, seq), 
	FOREIGN KEY(run_id) REFERENCES crawler_task_run (run_id) ON DELETE CASCADE
)

;

CREATE INDEX idx_run_event_time ON crawler_task_run_event (run_id, event_id);

CREATE INDEX ix_crawler_task_run_event_level ON crawler_task_run_event (level);

CREATE INDEX ix_crawler_task_run_event_occurred_at ON crawler_task_run_event (occurred_at);
