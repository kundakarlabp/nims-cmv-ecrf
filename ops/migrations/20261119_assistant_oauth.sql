-- Additive OAuth/MCP state only. No clinical table or baseline changes.
BEGIN;
SELECT pg_advisory_xact_lock(18451119);

CREATE TABLE IF NOT EXISTS assistant_mcp_receipts (
	id VARCHAR(64) NOT NULL, 
	request_digest VARCHAR(64) NOT NULL, 
	result JSON, 
	PRIMARY KEY (id)
)

;

CREATE TABLE IF NOT EXISTS assistant_oauth_clients (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	redirects JSON NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE IF NOT EXISTS assistant_oauth_codes (
	digest VARCHAR(64) NOT NULL, 
	client_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	redirect_uri TEXT NOT NULL, 
	challenge VARCHAR(43) NOT NULL, 
	resource TEXT NOT NULL, 
	scope VARCHAR(100) NOT NULL, 
	credential_version VARCHAR(64) NOT NULL, 
	mfa_verified BOOLEAN NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	consumed BOOLEAN NOT NULL, 
	PRIMARY KEY (digest)
)

;

CREATE TABLE IF NOT EXISTS assistant_oauth_grants (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	client_id VARCHAR(64) NOT NULL, 
	resource TEXT NOT NULL, 
	scope VARCHAR(100) NOT NULL, 
	credential_version VARCHAR(64) NOT NULL, 
	mfa_verified BOOLEAN NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX IF NOT EXISTS ix_assistant_oauth_grants_user_id ON assistant_oauth_grants (user_id);

CREATE TABLE IF NOT EXISTS assistant_oauth_tokens (
	digest VARCHAR(64) NOT NULL, 
	grant_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(10) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	consumed BOOLEAN NOT NULL, 
	PRIMARY KEY (digest)
)

;
CREATE INDEX IF NOT EXISTS ix_assistant_oauth_tokens_grant_id ON assistant_oauth_tokens (grant_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.assistant_mcp_receipts, public.assistant_oauth_clients, public.assistant_oauth_codes, public.assistant_oauth_grants, public.assistant_oauth_tokens TO nims_clinical_app;
COMMIT;
