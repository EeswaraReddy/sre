"""Get S3 access/server logs."""
import json
import boto3
from datetime import datetime, timedelta
from typing import Any


s3 = boto3.client("s3")


def handler(event: dict, context: Any) -> dict:
    """Retrieve S3 server access logs for a bucket.
    
    Args:
        event: Contains bucket_name (required), prefix, start_time, end_time
    
    Returns:
        S3 access log entries
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        bucket_name = body.get("bucket_name")
        prefix = body.get("prefix", "")
        start_time = body.get("start_time")
        end_time = body.get("end_time")
        
        if not bucket_name:
            return _error_response(400, "bucket_name is required")
        
        result = {"bucket_name": bucket_name, "logs": []}
        
        # Get bucket logging configuration
        try:
            logging_config = s3.get_bucket_logging(Bucket=bucket_name)
            logging_enabled = logging_config.get("LoggingEnabled")
            
            if logging_enabled:
                result["logging_enabled"] = True
                result["target_bucket"] = logging_enabled.get("TargetBucket")
                result["target_prefix"] = logging_enabled.get("TargetPrefix")
            else:
                result["logging_enabled"] = False
                result["message"] = "Server access logging is not enabled for this bucket"
                return _success_response(result)
                
        except Exception as e:
            return _error_response(500, f"Error getting bucket logging config: {str(e)}")
        
        # Parse time range
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        else:
            end_dt = datetime.utcnow()
            
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        else:
            start_dt = end_dt - timedelta(hours=24)
        
        # List and read log files from target bucket
        target_bucket = logging_enabled["TargetBucket"]
        target_prefix = logging_enabled.get("TargetPrefix", "")
        
        log_entries = []
        
        try:
            # List log files
            paginator = s3.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=target_bucket,
                Prefix=target_prefix,
                MaxKeys=100
            )
            
            for page in page_iterator:
                for obj in page.get("Contents", [])[:20]:  # Limit to 20 files
                    key = obj["Key"]
                    last_modified = obj["LastModified"]
                    
                    # Filter by time range
                    if last_modified.replace(tzinfo=None) < start_dt or \
                       last_modified.replace(tzinfo=None) > end_dt:
                        continue
                    
                    # Read log file
                    try:
                        log_obj = s3.get_object(Bucket=target_bucket, Key=key)
                        content = log_obj["Body"].read().decode("utf-8")
                        
                        # Parse log entries (S3 server access log format)
                        for line in content.strip().split("\n")[:50]:  # Limit entries per file
                            parsed = _parse_log_line(line)
                            if parsed:
                                # Filter by prefix if specified
                                if prefix and not parsed.get("key", "").startswith(prefix):
                                    continue
                                log_entries.append(parsed)
                                
                    except Exception:
                        continue
                        
        except Exception as e:
            result["error"] = f"Error reading logs: {str(e)}"
        
        # Sort by timestamp and limit
        log_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        result["logs"] = log_entries[:100]
        result["total_entries"] = len(log_entries)
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error retrieving S3 logs: {str(e)}")


def _parse_log_line(line: str) -> dict:
    """Parse S3 server access log line."""
    try:
        # S3 log format has space-separated fields with some in brackets/quotes
        parts = []
        current = ""
        in_brackets = False
        in_quotes = False
        
        for char in line:
            if char == "[" and not in_quotes:
                in_brackets = True
            elif char == "]" and in_brackets:
                in_brackets = False
                parts.append(current)
                current = ""
            elif char == '"' and not in_brackets:
                in_quotes = not in_quotes
            elif char == " " and not in_brackets and not in_quotes:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char
        
        if current:
            parts.append(current)
        
        if len(parts) >= 10:
            return {
                "bucket_owner": parts[0] if parts[0] != "-" else None,
                "bucket": parts[1] if parts[1] != "-" else None,
                "timestamp": parts[2] if len(parts) > 2 else None,
                "remote_ip": parts[3] if len(parts) > 3 else None,
                "requester": parts[4] if len(parts) > 4 and parts[4] != "-" else None,
                "request_id": parts[5] if len(parts) > 5 else None,
                "operation": parts[6] if len(parts) > 6 else None,
                "key": parts[7] if len(parts) > 7 and parts[7] != "-" else None,
                "http_status": parts[9] if len(parts) > 9 else None,
                "error_code": parts[10] if len(parts) > 10 and parts[10] != "-" else None,
            }
    except Exception:
        pass
    
    return None


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
