"""Get CloudWatch alarm details and history."""
import json
import boto3
from datetime import datetime, timedelta
from typing import Any


cloudwatch = boto3.client("cloudwatch")


def handler(event: dict, context: Any) -> dict:
    """Retrieve CloudWatch alarm state and history.
    
    Args:
        event: Contains alarm_name (required) or alarm_prefix for search
    
    Returns:
        Alarm details, current state, and recent history
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        alarm_name = body.get("alarm_name")
        alarm_prefix = body.get("alarm_prefix")
        
        if not alarm_name and not alarm_prefix:
            return _error_response(400, "alarm_name or alarm_prefix is required")
        
        result = {"alarms": []}
        
        if alarm_name:
            # Get specific alarm
            alarms_response = cloudwatch.describe_alarms(AlarmNames=[alarm_name])
            metric_alarms = alarms_response.get("MetricAlarms", [])
            composite_alarms = alarms_response.get("CompositeAlarms", [])
            
            for alarm in metric_alarms + composite_alarms:
                alarm_data = _format_alarm(alarm)
                alarm_data["history"] = _get_alarm_history(alarm["AlarmName"])
                alarm_data["metric_data"] = _get_metric_data(alarm) if "MetricName" in alarm else None
                result["alarms"].append(alarm_data)
        else:
            # Search by prefix
            alarms_response = cloudwatch.describe_alarms(AlarmNamePrefix=alarm_prefix, MaxRecords=20)
            metric_alarms = alarms_response.get("MetricAlarms", [])
            
            for alarm in metric_alarms:
                alarm_data = _format_alarm(alarm)
                result["alarms"].append(alarm_data)
        
        if not result["alarms"]:
            return _error_response(404, f"No alarms found matching criteria")
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error retrieving alarm data: {str(e)}")


def _format_alarm(alarm: dict) -> dict:
    """Format alarm data for response."""
    return {
        "alarm_name": alarm.get("AlarmName"),
        "alarm_description": alarm.get("AlarmDescription"),
        "state": alarm.get("StateValue"),
        "state_reason": alarm.get("StateReason"),
        "state_updated": alarm.get("StateUpdatedTimestamp"),
        "metric_name": alarm.get("MetricName"),
        "namespace": alarm.get("Namespace"),
        "statistic": alarm.get("Statistic") or alarm.get("ExtendedStatistic"),
        "period": alarm.get("Period"),
        "threshold": alarm.get("Threshold"),
        "comparison_operator": alarm.get("ComparisonOperator"),
        "evaluation_periods": alarm.get("EvaluationPeriods"),
        "datapoints_to_alarm": alarm.get("DatapointsToAlarm"),
        "dimensions": alarm.get("Dimensions", []),
        "actions_enabled": alarm.get("ActionsEnabled"),
        "alarm_actions": alarm.get("AlarmActions", []),
    }


def _get_alarm_history(alarm_name: str) -> list:
    """Get recent alarm history."""
    history = []
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=7)
        
        response = cloudwatch.describe_alarm_history(
            AlarmName=alarm_name,
            HistoryItemType="StateUpdate",
            StartDate=start_time,
            EndDate=end_time,
            MaxRecords=20
        )
        
        for item in response.get("AlarmHistoryItems", []):
            history.append({
                "timestamp": item.get("Timestamp"),
                "type": item.get("HistoryItemType"),
                "summary": item.get("HistorySummary"),
            })
            
    except Exception:
        pass
    
    return history


def _get_metric_data(alarm: dict) -> dict:
    """Get recent metric data for the alarm's metric."""
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=6)
        period = alarm.get("Period", 300)
        
        response = cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "m1",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": alarm.get("Namespace"),
                            "MetricName": alarm.get("MetricName"),
                            "Dimensions": alarm.get("Dimensions", [])
                        },
                        "Period": period,
                        "Stat": alarm.get("Statistic", "Average")
                    }
                }
            ],
            StartTime=start_time,
            EndTime=end_time
        )
        
        results = response.get("MetricDataResults", [])
        if results:
            data = results[0]
            return {
                "timestamps": [ts.isoformat() for ts in data.get("Timestamps", [])],
                "values": data.get("Values", []),
                "threshold": alarm.get("Threshold")
            }
            
    except Exception:
        pass
    
    return None


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
