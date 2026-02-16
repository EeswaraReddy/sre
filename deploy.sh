#!/bin/bash
# Deployment script for Incident Agent

set -e

echo "======================================"
echo "Deploying SRE Incident Agent"
echo "======================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Install CDK dependencies
echo -e "${YELLOW}Step 1: Installing CDK dependencies...${NC}"
cd cdk
pip install -r requirements.txt
cd ..

# Step 2: Create Lambda layer with dependencies
echo -e "${YELLOW}Step 2: Creating Lambda layer...${NC}"
mkdir -p lambda_layer/python
pip install -r requirements-deploy.txt -t lambda_layer/python/
echo -e "${GREEN}✓ Lambda layer created${NC}"

# Step 3: Copy agent code to Lambda functions
echo -e "${YELLOW}Step 3: Copying agent code to Lambda functions...${NC}"

# Copy to orchestrator Lambda
cp -r agents lambdas/orchestrator/
cp -r servicenow lambdas/orchestrator/
cp -r storage lambdas/orchestrator/

# Copy to poller Lambda
cp -r servicenow lambdas/poller/

echo -e "${GREEN}✓ Code copied${NC}"

# Step 4: Bootstrap CDK (if not already done)
echo -e "${YELLOW}Step 4: Bootstrapping CDK...${NC}"
cd cdk
cdk bootstrap
echo -e "${GREEN}✓ CDK bootstrapped${NC}"

# Step 5: Deploy stack
echo -e "${YELLOW}Step 5: Deploying CDK stack...${NC}"
cdk deploy --require-approval never
echo -e "${GREEN}✓ Stack deployed${NC}"

cd ..

echo ""
echo -e "${GREEN}======================================"
echo "Deployment Complete! ✓"
echo "======================================${NC}"
echo ""
echo "Next steps:"
echo "1. Update ServiceNow credentials in Secrets Manager"
echo "2. Configure MCP Gateway endpoint"
echo "3. Test with a sample incident"
echo ""
