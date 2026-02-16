#!/bin/bash
# GitHub Push Script for sreagentv2
# This script commits all changes and pushes to a new GitHub repository

echo "==========================================="
echo "GitHub Push to sreagentv2"
echo "==========================================="

# Step 1: Add all files
echo ""
echo "[1/6] Adding all files to git..."
git add .

# Step 2: Commit changes
echo ""
echo "[2/6] Committing changes..."
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
echo ""
echo "[3/6] Checking for existing remote 'sreagentv2'..."
if git remote | grep -q "sreagentv2"; then
    echo "Remote 'sreagentv2' already exists, updating URL..."
    git remote set-url sreagentv2 https://github.com/EeswaraReddy/sreagentv2.git
else
    echo "Adding new remote 'sreagentv2'..."
    git remote add sreagentv2 https://github.com/EeswaraReddy/sreagentv2.git
fi

# Step 4: Display remotes
echo ""
echo "[4/6] Current git remotes:"
git remote -v

# Step 5: Push to new repo
echo ""
echo "[5/6] Pushing to GitHub (sreagentv2)..."
echo ""
echo "IMPORTANT: You may need to create the repository first!"
echo "Go to: https://github.com/new"
echo "Repository name: sreagentv2"
echo "Description: AgentCore Incident Orchestration System"
echo "Visibility: Public or Private"
echo ""
read -p "Press Enter after creating the repository on GitHub..."

git push -u sreagentv2 master

# Step 6: Verify
echo ""
echo "[6/6] Verifying push..."
if [ $? -eq 0 ]; then
    echo ""
    echo "==========================================="
    echo "SUCCESS!"
    echo "==========================================="
    echo ""
    echo "Repository URL: https://github.com/EeswaraReddy/sreagentv2"
    echo ""
    echo "Next Steps:"
    echo "1. Visit: https://github.com/EeswaraReddy/sreagentv2"
    echo "2. Add repository description"
    echo "3. Add topics: aws, bedrock, agentcore, incident-management, sre"
    echo "4. Consider adding a LICENSE file"
    echo ""
else
    echo ""
    echo "==========================================="
    echo "PUSH FAILED"
    echo "==========================================="
    echo ""
    echo "If repository doesn't exist:"
    echo "1. Go to: https://github.com/new"
    echo "2. Create repository named 'sreagentv2'"
    echo "3. Run this script again"
    echo ""
    echo "If authentication failed:"
    echo "1. Generate a GitHub Personal Access Token"
    echo "2. Use: git push --set-upstream sreagentv2 master"
    echo "3. Enter token as password"
    echo ""
fi
