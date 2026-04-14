import boto3
import time
import re
from datetime import datetime
from collections import defaultdict
import json
import uuid
# sts = boto3.client("sts",region_name="us-east-1")

# # Get temporary credentials
# creds = response["Credentials"]
# Use them to create CloudWatch Logs client
# logs_client = boto3.client(
#     "logs",
#     region_name="us-east-1",
#     aws_access_key_id=creds["AccessKeyId"],
#     aws_secret_access_key=creds["SecretAccessKey"],
#     aws_session_token=creds["SessionToken"]
# )

logs_client = boto3.client("logs", region_name="us-east-1")

# Test
# print(logs_client.describe_log_groups(limit=5))
def get_log_groups(logs_client) -> list[str]:
    log_groups_final = []
    next_token = None # For pagination (otherwise it goes only for first page)
    

    # print("loggroups: ")
    while True:
        if next_token:
            log_groups = logs_client.describe_log_groups(nextToken= next_token)
        else:
            log_groups = logs_client.describe_log_groups()
        # Print log group names
        for lg in log_groups["logGroups"]:
            log_groups_final.append(lg["logGroupName"])

        next_token = log_groups.get("nextToken")

        if not next_token:
            break

    return log_groups_final


def parse_log_line(line: str) -> dict:
    """Parse a log line and extract structured information."""
    result = {
        'raw': line,
        'message': line,
        'level': None,
        'request_id': None,
        'metadata': {},
        'is_continuation': False
    }
    if line.startswith("INIT_"):
        result["phase"] = "init"
    elif line.startswith("START"):
        result["phase"] = "invoke"
    elif line.startswith("END") or line.startswith("REPORT"):
        result["phase"] = "invoke"
    
    # Check if stack trace continuation
    if line.startswith(('\t', '    ', 'at ', '  at ')):
        result['is_continuation'] = True
        return result
    
    # Try to parse as JSON
    if line.strip().startswith('{'):
        try:
            parsed = json.loads(line)
            result['message'] = parsed.get('message') or parsed.get('msg') or line
            result['level'] = parsed.get('level') or parsed.get('severity')
            result['request_id'] = (parsed.get('request_id') or 
                                   parsed.get('requestId') or 
                                   parsed.get('trace_id'))
            result['metadata'] = {k: v for k, v in parsed.items() 
                                 if k not in ['message', 'msg', 'level', 'severity', 'request_id', 'requestId']}
            return result
        except json.JSONDecodeError:
            pass
    
    # Parse Lambda START/END/REPORT lines
    if 'RequestId:' in line:
        match = re.search(r'RequestId: ([\w-]+)', line)
        if match:
            result['request_id'] = match.group(1)
        
        # Extract metrics from REPORT line
        if line.startswith('REPORT'):
            result['type'] = 'report'
            duration_match = re.search(r'Duration: ([\d.]+) ms', line)
            memory_match = re.search(r'Memory Used: (\d+) MB', line)
            billed_match = re.search(r'Billed Duration: (\d+) ms', line)
            max_memory_match = re.search(r'Max Memory Used: (\d+) MB', line)
            init_match = re.search(r'Init Duration: ([\d.]+) ms', line)
            
            if duration_match:
                result['metadata']['duration_ms'] = float(duration_match.group(1))
            if memory_match:
                result['metadata']['memory_used_mb'] = int(memory_match.group(1))
            if billed_match:
                result['metadata']['billed_duration_ms'] = int(billed_match.group(1))
            if max_memory_match:
                result['metadata']['max_memory_mb'] = int(max_memory_match.group(1))
            if init_match:
                result['metadata']['init_duration_ms'] = float(init_match.group(1))
                result['metadata']['is_cold_start'] = True
        
        
        elif line.startswith('START'):
            result['type'] = 'start'
        elif line.startswith('END'):
            result['type'] = 'end'
    
    # Extract log level from plain text
    level_match = re.search(r'\b(ERROR|WARN|WARNING|INFO|DEBUG)\b', line, re.IGNORECASE)
    if level_match:
        result['level'] = level_match.group(1).upper()
    
    return result


def fetch_all_logs(logs_client, log_group, filter_pattern=''):
    """Fetch all logs with full metadata (not just text)."""
    all_logs = []
    next_token = None
    
    while True:
        kwargs = {
            "logGroupName": log_group,
            "filterPattern": filter_pattern,
            "limit": 1000,
        }
        if next_token:
            kwargs["nextToken"] = next_token
        
        response = logs_client.filter_log_events(**kwargs)
        cnt =0
        for event in response.get('events', []):
            msg = event.get('message')

            if msg and '\\x' not in msg and 'StreamingBody' not in msg:
                # Parse the log line
                # print("message:", end='\n')
                # print(msg)
                parsed = parse_log_line(msg)
                # print("Parsed:", end='\n')
                # print(parsed)
                # Add CloudWatch metadata
                log_entry = {
                    'log_group': log_group,
                    'log_stream': event['logStreamName'],
                    'timestamp': event['timestamp'],
                    'timestamp_iso': datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
                    **parsed
                }
                all_logs.append(log_entry)
                # cnt +=1
                # if cnt == 5:
                #     break
        # break
        next_token = response.get('nextToken')
        if not next_token:
            break
    
    return all_logs


# def fetch_logs(logs_client, log_group):
#     # Filter events
#     events = logs_client.filter_log_events(
#         logGroupName= log_group,
#         # filterPattern='ERROR',
        
#         filterPattern='?ERROR ?INFO ?DEBUG ?WARN ?Exception ?Processing ?Input ?Output',
#         limit=100
#     )
#     # print(events['events'])
#     log_texts = [
#         e['message'] for e in events['events']
#         if '\\x' not in e['message'] and 'StreamingBody' not in e['message']
#     ]

#     return log_texts
 

def clean_logs(log_lines):
    normalized = []

    for line in log_lines:
        line = line.replace("\r\n", "\n").replace("\r", "\n")
        line = line.replace("\xa0", " ")
        normalized.append(line.rstrip())

    return "\n".join(normalized)


def assign_request_ids(logs):
    """Assign request_id based on log stream and temporal proximity."""
    # Sort by log_stream then timestamp
    sorted_logs = sorted(logs, key=lambda x: (x['log_stream'], x['timestamp']))
    
    current_request_id = None
    current_log_stream = None
    last_timestamp = None
    
    for log in sorted_logs:
        # Reset if log stream changed
        if log['log_stream'] != current_log_stream:
            current_request_id = None
            current_log_stream = log['log_stream']
            last_timestamp = None
        
        # Reset if time gap > 30 seconds (different execution)
        if last_timestamp and (log['timestamp'] - last_timestamp) > 30000:
            current_request_id = None
        
        # Update current request_id if this log has one
        if log.get('request_id'):
            current_request_id = log['request_id']
        # Assign current request_id if available
        elif current_request_id:
            log['request_id'] = current_request_id
        
        last_timestamp = log['timestamp']
    
    return logs

def group_by_request_id(logs: list[dict]) -> dict:
    """Group logs by Lambda request ID."""
    grouped = defaultdict(list)
    
    for log in logs:
        request_id = log.get('request_id')
        if request_id:
            grouped[request_id].append(log)
        else:
            # For logs without request ID, create individual groups
            grouped[f"ungrouped_{log['timestamp']}"].append(log)
    
    return dict(grouped)


def merge_continuations(logs):
    """Merge stack trace continuations with previous log entry."""
    merged = []
    current = None
    
    for log in sorted(logs, key=lambda x: x["timestamp"]):
        is_continuation = log.get("is_continuation")
        can_merge = current and current.get("type") not in {"start", "end", "report"}
        
        if is_continuation and can_merge:
            current["message"] += "\n" + log["message"]
            current["raw"] += "\n" + log["raw"]
        elif not is_continuation:
            if current:
                merged.append(current)
            current = log
        # Skip orphaned/problematic continuations
    
    if current:
        merged.append(current)
    
    return merged


# def create_rag_documents(grouped):
#     documents = []

#     for request_id, logs in grouped.items():
#         logs = sorted(logs, key=lambda x: x["timestamp"])
#         first_log, last_log = logs[0], logs[-1]

#         # Aggregate metadata safely
#         execution_metrics = {}
#         for log in logs:
#             for k, v in log.get("metadata", {}).items():
#                 execution_metrics.setdefault(k, v)

#         # Errors
#         error_logs = [
#             log for log in logs
#             if log.get("level") in {"ERROR", "WARN", "WARNING"}
#         ]

#         error_summary = [
#             log["message"][:200] for log in error_logs[:3]
#         ]

#         # Build structured content
#         content_lines = []
#         for log in logs:
#             prefix = f"[{log['timestamp_iso']}]"
#             if log.get("phase"):
#                 prefix += f" [{log['phase'].upper()}]"
#             content_lines.append(
#                 f"{prefix} {log.get('level','INFO')}: {log['message']}"
#             )

#         metadata = {
#             "request_id": request_id,
#             "function_name": first_log["log_group"].split("/")[-1],
#             "log_group": first_log["log_group"],
#             "log_stream": first_log["log_stream"],
#             "start_time": first_log["timestamp_iso"],
#             "end_time": last_log["timestamp_iso"],
#             "log_count": len(logs),

#             # Error info
#             "has_error": bool(error_logs),
#             "error_count": len(error_logs),
#             "error_summary": error_summary,

#             # Execution metrics
#             **execution_metrics,
#         }

#         documents.append({
#             "page_content": "\n".join(content_lines),
#             "metadata": metadata,
#         })

#     return documents



def create_rag_documents(grouped):
    documents = []

    for request_id, logs in grouped.items():
        logs = sorted(logs, key=lambda x: x["timestamp"])
        first_log, last_log = logs[0], logs[-1]

        # Aggregate metadata safely
        execution_metrics = {}
        for log in logs:
            for k, v in log.get("metadata", {}).items():
                execution_metrics.setdefault(k, v)

        # Errors
        error_logs = [
            log for log in logs
            if log.get("level") in {"ERROR", "WARN", "WARNING"}
        ]

        error_summary = [
            log["message"][:200] for log in error_logs[:3]
        ]
        
        # ADD THIS: Extract error types safely
        error_types = []
        missing_modules = []
        if error_logs:
            for log in error_logs:
                # Extract error type
                match = re.search(r'([A-Z]\w+Error)', log['message'])
                if match:
                    error_types.append(match.group(1))
                
                # Extract missing module
                match = re.search(r"No module named '(\w+)'", log['message'])
                if match:
                    missing_modules.append(match.group(1))

        # CHANGE THIS: Build better content structure
        content_lines = []
        
        # Add summary header
        function_name = first_log["log_group"].split("/")[-1]
        content_lines.append(f"Lambda function: {function_name}")
        content_lines.append(f"Request ID: {request_id}")
        
        if error_types:
            content_lines.append(f"Errors: {', '.join(set(error_types))}")
        if missing_modules:
            content_lines.append(f"Missing modules: {', '.join(set(missing_modules))}")
        
        content_lines.append("\n--- Logs ---")
        
        # Add log lines (keep your original format or shorten timestamps)
        for log in logs:
            prefix = f"[{log['timestamp_iso']}]"
            if log.get("phase"):
                prefix += f" [{log['phase'].upper()}]"
            content_lines.append(
                f"{prefix} {log.get('level','INFO')}: {log['message']}"
            )

        metadata = {
            "request_id": request_id,
            "function_name": function_name,  # ADD THIS
            "log_group": first_log["log_group"],
            "log_stream": first_log["log_stream"],
            "start_time": first_log["timestamp_iso"],
            "end_time": last_log["timestamp_iso"],
            "log_count": len(logs),

            # Error info
            "has_error": bool(error_logs),
            "error_count": len(error_logs),
            "error_summary": error_summary,
            "error_types": list(set(error_types)),  # ADD THIS
            "missing_modules": list(set(missing_modules)),  # ADD THIS

            # Execution metrics
            **execution_metrics,
        }

        documents.append({
            "page_content": "\n".join(content_lines),
            "metadata": metadata,
        })

    return documents
# # OR start a Logs Insights query
# query_id = logs_client.start_query(
#     logGroupName='/aws/lambda/test',
#     startTime=1670000000,   # unix timestamp
#     endTime=1679999999,     # unix timestamp
#     queryString='fields @timestamp, @message | sort @timestamp desc | limit 20'
# )['queryId']

# results = logs_client.get_query_results(queryId=query_id)
# print(results)

from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams

def store_documents(documents):
    # Initialize client
    client = QdrantClient(url="http://localhost:6333")
    collection_name = "cloudwatch-documents"
    model_name = "BAAI/bge-small-en"
    
    # Create collection
    if not client.collection_exists(collection_name=collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=client.get_embedding_size(model_name),  # ✅ This works!
                distance=models.Distance.COSINE
            ),
        )
        
    # Prepare data
    docs = [doc['page_content'] for doc in documents]
    
    # Merge page_content into metadata for storage
    payloads = []
    for doc in documents:
        payload = {
            "text": doc["page_content"],  # Store original text
            **doc["metadata"]              # All metadata fields
        }
        payloads.append(payload)
    
    # Generate IDs
    ids = [str(uuid.uuid4()) for _ in documents]
    
    
    # Upload with FastEmbed integration
    client.upload_collection(
        collection_name=collection_name,
        vectors=[models.Document(text=doc, model=model_name) for doc in docs],
        payload=payloads,
        ids=ids,
    )
    
    info = client.get_collection(collection_name)
    print(f"✅ Collection now has {info.points_count} total documents")

    return client

log_groups  = get_log_groups(logs_client)
# print(log_groups)
log_group = '/aws/lambda/CoverLetterGen'
text = fetch_all_logs(logs_client, log_group)
# print(text)


# def main():
#     # Get all log groups (or specify manually)
#     log_groups = get_log_groups(logs_client)
#     print(f"Found {len(log_groups)} log groups")
    
#     # Filter for Lambda logs (or specify your target log group)
#     target_log_group = '/aws/lambda/CoverLetterGen'
    
#     print(f"\nProcessing: {target_log_group}")
    
#     # Fetch all logs with structure
#     all_logs = fetch_all_logs(logs_client, target_log_group)
#     print(f"Fetched {len(all_logs)} log entries")
#     all_logs = assign_request_ids(all_logs)  # <- Add this
#     grouped = group_by_request_id(all_logs)

#     for req_id in grouped:
#         grouped[req_id] = merge_continuations(grouped[req_id])
    
#     documents = create_rag_documents(grouped)
#     print(f"Created {len(documents)} RAG documents\n")

#     client = store_documents(documents)
#     print(client)
    
    # Save as JSONL (one JSON object per line)
    # with open("logs.jsonl", "w") as f:
    #     for doc in documents:
    #         f.write(json.dumps(doc) + '\n')
    
    # print("Saved to logs.jsonl")
    
  # print(all_logs[23])

    # with open("logs.jsonl", "w") as f:
    #     for req_id, logs in grouped.items():  # ← Use .items() to get both
    #         document = {
    #             'request_id': req_id,
    #             'log_count': len(logs),
    #             'logs': logs
    #         }
    #         f.write(json.dumps(document) + "\n")

    # with open("logs.txt", "w") as f:
    #     f.write(all_logs[1])
    
    # Group by request ID
    # grouped = group_by_request_id(all_logs)
    # print(f"Grouped into {len(grouped)} executions")
# cleaned_text = clean_logs(text)

# print(cleaned_text)
# with open("logs.txt", "w") as f:
#     f.write(cleaned_text)

# if __name__ == "__main__":
#     main()