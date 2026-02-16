# Multi-Agent Incident Handler for AWS Data Lake

An AI-powered incident handler that automatically classifies, investigates, and resolves AWS data lake incidents using Amazon Bedrock AgentCore Runtime, AgentCore Gateway (MCP), and Strands Agents SDK.

## System Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           ServiceNow                                      │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  New Incidents: assigned_to="Data Lake Platform Team"            │    │
│  │  Status: New → In Progress → Resolved/Closed                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 │ ① Polling (every 5 min)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          AWS EventBridge                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Schedule Rule: rate(5 minutes)                                   │    │
│  │  Trigger: Poller Lambda                                           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 │ ② Trigger
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Poller Lambda Function                                 │
│  • Get new incidents from ServiceNow API                                  │
│  • Update status to "In Progress"                                         │
│  • Invoke AgentCore Runtime (async)                                       │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 │ ③ Invoke with incident payload
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Bedrock AgentCore Runtime                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     Main Orchestrator                            │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │    │
│  │  │   Intent     │  │ Investigator │  │   Action     │           │    │
│  │  │ Classifier   │→→│    Agent     │→→│    Agent     │           │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘           │    │
│  │         │                  ↓                  ↓                  │    │
│  │         │          ┌──────────────┐  ┌──────────────┐           │    │
│  │         └──────────│   Policy     │──│     RCA      │           │    │
│  │                    │   Engine     │  │   Builder    │           │    │
│  │                    └──────────────┘  └──────────────┘           │    │
│  └─────────────────────────────┬───────────────────────────────────┘    │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │
                                 │ ④ Call MCP tools
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AgentCore Gateway (MCP)                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                  13 Lambda Tool Functions                        │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │    │
│  │  │ get_emr_logs│ │get_glue_logs│ │get_mwaa_logs│ │ get_athena │ │    │
│  │  ├─────────────┤ ├─────────────┤ ├─────────────┤ ├────────────┤ │    │
│  │  │  retry_emr  │ │retry_glue   │ │retry_airflow│ │retry_athena│ │    │
│  │  ├─────────────┤ ├─────────────┤ ├─────────────┤ ├────────────┤ │    │
│  │  │verify_source│ │ get_s3_logs │ │ get_cw_alarm│ │retry_kafka │ │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │    │
│  │                                  ┌─────────────────────────────┐│    │
│  │                                  │  update_servicenow_ticket   ││    │
│  │                                  └─────────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  AWS Services   │    │   S3 RCA Bucket │    │   ServiceNow    │
│ EMR/Glue/MWAA   │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Features

- **Intent Classification**: Classifies incidents into 13 categories (EMR, Glue, Airflow, Athena, Kafka, etc.)
- **Automated Investigation**: Gathers evidence using MCP tools via AgentCore Gateway
- **Smart Actions**: Executes retry operations for transient failures
- **Policy Engine**: Scores evidence and determines decisions (auto-close, auto-retry, escalate, human-review)
- **RCA Storage**: Stores Root Cause Analysis documents in S3
- **CloudWatch Monitoring**: Comprehensive dashboards and alarms for agent behavior

## Project Structure

```
sreagent/
├── agents/                         # Strands agent modules
│   ├── __init__.py
│   ├── config.py                   # Configuration and intent taxonomy
│   ├── schemas.py                  # JSON schema validation
│   ├── intent_classifier.py        # Intent classification agent
│   ├── investigator.py             # Investigation agent
│   ├── action_agent.py             # Action execution agent
│   ├── policy_engine.py            # Policy and RCA builder
│   └── main.py                     # Main orchestrator handler
├── lambdas/                        # Lambda tool functions
│   ├── get_emr_logs/handler.py
│   ├── get_glue_logs/handler.py
│   ├── get_mwaa_logs/handler.py
│   ├── get_cloudwatch_alarm/handler.py
│   ├── get_athena_query/handler.py
│   ├── get_s3_logs/handler.py
│   ├── verify_source_data/handler.py
│   ├── retry_emr/handler.py
│   ├── retry_glue_job/handler.py
│   ├── retry_airflow_dag/handler.py
│   ├── retry_athena_query/handler.py
│   ├── retry_kafka/handler.py
│   └── update_servicenow_ticket/handler.py
├── gateway/                        # AgentCore Gateway configuration
│   ├── tool_schemas.json           # MCP tool definitions
│   └── gateway_config.json         # Gateway endpoint config
├── cdk/                            # AWS CDK infrastructure
│   ├── app.py                      # CDK app entrypoint
│   ├── cdk.json
│   ├── requirements.txt
│   └── stacks/
│       ├── s3_stack.py             # RCA bucket
│       ├── cognito_stack.py        # JWT authentication
│       ├── lambda_stack.py         # 13 tool functions
│       └── monitoring_stack.py     # Dashboard & alarms
├── evaluation/                     # Testing
│   ├── test_cases.json             # Sample incident test cases
│   └── evaluate.py                 # Evaluation script
├── agentcore_runtime_config.json   # Runtime configuration
└── requirements.txt                # Python dependencies
```

## Intent Taxonomy

| Intent | Description | Auto-Retry |
|--------|-------------|------------|
| `dag_failure` | Airflow DAG execution failed | Yes |
| `dag_alarm` | CloudWatch alarm for DAG | No |
| `mwaa_failure` | MWAA environment failure | Yes |
| `glue_etl_failure` | Glue ETL job failure | Yes |
| `athena_failure` | Athena query failure | Yes |
| `emr_failure` | EMR cluster/step failure | Yes |
| `kafka_events_failed` | Kafka consumer failure | No* |
| `data_missing` | Expected data not found | No |
| `source_zero_data` | Source has zero records | No |
| `data_not_available` | Data source unreachable | No |
| `batch_auto_recovery_failed` | Batch recovery failed | No |
| `access_denied` | IAM permission denied | No* |
| `unknown` | Unknown category | No |

\* These intents have policy overrides that always result in escalation/human-review.

## Policy Decisions

| Decision | Criteria |
|----------|----------|
| `auto_close` | High confidence (≥0.8) with successful action |
| `auto_retry` | Medium confidence (≥0.6), transient failure detected |
| `escalate` | Low confidence (≥0.4) or complex issue |
| `human_review` | Very low confidence or policy override |

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.12+
- Node.js 18+ (for CDK)
- AWS CDK CLI (`npm install -g aws-cdk`)

### Deploy Infrastructure

```bash
cd cdk
pip install -r requirements.txt
cdk bootstrap
cdk deploy --all
```

### Configure ServiceNow Credentials

Create a secret in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name incident-handler/servicenow \
  --secret-string '{
    "instance_url": "https://your-instance.service-now.com",
    "client_id": "your-oauth-client-id",
    "client_secret": "your-oauth-client-secret"
  }'
```

### Deploy Agent Runtime

```bash
# Package and deploy to AgentCore Runtime
# (Follow AWS Bedrock AgentCore deployment guide)
```

## Local Testing

### Run Evaluation

```bash
pip install -r requirements.txt
python evaluation/evaluate.py -v
```

### Test Single Incident

```python
from agents.main import handler_sync

result = handler_sync({
    "incident": {
        "sys_id": "INC001",
        "short_description": "Glue job failed with OutOfMemory",
        "category": "Data Pipeline"
    }
})
print(result)
```

## CloudWatch Monitoring

The monitoring stack creates:

- **Dashboard**: `IncidentHandlerAgents` with agent metrics, policy decisions, and tool performance
- **Alarms**:
  - High human review rate
  - Low classification confidence
  - High orchestration latency
  - Schema validation failures
  - Critical tool errors

## Environment Variables

| Variable | Description |
|----------|-------------|
| `RCA_BUCKET` | S3 bucket for RCA storage |
| `RCA_PREFIX` | S3 prefix for RCAs (default: `rca/`) |
| `GATEWAY_ENDPOINT` | AgentCore Gateway URL |
| `BEDROCK_MODEL_ID` | Bedrock model (default: `anthropic.claude-sonnet-4-20250514`) |
| `SERVICENOW_SECRET_ARN` | Secrets Manager ARN for ServiceNow creds |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

## License

MIT
