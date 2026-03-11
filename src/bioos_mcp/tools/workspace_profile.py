from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bioos import bioos
from bioos.config import Config
from bioos.resource.workflows import Submission
from bioos.service.api import list_submissions, list_workflows

def get_workspace_profile_data(cfg: Any) -> Dict[str, Any]:
    ak, sk = get_credentials(cfg.ak, cfg.sk)
    bioos.login(access_key=ak, secret_key=sk, endpoint=cfg.endpoint)

    workspace_id, workspace_row = resolve_workspace(cfg.workspace_name)
    ws = bioos.workspace(workspace_id)
    ies_records, ies_warning, ies_coverage = collect_ies_records(ws, cfg)

    workspace_section = build_workspace_section(workspace_id, workspace_row, ws, cfg, ies_records)
    workflows = build_workflows_section(workspace_id)
    workflow_lookup = {item["id"]: item["name"] for item in workflows}
    data_models = build_data_models_section(workspace_id, ws, cfg)
    submissions = build_submissions_section(workspace_id, workflow_lookup, cfg)
    submission_metrics, submission_metric_warnings = collect_submission_metrics(workspace_id, submissions)
    failure_summaries = build_failure_summaries(workspace_id, submissions, cfg)

    artifact_summaries, artifact_warnings, artifact_coverage = collect_artifact_summaries(
        ws,
        workspace_section.get("s3_bucket"),
        submissions,
        cfg,
    )

    ies_apps = build_ies_section(ies_records)
    lineage = build_lineage(submissions)
    summary = build_summary(workflows, data_models, submissions, submission_metrics)

    coverage = {
        "workspace": "partial",
        "workflows": "full",
        "data_models": "full",
        "submissions": "full",
        "failure_details": "full" if cfg.include_failure_details else "not_requested",
        "artifacts": artifact_coverage,
        "ies": ies_coverage,
    }

    warnings: List[str] = []
    if not cfg.include_signed_urls:
        warnings.append("Signed artifact URLs are omitted by default.")
    if workspace_section.get("has_dashboard") is None:
        warnings.append("Dashboard presence is not resolved in this version.")
    if ies_warning:
        warnings.append(ies_warning)
    warnings.extend(artifact_warnings)
    warnings.extend(submission_metric_warnings)

    return {
        "success": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": workspace_section,
        "summary": summary,
        "coverage": coverage,
        "workflows": workflows,
        "data_models": data_models,
        "recent_submissions": submissions,
        "lineage": lineage,
        "failure_summaries": failure_summaries,
        "artifact_summaries": artifact_summaries,
        "ies_apps": ies_apps,
        "warnings": warnings,
    }


def get_credentials(user_ak: Optional[str] = None, user_sk: Optional[str] = None) -> Tuple[str, str]:
    ak = user_ak if user_ak is not None else os.getenv("MIRACLE_ACCESS_KEY")
    sk = user_sk if user_sk is not None else os.getenv("MIRACLE_SECRET_KEY")

    if not ak:
        raise ValueError("未提供 MIRACLE_ACCESS_KEY，请设置环境变量 'MIRACLE_ACCESS_KEY' 或在参数中指定")
    if not sk:
        raise ValueError("未提供 MIRACLE_SECRET_KEY，请设置环境变量 'MIRACLE_SECRET_KEY' 或在参数中指定")

    return ak, sk


def to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (int, float)):
        if value != value:
            return None
        ts = float(value)
        if ts <= 0:
            return None
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def safe_json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def df_records(df: Any) -> List[Dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    return df.to_dict(orient="records")


def normalize_params(items: Any) -> List[Dict[str, Any]]:
    result = []
    for item in items or []:
        result.append(
            {
                "name": item.get("Name"),
                "type": item.get("Type"),
                "required": not bool(item.get("Optional")),
                "default_value": item.get("Default"),
            }
        )
    return result


def resolve_workspace(workspace_name: str) -> Tuple[str, Dict[str, Any]]:
    workspaces = bioos.list_workspaces()
    matched = workspaces[workspaces["Name"] == workspace_name]
    if getattr(matched, "empty", True):
        raise ValueError(f"未找到工作空间：{workspace_name}")
    row = matched.iloc[0].to_dict()
    return str(row["ID"]), row


def summarize_cluster_bindings(env_info: Any) -> List[Dict[str, Any]]:
    records = df_records(env_info)
    summary = []
    for item in records:
        summary.append(
            {
                "cluster_id": item.get("cluster_id"),
                "name": item.get("name"),
                "description": item.get("description"),
                "type": item.get("type"),
            }
        )
    return summary


def summarize_ies_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "none attached webapp type cluster" in lowered:
        return "IES is unavailable for this workspace because no webapp type cluster is attached."
    return f"Failed to query IES apps: {message}"


def collect_ies_records(ws: Any, cfg: Any) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    if not cfg.include_ies:
        return [], None, "not_requested"

    try:
        return df_records(ws.webinstanceapps.list()), None, "full"
    except Exception as exc:
        return [], summarize_ies_error(exc), "partial"


def build_workspace_section(
    workspace_id: str,
    workspace_row: Dict[str, Any],
    ws: Any,
    cfg: Any,
    ies_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    basic_info = ws.basic_info or {}
    cluster_bindings = summarize_cluster_bindings(ws.env_info)

    return {
        "id": workspace_id,
        "name": workspace_row.get("Name") or basic_info.get("name"),
        "description": workspace_row.get("Description") or basic_info.get("description"),
        "owner_name": workspace_row.get("OwnerName") or basic_info.get("owner"),
        "endpoint": cfg.endpoint,
        "s3_bucket": workspace_row.get("S3Bucket") or basic_info.get("s3_bucket"),
        "created_at": to_iso(workspace_row.get("CreateTime") or basic_info.get("create_time")),
        "updated_at": to_iso(workspace_row.get("UpdateTime")),
        "cluster_bindings": cluster_bindings,
        "has_ies": bool(ies_records) if cfg.include_ies else None,
        "has_dashboard": None,
    }


def build_workflows_section(workspace_id: str) -> List[Dict[str, Any]]:
    items = list_workflows(workspace_id=workspace_id, page_number=1, page_size=100) or []
    workflows = []
    for item in items:
        workflows.append(
            {
                "id": item.get("ID"),
                "name": item.get("Name"),
                "description": item.get("Description"),
                "status": (item.get("Status") or {}).get("Phase", item.get("Status")),
                "language": item.get("Language"),
                "source_type": item.get("SourceType"),
                "tag": item.get("Tag"),
                "main_workflow_path": item.get("MainWorkflowPath"),
                "owner_name": item.get("OwnerName"),
                "created_at": to_iso(item.get("CreateTime")),
                "updated_at": to_iso(item.get("UpdateTime")),
                "inputs": normalize_params(item.get("Inputs")),
                "outputs": normalize_params(item.get("Outputs")),
            }
        )
    workflows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return workflows


def preview_data_model_rows(
    workspace_id: str,
    model_id: str,
    sample_rows_per_data_model: int,
) -> Dict[str, Any]:
    content = Config.service().list_data_model_rows(
        {
            "WorkspaceID": workspace_id,
            "ID": model_id,
            "PageNumber": 1,
            "PageSize": sample_rows_per_data_model,
        }
    )
    headers = content.get("Headers", [])
    rows = content.get("Rows", [])
    preview_rows = []
    for row in rows:
        if isinstance(row, list):
            preview_rows.append(dict(zip(headers, row)))
        elif isinstance(row, dict):
            preview_rows.append(row)
    return {
        "columns": headers,
        "sample_rows": preview_rows,
        "row_count": content.get("TotalCount"),
    }


def list_data_model_records(workspace_id: str) -> List[Dict[str, Any]]:
    payload = Config.service().list_data_models({"WorkspaceID": workspace_id}) or {}
    items = payload.get("Items") or []
    if not isinstance(items, list):
        return []

    normal_items = [item for item in items if isinstance(item, dict) and item.get("Type") == "normal"]
    if normal_items:
        return normal_items

    # Some workspaces may return empty Items or records without a Type field.
    return [item for item in items if isinstance(item, dict)]


def build_data_models_section(
    workspace_id: str,
    ws: Any,
    cfg: Any,
) -> List[Dict[str, Any]]:
    models = []
    for item in list_data_model_records(workspace_id):
        model_id = item.get("ID")
        preview = {"columns": [], "sample_rows": [], "row_count": item.get("RowCount")}
        if model_id and cfg.sample_rows_per_data_model > 0:
            try:
                preview = preview_data_model_rows(
                    workspace_id,
                    model_id,
                    cfg.sample_rows_per_data_model,
                )
            except Exception:
                pass
        models.append(
            {
                "id": model_id,
                "name": item.get("Name"),
                "type": item.get("Type"),
                "row_count": preview.get("row_count") or item.get("RowCount"),
                "columns": preview.get("columns", []),
                "sample_rows": preview.get("sample_rows", []),
                "created_at": to_iso(item.get("CreateTime")),
                "updated_at": to_iso(item.get("UpdateTime")),
            }
        )
    return models


def build_submissions_section(
    workspace_id: str,
    workflow_lookup: Dict[str, str],
    cfg: Any,
) -> List[Dict[str, Any]]:
    items = list_submissions(
        workspace_id=workspace_id,
        page_number=1,
        page_size=max(50, cfg.submission_limit),
    ) or []
    items.sort(key=lambda item: item.get("StartTime") or 0, reverse=True)

    submissions = []
    for item in items[: cfg.submission_limit]:
        data_entity = item.get("DataEntity") or {}
        input_binding = safe_json_loads(item.get("Inputs"))
        output_binding = safe_json_loads(item.get("Outputs"))
        submissions.append(
            {
                "id": item.get("ID"),
                "name": item.get("Name"),
                "description": item.get("Description"),
                "status": item.get("Status"),
                "workflow_id": item.get("WorkflowID"),
                "workflow_name": workflow_lookup.get(item.get("WorkflowID")),
                "owner_name": item.get("OwnerName"),
                "start_time": to_iso(item.get("StartTime")),
                "finish_time": to_iso(item.get("FinishTime")),
                "duration_seconds": item.get("Duration"),
                "data_model_id": item.get("DataModelID"),
                "data_model_name": data_entity.get("Name"),
                "row_ids": data_entity.get("RowIDs") or [],
                "cluster_id": item.get("ClusterID"),
                "cluster_type": item.get("ClusterType"),
                "input_binding": input_binding if isinstance(input_binding, dict) else {},
                "output_binding": output_binding if isinstance(output_binding, dict) else {},
                "options": item.get("ExposedOptions") or {},
                "final_execution_dir": item.get("FinalExecutionDir"),
                "run_status": item.get("RunStatus") or {},
            }
        )
    return submissions


def fetch_all_submission_records(workspace_id: str, page_size: int = 100) -> Tuple[List[Dict[str, Any]], int]:
    all_items: List[Dict[str, Any]] = []
    page_number = 1
    total_count: Optional[int] = None

    while True:
        payload = Config.service().list_submissions(
            {
                "WorkspaceID": workspace_id,
                "PageNumber": page_number,
                "PageSize": page_size,
                "Filter": {},
            }
        ) or {}
        if total_count is None and payload.get("TotalCount") is not None:
            total_count = int(payload["TotalCount"])

        items = payload.get("Items") or []
        if not isinstance(items, list) or not items:
            break

        all_items.extend(item for item in items if isinstance(item, dict))

        if total_count is not None and len(all_items) >= total_count:
            break
        if total_count is None and len(items) < page_size:
            break

        page_number += 1

    return all_items, total_count if total_count is not None else len(all_items)


def collect_submission_metrics(
    workspace_id: str,
    submissions: List[Dict[str, Any]],
) -> Tuple[Dict[str, int], List[str]]:
    recent_count = len(submissions)
    fallback_metrics = {
        "submission_count": recent_count,
        "recent_submission_count": recent_count,
        "succeeded_submission_count": sum(1 for item in submissions if item.get("status") == "Succeeded"),
        "failed_submission_count": sum(1 for item in submissions if item.get("status") == "Failed"),
        "running_submission_count": sum(
            1 for item in submissions if item.get("status") in {"Running", "Pending"}
        ),
    }

    try:
        all_submission_items, total_submission_count = fetch_all_submission_records(workspace_id)
        return {
            "submission_count": total_submission_count,
            "recent_submission_count": recent_count,
            "succeeded_submission_count": sum(
                1 for item in all_submission_items if item.get("Status") == "Succeeded"
            ),
            "failed_submission_count": sum(
                1 for item in all_submission_items if item.get("Status") == "Failed"
            ),
            "running_submission_count": sum(
                1 for item in all_submission_items if item.get("Status") in {"Running", "Pending"}
            ),
        }, []
    except Exception as exc:
        return fallback_metrics, [f"Failed to query total submission metrics; falling back to recent submissions: {exc}"]


def summarize_failure_message(raw_message: str) -> str:
    if not raw_message:
        return "Submission failed, but no detailed run error was returned."
    job_match = re.search(r"Job ([^ ]+) exited with return code (\d+)", raw_message)
    if job_match:
        return f"Job {job_match.group(1)} exited with return code {job_match.group(2)}."
    workflow_match = re.search(r'message":"([^"]+)"', raw_message)
    if workflow_match:
        return workflow_match.group(1)
    return raw_message.strip()


def infer_failed_task(raw_message: str) -> Optional[str]:
    match = re.search(r"Job ([^ ]+) exited", raw_message or "")
    if match:
        return match.group(1)
    return None


def build_failure_summaries(
    workspace_id: str,
    submissions: List[Dict[str, Any]],
    cfg: Any,
) -> List[Dict[str, Any]]:
    if not cfg.include_failure_details:
        return []

    summaries = []
    for submission in submissions:
        if submission.get("status") != "Failed":
            continue
        try:
            submission_obj = Submission(workspace_id, submission["id"])
            failed_runs = [run for run in submission_obj.runs if run.status == "Failed"]
            if not failed_runs:
                continue
            run = failed_runs[0]
            raw_message = run.error if isinstance(run.error, str) else ""
            summaries.append(
                {
                    "submission_id": submission["id"],
                    "workflow_name": submission.get("workflow_name"),
                    "run_id": run.id,
                    "failed_task": infer_failed_task(raw_message),
                    "error_summary": summarize_failure_message(raw_message),
                    "raw_message": raw_message,
                }
            )
        except Exception as exc:
            summaries.append(
                {
                    "submission_id": submission["id"],
                    "workflow_name": submission.get("workflow_name"),
                    "run_id": None,
                    "failed_task": None,
                    "error_summary": f"Failed to retrieve run-level error: {exc}",
                    "raw_message": "",
                }
            )
    return summaries


def strip_execution_prefix(execution_dir: Optional[str], bucket: Optional[str]) -> Optional[str]:
    if not execution_dir:
        return None
    if execution_dir.startswith("s3://"):
        key = execution_dir[5:]
        parts = key.split("/", 1)
        if len(parts) == 2:
            bucket_name, object_key = parts
            if bucket and bucket_name == bucket:
                return object_key
            return object_key
    return execution_dir.lstrip("/")


def categorize_file(key: str) -> str:
    name = Path(key).name
    if name == "stdout":
        return "stdout"
    if name == "stderr":
        return "stderr"
    if name == "script":
        return "script"
    if name == "log" or (name.startswith("workflow.") and name.endswith(".log")):
        return "log"
    if name == "rc" or name.endswith(".list") or name == "cromwell_glob_control_file":
        return "control"
    return "result"


def summarize_artifacts(
    ws: Any,
    bucket: Optional[str],
    submission: Dict[str, Any],
    cfg: Any,
) -> Optional[Dict[str, Any]]:
    prefix = strip_execution_prefix(submission.get("final_execution_dir"), bucket)
    if not prefix:
        return None

    files_df = ws.files.list(prefix=prefix, recursive=True)
    records = df_records(files_df)
    if not records:
        return None

    total_size = 0
    sample_files = []
    for record in records:
        size = record.get("size") or 0
        if size != size:
            size = 0
        size = int(size)
        total_size += size
        entry = {
            "key": record.get("key"),
            "size_bytes": size,
            "category": categorize_file(record.get("key", "")),
        }
        if cfg.include_signed_urls:
            entry["s3_url"] = record.get("s3_url")
            entry["https_url"] = record.get("https_url")
        sample_files.append(entry)

    order = {"result": 0, "log": 1, "stderr": 2, "stdout": 3, "script": 4, "control": 5}
    sample_files.sort(key=lambda item: (order.get(item["category"], 99), -item["size_bytes"]))

    categories = {item["category"] for item in sample_files}
    return {
        "submission_id": submission["id"],
        "workflow_name": submission.get("workflow_name"),
        "execution_dir": prefix,
        "file_count": len(records),
        "total_size_bytes": total_size,
        "has_stdout": "stdout" in categories,
        "has_stderr": "stderr" in categories,
        "has_workflow_log": "log" in categories,
        "has_result_files": "result" in categories,
        "sample_files": sample_files[: cfg.artifact_limit_per_submission],
    }


def collect_artifact_summaries(
    ws: Any,
    bucket: Optional[str],
    submissions: List[Dict[str, Any]],
    cfg: Any,
) -> Tuple[List[Dict[str, Any]], List[str], str]:
    if not cfg.include_artifacts:
        return [], [], "not_requested"

    artifact_summaries: List[Dict[str, Any]] = []
    warnings: List[str] = []
    had_error = False

    for submission in submissions:
        try:
            artifact_summary = summarize_artifacts(ws, bucket, submission, cfg)
            if artifact_summary:
                artifact_summaries.append(artifact_summary)
        except Exception as exc:
            had_error = True
            warnings.append(
                f"Failed to summarize artifacts for submission {submission.get('id')}: {exc}"
            )

    return artifact_summaries, warnings, "partial" if had_error else "full"


def build_ies_section(ies_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ies_apps = []
    for item in ies_records:
        status = item.get("Status")
        state = status.get("State") if isinstance(status, dict) else str(status)
        ies_apps.append(
            {
                "id": item.get("ID"),
                "name": item.get("Name"),
                "description": item.get("Description"),
                "state": state,
                "owner_name": item.get("OwnerName"),
                "resource_size": item.get("ResourceSize"),
                "storage_capacity": item.get("StorageCapacity"),
                "created_at": to_iso(item.get("CreateTime")),
                "updated_at": to_iso(item.get("UpdateTime")),
            }
        )
    return ies_apps


def build_lineage(submissions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lineage = []
    for submission in submissions:
        lineage.append(
            {
                "data_model_id": submission.get("data_model_id"),
                "data_model_name": submission.get("data_model_name"),
                "workflow_id": submission.get("workflow_id"),
                "workflow_name": submission.get("workflow_name"),
                "submission_id": submission.get("id"),
                "submission_status": submission.get("status"),
                "row_ids": submission.get("row_ids", []),
                "final_execution_dir": submission.get("final_execution_dir"),
            }
        )
    return lineage


def build_summary(
    workflows: List[Dict[str, Any]],
    data_models: List[Dict[str, Any]],
    submissions: List[Dict[str, Any]],
    submission_metrics: Dict[str, int],
) -> Dict[str, Any]:
    total_submissions = submission_metrics.get("submission_count", len(submissions))
    recent_submissions = submission_metrics.get("recent_submission_count", len(submissions))
    succeeded = submission_metrics.get(
        "succeeded_submission_count",
        sum(1 for item in submissions if item.get("status") == "Succeeded"),
    )
    failed = submission_metrics.get(
        "failed_submission_count",
        sum(1 for item in submissions if item.get("status") == "Failed"),
    )
    running = submission_metrics.get(
        "running_submission_count",
        sum(1 for item in submissions if item.get("status") in {"Running", "Pending"}),
    )
    latest_submission = submissions[0] if submissions else None

    if failed > 0 and succeeded == 0:
        health_status = "error"
    elif failed > 0 or running > 0:
        health_status = "warning"
    else:
        health_status = "healthy"

    health_summary = (
        f"Workspace has {len(workflows)} workflows, {len(data_models)} data models, "
        f"and {total_submissions} total submissions."
    )
    if recent_submissions != total_submissions:
        health_summary += f" This profile includes details for the {recent_submissions} most recent submissions."
    if failed > 0:
        health_summary += f" {failed} submission(s) failed."
    elif running > 0:
        health_summary += f" {running} submission(s) still running or pending."
    else:
        health_summary += " No recent failures were found."

    return {
        "workflow_count": len(workflows),
        "data_model_count": len(data_models),
        "submission_count": total_submissions,
        "recent_submission_count": recent_submissions,
        "succeeded_submission_count": succeeded,
        "failed_submission_count": failed,
        "running_submission_count": running,
        "latest_submission_id": latest_submission.get("id") if latest_submission else None,
        "latest_activity_at": latest_submission.get("finish_time") if latest_submission else None,
        "health_status": health_status,
        "health_summary": health_summary,
    }
