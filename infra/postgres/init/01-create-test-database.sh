#!/bin/sh
# Runs once, when the database volume is first created.
# Creates the separate database used by the automated test suite.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE DATABASE "${POSTGRES_TEST_DB}" OWNER "${POSTGRES_USER}";
SQL
