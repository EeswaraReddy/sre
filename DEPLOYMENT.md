# Deployment Guide - SRE Incident Agent

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **Python 3.12+** installed
4. **Node.js 18+** (for CDK)
5. **ServiceNow Instance** with API access

## Architecture Overview

```
EventBridge (5 min schedule)
    ↓
Poller Lambda (polls ServiceNow)
    ↓
Orchestrator Lambda (runs agents)
    ↓
MCP Gateway (tools) + ServiceNow API
    ↓
S3 (RCA storage) + ServiceNow (update/close)
```

## Deployment Steps

### 1. Install Dependencies

```bash
# Install CDK CLI globally
npm install -g aws-cdk

# Install Python dependencies
pip install -r requirements.txt
pip install -r cdk/requirements.txt
```

### 2. Configure AWS Credentials

```bash
# Configure AWS CLI
aws configure

# Verify credentials
aws sts get-caller-identity
```

### 3. Set Up ServiceNow Credentials

Create a secret in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name servicenow/credentials \
    --description "ServiceNow API credentials" \
    --secret-string '{
        "servicenow_instance": "your-instance.service-now.com",
        "servicenow_username": "service-account",
        "servicenow_password": "your-password"
    }'
```

### 4. Deploy Using Script

```bash
# Make script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

**Or deploy manually:**

```bash
# Create Lambda layer
mkdir -p lambda_layer/python
pip install -r requirements-deploy.txt -t lambda_layer/python/

# Copy code to Lambda directories
cp -r agents servicenow storage lambdas/orchestrator/
cp -r servicenow lambdas/poller/

# Bootstrap and deploy CDK
cd cdk
cdk bootstrap
cdk deploy
```

### 5. Configure Environment Variables

After deployment, update Lambda environment variables if needed:

**Orchestrator Lambda:**
- `RCA_BUCKET`: Auto-set by CDK
- `MCP_GATEWAY_ENDPOINT`: Set to your MCP Gateway URL
- `MODEL_ID`: Bedrock model ID

**Poller Lambda:**
- `ASSIGNMENT_GROUP`: ServiceNow assignment group name
- `POLL_LIMIT`: Max incidents per poll (default: 10)
- `MINUTES_BACK`: Look back period (default: 10)

## Testing

### Test Poller Lambda

```bash
aws lambda invoke \
    --function-name incident-poller \
    --payload '{}' \
    response.json

cat response.json
```

### Test Orchestrator Lambda

```bash
aws lambda invoke \
    --function-name incident-orchestrator \
    --payload '{
        "incident": {
            "sys_id": "test123",
            "number": "INC0001",
            "short_description": "Test MWAA DAG failure",
            "category": "Data Pipeline"
        }
    }' \
    response.json

cat response.json
```

### Check CloudWatch Logs

```bash
# Poller logs
aws logs tail /aws/lambda/incident-poller --follow

# Orchestrator logs
aws logs tail /aws/lambda/incident-orchestrator --follow
```

## Monitoring

### CloudWatch Metrics

Monitor these metrics:
- Lambda invocations
- Lambda errors
- Lambda duration
- DLQ messages

### CloudWatch Alarms

Set up alarms for:
- Lambda errors > 5 in 5 minutes
- Lambda duration > 5 minutes
- DLQ messages > 0

## Configuration

### Polling Frequency

To change polling frequency, update EventBridge rule:

```bash
aws events put-rule \
    --name incident-poller-schedule \
    --schedule-expression "rate(5 minutes)"
```

### Assignment Group Filter

Update `ASSIGNMENT_GROUP` environment variable in poller Lambda:

```bash
aws lambda update-function-configuration \
    --function-name incident-poller \
    --environment "Variables={ASSIGNMENT_GROUP=Your Team Name}"
```

## Troubleshooting

### Issue: Lambda timeout

**Solution:** Increase timeout in `cdk/incident_agent_stack.py`:
```python
timeout=Duration.minutes(15)  # Increase this
```

### Issue: ServiceNow API errors

**Solution:** Check credentials in Secrets Manager:
```bash
aws secretsmanager get-secret-value \
    --secret-id servicenow/credentials
```

### Issue: Bedrock access denied

**Solution:** Ensure Lambda role has Bedrock permissions:
```bash
# Check IAM role has bedrock:InvokeModel permission
aws iam get-role-policy --role-name IncidentAgentLambdaRole
```

## Cleanup

To remove all resources:

```bash
cd cdk
cdk destroy
```

**Note:** S3 bucket with RCA documents will be retained by default.

## Cost Estimate

Typical monthly costs (assuming 100 incidents/day):

- Lambda: ~$5-10
- S3: ~$1-2
- Bedrock: ~$20-50 (depending on model)
- **Total: ~$30-65/month**

## Next Steps

1. ✅ Test with real ServiceNow incidents
2. ✅ Configure MCP Gateway tools
3. ✅ Set up CloudWatch alarms
4. ✅ Review RCA documents in S3
5. ✅ Fine-tune prompts based on results
