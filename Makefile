include .env

# Helper
PSQL = PGPASSWORD=$(PGPASSWORD) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)

db-reset:
	@echo "[DB] Drop all tables in $(DB_NAME)..."
	@$(PSQL) -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "[DB] All tables dropped."
	@echo "[DB] Run migrations..."
	@python3 -m infrastructure.railway.bootstrap
	@echo "[DB] Migrations done."

psql:
	@$(PSQL)
