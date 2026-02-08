"""Monitoring Stack for agent observability, behavior tracking, and risk detection."""
from aws_cdk import (
    Stack,
    Duration,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_lambda as _lambda,
    CfnOutput,
)
from constructs import Construct


class MonitoringStack(Stack):
    """Creates CloudWatch dashboards and alarms for agent monitoring."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_functions: dict[str, _lambda.Function],
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.functions = lambda_functions

        # SNS Topic for alerts
        self.alert_topic = sns.Topic(
            self, "AgentAlertTopic",
            topic_name="incident-handler-alerts",
            display_name="Incident Handler Agent Alerts"
        )

        # Create comprehensive dashboard
        self.dashboard = self._create_dashboard()

        # Create alarms
        self._create_agent_behavior_alarms()
        self._create_risk_alarms()

        # Outputs
        CfnOutput(self, "DashboardUrl",
                  value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name=IncidentHandlerAgents")
        CfnOutput(self, "AlertTopicArn", value=self.alert_topic.topic_arn)

    def _create_dashboard(self) -> cw.Dashboard:
        """Create comprehensive monitoring dashboard."""
        dashboard = cw.Dashboard(
            self, "AgentDashboard",
            dashboard_name="IncidentHandlerAgents",
            default_interval=Duration.hours(3),
        )

        # ============ AGENT OVERVIEW SECTION ============
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="# 🤖 Multi-Agent Incident Handler Dashboard\n"
                         "Real-time monitoring for Intent Classifier, Investigator, Action, and Policy agents.",
                width=24,
                height=1
            )
        )

        # AgentCore Runtime metrics (custom namespace)
        dashboard.add_widgets(
            cw.GraphWidget(
                title="Agent Invocations",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Invocations",
                        dimensions_map={"Agent": "Orchestrator"},
                        statistic="Sum",
                        period=Duration.minutes(5)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Invocations",
                        dimensions_map={"Agent": "IntentClassifier"},
                        statistic="Sum",
                        period=Duration.minutes(5)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Invocations",
                        dimensions_map={"Agent": "Investigator"},
                        statistic="Sum",
                        period=Duration.minutes(5)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Invocations",
                        dimensions_map={"Agent": "ActionAgent"},
                        statistic="Sum",
                        period=Duration.minutes(5)
                    ),
                ],
                width=12,
                height=6
            ),
            cw.GraphWidget(
                title="Agent Latency (P95)",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Latency",
                        dimensions_map={"Agent": "Orchestrator"},
                        statistic="p95",
                        period=Duration.minutes(5)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Agents",
                        metric_name="Latency",
                        dimensions_map={"Agent": "IntentClassifier"},
                        statistic="p95",
                        period=Duration.minutes(5)
                    ),
                ],
                width=12,
                height=6
            ),
        )

        # ============ DECISION OUTCOMES SECTION ============
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="## 📊 Policy Decision Outcomes",
                width=24,
                height=1
            )
        )

        dashboard.add_widgets(
            cw.SingleValueWidget(
                title="Auto-Close Rate",
                metrics=[
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Decision",
                        dimensions_map={"Outcome": "auto_close"},
                        statistic="Sum",
                        period=Duration.hours(24)
                    )
                ],
                width=6,
                height=4
            ),
            cw.SingleValueWidget(
                title="Auto-Retry Rate",
                metrics=[
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Decision",
                        dimensions_map={"Outcome": "auto_retry"},
                        statistic="Sum",
                        period=Duration.hours(24)
                    )
                ],
                width=6,
                height=4
            ),
            cw.SingleValueWidget(
                title="Escalations",
                metrics=[
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Decision",
                        dimensions_map={"Outcome": "escalate"},
                        statistic="Sum",
                        period=Duration.hours(24)
                    )
                ],
                width=6,
                height=4
            ),
            cw.SingleValueWidget(
                title="Human Review Required",
                metrics=[
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Decision",
                        dimensions_map={"Outcome": "human_review"},
                        statistic="Sum",
                        period=Duration.hours(24)
                    )
                ],
                width=6,
                height=4
            ),
        )

        # ============ INTENT CLASSIFICATION SECTION ============
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="## 🎯 Intent Classification",
                width=24,
                height=1
            )
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Intent Distribution",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Intent",
                        metric_name="Classification",
                        dimensions_map={"Intent": intent},
                        statistic="Sum",
                        period=Duration.hours(1)
                    )
                    for intent in ["dag_failure", "glue_etl_failure", "emr_failure",
                                   "athena_failure", "data_missing", "access_denied", "unknown"]
                ],
                width=16,
                height=6
            ),
            cw.GraphWidget(
                title="Classification Confidence",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Intent",
                        metric_name="Confidence",
                        statistic="Average",
                        period=Duration.minutes(15)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Intent",
                        metric_name="Confidence",
                        statistic="p10",
                        period=Duration.minutes(15)
                    ),
                ],
                width=8,
                height=6
            ),
        )

        # ============ LAMBDA TOOLS SECTION ============
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="## 🔧 Tool Lambda Functions",
                width=24,
                height=1
            )
        )

        # Lambda invocations and errors
        invocation_metrics = []
        error_metrics = []
        for name, func in self.functions.items():
            invocation_metrics.append(func.metric_invocations(period=Duration.minutes(5)))
            error_metrics.append(func.metric_errors(period=Duration.minutes(5)))

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Tool Lambda Invocations",
                left=invocation_metrics[:7],  # First 7 tools
                width=12,
                height=6
            ),
            cw.GraphWidget(
                title="Tool Lambda Errors",
                left=error_metrics,
                width=12,
                height=6
            ),
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Tool Lambda Duration (P95)",
                left=[func.metric_duration(statistic="p95", period=Duration.minutes(5))
                      for func in list(self.functions.values())[:6]],
                width=12,
                height=6
            ),
            cw.GraphWidget(
                title="Tool Lambda Throttles",
                left=[func.metric_throttles(period=Duration.minutes(5))
                      for func in self.functions.values()],
                width=12,
                height=6
            ),
        )

        # ============ RISK INDICATORS SECTION ============
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="## ⚠️ Risk Indicators",
                width=24,
                height=1
            )
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Schema Validation Failures",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Validation",
                        metric_name="Failure",
                        dimensions_map={"Schema": schema},
                        statistic="Sum",
                        period=Duration.minutes(15)
                    )
                    for schema in ["intent", "investigation", "action", "orchestrator"]
                ],
                width=8,
                height=6
            ),
            cw.GraphWidget(
                title="Policy Override Triggers",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Override",
                        dimensions_map={"Type": "access_denied"},
                        statistic="Sum",
                        period=Duration.hours(1)
                    ),
                    cw.Metric(
                        namespace="IncidentHandler/Policy",
                        metric_name="Override",
                        dimensions_map={"Type": "kafka_events_failed"},
                        statistic="Sum",
                        period=Duration.hours(1)
                    ),
                ],
                width=8,
                height=6
            ),
            cw.GraphWidget(
                title="Low Confidence Classifications",
                left=[
                    cw.Metric(
                        namespace="IncidentHandler/Intent",
                        metric_name="LowConfidence",
                        statistic="Sum",
                        period=Duration.hours(1)
                    ),
                ],
                width=8,
                height=6
            ),
        )

        return dashboard

    def _create_agent_behavior_alarms(self) -> None:
        """Create alarms for agent behavior anomalies."""

        # High human_review rate alarm
        cw.Alarm(
            self, "HighHumanReviewRate",
            alarm_name="IncidentHandler-HighHumanReviewRate",
            metric=cw.Metric(
                namespace="IncidentHandler/Policy",
                metric_name="Decision",
                dimensions_map={"Outcome": "human_review"},
                statistic="Sum",
                period=Duration.hours(1)
            ),
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="More than 10 incidents requiring human review in 1 hour",
            actions_enabled=True,
        ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        # Low classification confidence alarm
        cw.Alarm(
            self, "LowConfidenceAlarm",
            alarm_name="IncidentHandler-LowClassificationConfidence",
            metric=cw.Metric(
                namespace="IncidentHandler/Intent",
                metric_name="Confidence",
                statistic="Average",
                period=Duration.minutes(30)
            ),
            threshold=0.5,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            alarm_description="Average intent classification confidence below 50%",
            actions_enabled=True,
        ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        # Agent latency alarm
        cw.Alarm(
            self, "HighAgentLatency",
            alarm_name="IncidentHandler-HighAgentLatency",
            metric=cw.Metric(
                namespace="IncidentHandler/Agents",
                metric_name="Latency",
                dimensions_map={"Agent": "Orchestrator"},
                statistic="p95",
                period=Duration.minutes(5)
            ),
            threshold=60000,  # 60 seconds
            evaluation_periods=3,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Agent orchestration P95 latency exceeds 60 seconds",
            actions_enabled=True,
        ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))

    def _create_risk_alarms(self) -> None:
        """Create alarms for risk detection."""

        # Schema validation failure spike
        cw.Alarm(
            self, "SchemaValidationFailureSpike",
            alarm_name="IncidentHandler-SchemaValidationFailures",
            metric=cw.Metric(
                namespace="IncidentHandler/Validation",
                metric_name="Failure",
                statistic="Sum",
                period=Duration.minutes(15)
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="More than 5 schema validation failures in 15 minutes",
            actions_enabled=True,
        ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        # High access_denied escalations
        cw.Alarm(
            self, "HighAccessDeniedEscalations",
            alarm_name="IncidentHandler-HighAccessDeniedEscalations",
            metric=cw.Metric(
                namespace="IncidentHandler/Policy",
                metric_name="Override",
                dimensions_map={"Type": "access_denied"},
                statistic="Sum",
                period=Duration.hours(1)
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="More than 5 access_denied incidents in 1 hour - potential security issue",
            actions_enabled=True,
        ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        # Lambda error rate alarms for critical tools
        for tool_name in ["update_servicenow_ticket", "retry_emr", "retry_glue_job"]:
            if tool_name in self.functions:
                func = self.functions[tool_name]
                cw.Alarm(
                    self, f"{tool_name}ErrorAlarm",
                    alarm_name=f"IncidentHandler-{tool_name}-Errors",
                    metric=func.metric_errors(period=Duration.minutes(5)),
                    threshold=3,
                    evaluation_periods=2,
                    comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                    alarm_description=f"High error rate for {tool_name} Lambda",
                    actions_enabled=True,
                ).add_alarm_action(cw_actions.SnsAction(self.alert_topic))
