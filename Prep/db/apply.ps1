# Apply db/init/*.sql to the already-running db container, in order.
# Needed because Postgres only auto-runs init/ on a container's FIRST boot (empty volume) —
# this re-applies by hand for an existing container. All files are IF NOT EXISTS-safe.
# Filter which files run with -Pattern, e.g. apply.ps1 -Pattern "01_*"
param([string]$Pattern = "*.sql")

$initFiles = Get-ChildItem "$PSScriptRoot\init\$Pattern" | Sort-Object Name

foreach ($file in $initFiles) {
    Write-Host "Applying $($file.Name)..."
    Get-Content $file.FullName | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}
