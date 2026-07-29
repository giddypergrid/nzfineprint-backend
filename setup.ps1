# One-time full setup: create the table, load all notices, then build the indexes.
# Run from the repo root: .\setup.ps1
# Indexes go LAST on purpose — bulk-inserting into an already-indexed table is much slower.

docker compose up -d db
.\Prep\db\apply.ps1 -Pattern "01_*"

Push-Location Prep
python -m pipeline.load
Pop-Location

.\Prep\db\apply.ps1 -Pattern "02_*"
