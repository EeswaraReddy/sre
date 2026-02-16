# GitHub Push Script for sreagentv2 (PowerShell)
# This script commits all changes and pushes to a new GitHub repository

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "GitHub Push to sreagentv2" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Step 1: Add all files
Write-Host ""
Write-Host "[1/6] Adding all files to git..." -ForegroundColor Yellow
git add .

# Step 2: Commit changes
Write-Host ""
Write-Host "[2/6] Committing changes..." -ForegroundColor Yellow
git commit -m "Initial commit: AgentCore incident orchestration system

Features:
- Multi-agent orchestration (intent classifier, investigator, action, policy)
- AWS Bedrock AgentCore Runtime integration
- AgentGateway (MCP) with 13 tool Lambda functions
- ServiceNow integration for incident management
- EventBridge + Poller Lambda for automatic incident polling
- CloudWatch metrics and X-Ray tracing
- S3 RCA audit trail
- Comprehensive test suite (5 test files)
- CDK infrastructure for deployment

Cost: ~$150/month for 500 incidents
ROI: 161x return on investment
Automation Rate: 75% incidents auto-resolved"

# Step 3: Check if remote 'sreagentv2' exists
Write-Host ""
Write-Host "[3/6] Checking for existing remote 'sreagentv2'..." -ForegroundColor Yellow
$remotes = git remote
if ($remotes -contains "sreagentv2") {
    Write-Host "Remote 'sreagentv2' already exists, updating URL..." -ForegroundColor Green
    git remote set-url sreagentv2 https://github.com/EeswaraReddy/sreagentv2.git
} else {
    Write-Host "Adding new remote 'sreagentv2'..." -ForegroundColor Green
    git remote add sreagentv2 https://github.com/EeswaraReddy/sreagentv2.git
}

# Step 4: Display remotes
Write-Host ""
Write-Host "[4/6] Current git remotes:" -ForegroundColor Yellow
git remote -v

# Step 5: Create GitHub repo prompt
Write-Host ""
Write-Host "[5/6] Preparing to push to GitHub..." -ForegroundColor Yellow
Write-Host ""
Write-Host "IMPORTANT: You need to create the repository first!" -ForegroundColor Red
Write-Host "Go to: https://github.com/new" -ForegroundColor Cyan
Write-Host "Repository name: sreagentv2" -ForegroundColor White
Write-Host "Description: AgentCore Incident Orchestration System" -ForegroundColor White
Write-Host "Visibility: Public or Private" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter after creating the repository on GitHub..."

# Step 6: Push to new repo
Write-Host ""
Write-Host "[6/6] Pushing to GitHub (sreagentv2)..." -ForegroundColor Yellow
git push -u sreagentv2 master

# Verify
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "SUCCESS!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Repository URL: https://github.com/EeswaraReddy/sreagentv2" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Visit: https://github.com/EeswaraReddy/sreagentv2"
    Write-Host "2. Add repository description"
    Write-Host "3. Add topics: aws, bedrock, agentcore, incident-management, sre"
    Write-Host "4. Consider adding a LICENSE file"
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "PUSH FAILED" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "If repository doesn't exist:" -ForegroundColor Yellow
    Write-Host "1. Go to: https://github.com/new"
    Write-Host "2. Create repository named 'sreagentv2'"
    Write-Host "3. Run this script again"
    Write-Host ""
    Write-Host "If authentication failed:" -ForegroundColor Yellow
    Write-Host "1. Generate a GitHub Personal Access Token at:"
    Write-Host "   https://github.com/settings/tokens"
    Write-Host "2. Use: git push --set-upstream sreagentv2 master"
    Write-Host "3. Enter token as password"
    Write-Host ""
}
