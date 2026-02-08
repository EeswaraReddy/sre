"""Verify source data availability and validity."""
import json
import boto3
from datetime import datetime
from typing import Any


s3 = boto3.client("s3")
glue = boto3.client("glue")


def handler(event: dict, context: Any) -> dict:
    """Verify source data exists and is valid.
    
    Args:
        event: Contains s3_path OR (database, table_name), optional partition_filter
    
    Returns:
        Data availability status, file counts, and sample metadata
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        
        s3_path = body.get("s3_path")
        database = body.get("database")
        table_name = body.get("table_name")
        partition_filter = body.get("partition_filter")  # e.g., "dt='2024-01-15'"
        
        result = {"verified": False, "checks": []}
        
        if s3_path:
            # Direct S3 path verification
            result.update(_verify_s3_path(s3_path))
        elif database and table_name:
            # Glue table verification
            result.update(_verify_glue_table(database, table_name, partition_filter))
        else:
            return _error_response(400, "Either s3_path or (database + table_name) is required")
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error verifying source data: {str(e)}")


def _verify_s3_path(s3_path: str) -> dict:
    """Verify data at S3 path."""
    result = {
        "source_type": "s3",
        "path": s3_path,
        "checks": []
    }
    
    try:
        # Parse S3 path
        if s3_path.startswith("s3://"):
            path = s3_path[5:]
        else:
            path = s3_path
        
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        
        result["bucket"] = bucket
        result["prefix"] = prefix
        
        # Check bucket exists and is accessible
        try:
            s3.head_bucket(Bucket=bucket)
            result["checks"].append({"check": "bucket_accessible", "status": "pass"})
        except s3.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            result["checks"].append({
                "check": "bucket_accessible", 
                "status": "fail",
                "error": f"Bucket not accessible: {error_code}"
            })
            result["verified"] = False
            return result
        
        # List objects at path
        response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=1000
        )
        
        objects = response.get("Contents", [])
        total_objects = len(objects)
        
        if total_objects == 0:
            result["checks"].append({
                "check": "data_exists",
                "status": "fail",
                "error": "No objects found at path"
            })
            result["verified"] = False
            return result
        
        result["checks"].append({
            "check": "data_exists",
            "status": "pass",
            "object_count": total_objects
        })
        
        # Calculate total size
        total_size = sum(obj["Size"] for obj in objects)
        result["total_size_bytes"] = total_size
        result["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        # Check for zero-byte files
        zero_byte_files = [obj["Key"] for obj in objects if obj["Size"] == 0]
        if zero_byte_files:
            result["checks"].append({
                "check": "no_empty_files",
                "status": "warn",
                "empty_file_count": len(zero_byte_files),
                "sample_empty_files": zero_byte_files[:5]
            })
        else:
            result["checks"].append({"check": "no_empty_files", "status": "pass"})
        
        # Check recency
        latest_modified = max(obj["LastModified"] for obj in objects)
        result["latest_modified"] = latest_modified
        
        hours_since_update = (datetime.now(latest_modified.tzinfo) - latest_modified).total_seconds() / 3600
        if hours_since_update > 48:
            result["checks"].append({
                "check": "data_recency",
                "status": "warn",
                "hours_since_update": round(hours_since_update, 1)
            })
        else:
            result["checks"].append({
                "check": "data_recency",
                "status": "pass",
                "hours_since_update": round(hours_since_update, 1)
            })
        
        # Sample file info
        result["sample_files"] = [
            {
                "key": obj["Key"].split("/")[-1],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"]
            }
            for obj in objects[:5]
        ]
        
        # Overall verification
        failed_checks = [c for c in result["checks"] if c["status"] == "fail"]
        result["verified"] = len(failed_checks) == 0
        
    except Exception as e:
        result["error"] = str(e)
        result["verified"] = False
    
    return result


def _verify_glue_table(database: str, table_name: str, partition_filter: str = None) -> dict:
    """Verify Glue table and its data."""
    result = {
        "source_type": "glue_table",
        "database": database,
        "table_name": table_name,
        "checks": []
    }
    
    try:
        # Get table metadata
        table_response = glue.get_table(DatabaseName=database, Name=table_name)
        table = table_response["Table"]
        
        result["checks"].append({"check": "table_exists", "status": "pass"})
        
        # Table info
        result["table_type"] = table.get("TableType")
        result["location"] = table.get("StorageDescriptor", {}).get("Location")
        result["input_format"] = table.get("StorageDescriptor", {}).get("InputFormat")
        result["columns"] = [
            {"name": col["Name"], "type": col["Type"]}
            for col in table.get("StorageDescriptor", {}).get("Columns", [])
        ]
        result["partition_keys"] = [
            {"name": pk["Name"], "type": pk["Type"]}
            for pk in table.get("PartitionKeys", [])
        ]
        
        # Check partitions
        if table.get("PartitionKeys"):
            params = {"DatabaseName": database, "TableName": table_name, "MaxResults": 100}
            if partition_filter:
                params["Expression"] = partition_filter
            
            partitions_response = glue.get_partitions(**params)
            partitions = partitions_response.get("Partitions", [])
            
            if len(partitions) == 0:
                result["checks"].append({
                    "check": "partitions_exist",
                    "status": "fail",
                    "error": "No partitions found" + (f" matching {partition_filter}" if partition_filter else "")
                })
            else:
                result["checks"].append({
                    "check": "partitions_exist",
                    "status": "pass",
                    "partition_count": len(partitions)
                })
                
                # Sample partition info
                result["sample_partitions"] = [
                    {
                        "values": p.get("Values"),
                        "location": p.get("StorageDescriptor", {}).get("Location")
                    }
                    for p in partitions[:5]
                ]
        
        # Verify S3 location
        if result.get("location"):
            s3_result = _verify_s3_path(result["location"])
            result["s3_verification"] = {
                "verified": s3_result.get("verified"),
                "object_count": next(
                    (c.get("object_count") for c in s3_result.get("checks", []) 
                     if c.get("check") == "data_exists"), None
                ),
                "total_size_mb": s3_result.get("total_size_mb")
            }
            
            if not s3_result.get("verified"):
                result["checks"].append({
                    "check": "s3_data_exists",
                    "status": "fail",
                    "error": "S3 location has no data"
                })
            else:
                result["checks"].append({"check": "s3_data_exists", "status": "pass"})
        
        # Overall verification
        failed_checks = [c for c in result["checks"] if c["status"] == "fail"]
        result["verified"] = len(failed_checks) == 0
        
    except glue.exceptions.EntityNotFoundException as e:
        result["checks"].append({
            "check": "table_exists",
            "status": "fail",
            "error": str(e)
        })
        result["verified"] = False
    except Exception as e:
        result["error"] = str(e)
        result["verified"] = False
    
    return result


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
