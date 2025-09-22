# Config
DB_NAME ?= zorgwaard
DB_USER ?= zorgwaard
PGPASSWORD ?= zorgwaard
DB_HOST ?= 192.168.2.51
DB_PORT ?= 5438
SCHEMA_FILE ?= schema.sql

# Helper
PSQL = PGPASSWORD=$(PGPASSWORD) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)

# Doel: hele database leegmaken en schema opnieuw laden
reset-db:
	@echo "[DB] Droppen van alle tabellen in $(DB_NAME)..."
	@$(PSQL) -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "[DB] Inladen schema uit $(SCHEMA_FILE)..."
	@$(PSQL) -f $(SCHEMA_FILE)
	@echo "[DB] Klaar."

# Handige shortcut: alleen schema inladen
load-schema:
	@$(PSQL) -f $(SCHEMA_FILE)

# Handige shortcut: connectie openen
psql:
	@$(PSQL)
