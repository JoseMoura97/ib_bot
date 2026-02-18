# IB Bot Migration Script
# Usage: .\infra\scripts\migrate.ps1

$ServerIP = "213.159.68.39"
$User = "root"
$Remote = "${User}@${ServerIP}"

Write-Host ">>> IB Bot Migration to $ServerIP" -ForegroundColor Cyan

# 1. Check for SSH connection
Write-Host "1. Testing SSH connection..."
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$Remote" "echo Connection Success" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: SSH key not set up or connection failed." -ForegroundColor Yellow
    Write-Host "You will be prompted for the password multiple times."
    Write-Host "Server Password: heKyD760SS74" -ForegroundColor Green
}

# 2. Upload Provisioning Script
Write-Host "2. Uploading provisioning script..."
scp -o StrictHostKeyChecking=no infra/scripts/server_provision.sh "${Remote}:/tmp/server_provision.sh"

# 3. Execute Provisioning
Write-Host "3. Running provisioning script on server (this may take a few minutes)..."
ssh -o StrictHostKeyChecking=no "$Remote" "chmod +x /tmp/server_provision.sh && /tmp/server_provision.sh"

# 4. Create Database Backup
Write-Host "4. Creating local database backup..."
$dbContainer = docker ps -qf "name=ib_bot-db-1" 2>$null
if ($dbContainer) {
    docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot -F c -f /tmp/ibbot_migration.dump
    docker cp ib_bot-db-1:/tmp/ibbot_migration.dump ./ibbot_migration.dump
} else {
    Write-Host "Warning: Local DB container not running. Skipping DB dump." -ForegroundColor Yellow
}

# 5. Archive Cache
Write-Host "5. Archiving cache..."
if (Test-Path ".cache") {
    tar -czf cache_migration.tar.gz .cache
} else {
    Write-Host "Warning: .cache directory not found." -ForegroundColor Yellow
}

# 6. Transfer Files
Write-Host "6. Transferring project files..."
ssh -o StrictHostKeyChecking=no "$Remote" "mkdir -p /home/ibbot/ib_bot"

Write-Host "   Bundling project files..."
tar --exclude="./.git" --exclude="./node_modules" --exclude="./.cache" --exclude="./.next" --exclude="*.dump" --exclude="*.tar.gz" --exclude=".venv" --exclude="./venv_stable" --exclude="__pycache__" -czf project_migration.tar.gz .

Write-Host "   Uploading project bundle..."
scp -o StrictHostKeyChecking=no project_migration.tar.gz "${Remote}:/home/ibbot/ib_bot/"

Write-Host "   Uploading database dump..."
if (Test-Path "ibbot_migration.dump") {
    scp -o StrictHostKeyChecking=no ibbot_migration.dump "${Remote}:/home/ibbot/"
}

Write-Host "   Uploading cache..."
if (Test-Path "cache_migration.tar.gz") {
    scp -o StrictHostKeyChecking=no cache_migration.tar.gz "${Remote}:/home/ibbot/ib_bot/"
}

# 7. Extract on Server
Write-Host "7. Extracting files on server..."
ssh -o StrictHostKeyChecking=no "$Remote" "cd /home/ibbot/ib_bot && tar -xzf project_migration.tar.gz && rm project_migration.tar.gz"
ssh -o StrictHostKeyChecking=no "$Remote" "cd /home/ibbot/ib_bot && if [ -f cache_migration.tar.gz ]; then tar -xzf cache_migration.tar.gz && rm cache_migration.tar.gz; fi"

# 8. Restore Database (if dump exists)
ssh -o StrictHostKeyChecking=no "$Remote" "if [ -f /home/ibbot/ibbot_migration.dump ]; then echo 'DB dump uploaded - restore after docker-compose up'; fi"

# 9. Set Permissions
Write-Host "8. Setting permissions..."
ssh -o StrictHostKeyChecking=no "$Remote" "chown -R ibbot:ibbot /home/ibbot"

# Cleanup Local
Write-Host "Cleaning up local temporary files..."
Remove-Item project_migration.tar.gz -ErrorAction SilentlyContinue
Remove-Item cache_migration.tar.gz -ErrorAction SilentlyContinue

Write-Host ">>> Migration File Transfer Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. SSH into server: ssh root@$ServerIP"
Write-Host "2. Switch to user:  su - ibbot"
Write-Host "3. cd ~/ib_bot"
Write-Host "4. cp .env.example .env && nano .env"
Write-Host "5. docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
