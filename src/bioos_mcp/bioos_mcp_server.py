"""Bio-OS MCP 服务器

这个模块实现了一个 MCP 服务器，提供了 Bio-OS 工作流管理和 Docker 镜像构建的功能。
"""

from bioos_mcp.tools.rerank_client import RerankClient
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Union
from pydantic import BaseModel, Field, model_validator, field_validator
import requests
from mcp.server.fastmcp import FastMCP

from bioos_mcp.tools.dockstore_search import DockstoreSearch
from bioos_mcp.tools.fetch_wdl_from_dockstore import DockstoreDownloader
from bioos.resource.workflows import Submission
from bioos_mcp.tools.compose_tools import build_inputs
from bioos import bioos
import asyncio, functools


# 创建 MCP 服务器，不设置连接超时时间
mcp = FastMCP("Bio-OS-MCP-Server")

# 默认的 Bio-OS endpoint
DEFAULT_ENDPOINT = "https://bio-top.miracle.ac.cn"


RERANKER = RerankClient(api_url="http://10.22.17.85:10802/rerank")


# 辅助函数：获取 ak、sk，用户输入优先
def get_credentials(user_ak: Optional[str] = None, user_sk: Optional[str] = None) -> Tuple[str, str]:
    """获取 ak、sk，用户输入优先于环境变量"""
    ak = user_ak if user_ak is not None else os.getenv("MIRACLE_ACCESS_KEY")
    sk = user_sk if user_sk is not None else os.getenv("MIRACLE_SECRET_KEY")
    
    if not ak:
        raise ValueError("未提供 MIRACLE_ACCESS_KEY，请设置环境变量 'MIRACLE_ACCESS_KEY' 或在参数中指定")
    if not sk:
        raise ValueError("未提供 MIRACLE_SECRET_KEY，请设置环境变量 'MIRACLE_SECRET_KEY' 或在参数中指定")
    
    return ak, sk

def get_workspace_id_by_name(workspace_name: str) -> str:
    """根据工作空间名称解析得到其 ID"""
    workspaces = bioos.list_workspaces()
    workspace_info = workspaces.query(f"Name=='{workspace_name}'")
    if getattr(workspace_info, "empty", True):
        raise ValueError(f"未找到工作空间：{workspace_name}")
    return str(workspace_info["ID"].iloc[0])

def load_miracle_env_from_parent_proc():
    """
    Read the parent process environment and write all variables
    starting with 'MIRACLE' into the current process environment.
    """
    ppid = os.getppid()  # get parent process ID
    try:
        # Open the parent process's environ file
        with open(f"/proc/{ppid}/environ", "rb") as f:
            raw = f.read().decode()
            parent_env = dict(x.split("=", 1) for x in raw.split("\x00") if "=" in x)
        
        # Only write variables starting with 'MIRACLE' to current environment
        for k, v in parent_env.items():
            if k.startswith("MIRACLE"):
                os.environ[k] = v
                # Optional: print confirmation
                print(f"Loaded {k}={v}")
    except Exception as e:
        print(f"Failed to load parent MIRACLE env: {e}")




class WDLValidateConfig(BaseModel):
    """WDL 文件验证配置"""
    wdl_path: str = Field(..., description="待验证的WDL 文件路径")


# ----- 工作流相关配置 -----
class SubmitWorkflowConfig(BaseModel):
    # 必填
    workspace_name: str = Field(..., description="目标 Workspace 名称（--workspace_name）")
    workflow_name: str = Field(..., description="目标 Workflow 名称（--workflow_name）")
    input_json: str = Field(..., description="Cromwell Womtools 格式的输入 JSON 文件路径（--input_json）")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点（--endpoint）")
    ak: Optional[str] = Field(default=None, description="Access Key；为空则从环境变量 MIRACLE_ACCESS_KEY 获取")
    sk: Optional[str] = Field(default=None, description="Secret Key；为空则从环境变量 MIRACLE_SECRET_KEY 获取")
    # 可选：bw 其他参数
    data_model_name: Optional[str] = Field(default=None, description="在平台生成的数据模型名称（--data_model_name）")
    call_caching: bool = Field(default=False, description="是否启用 call caching（--call_caching）")
    submission_desc: Optional[str] = Field(default=None, description="本次提交的描述（--submission_desc）")
    force_reupload: bool = Field(default=False, description="是否强制重新上传已存在的 TOS 文件（--force_reupload）")
    mount_tos: bool = Field(default=False, description="是否挂载 TOS（--mount_tos）")
    monitor: bool = Field(default=False, description="是否监控任务直至结束（--monitor）")
    monitor_interval: Optional[int] = Field(
        default=None, ge=1, description="监控模式下的查询间隔（秒）（--monitor_interval）"
    )
    download_results: bool = Field(default=False, description="是否在结束后下载结果（--download_results）")
    download_dir: Optional[str] = Field(default=None, description="下载结果的本地目录（--download_dir）")


class WorkflowImportStatusConfig(BaseModel):
    """工作流导入状态查询配置"""
    workspace_name: str = Field(..., description="工作空间名称")
    workflow_id: str = Field(..., description="工作流ID")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class BioosWorkspaceConfig(BaseModel):
    """Bio-OS 工作空间创建配置"""
    workspace_name: str = Field(..., description="要创建的工作空间名称")
    workspace_description: str = Field(..., description="工作空间描述")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")

class BioosExportWorkspace(BaseModel):
    """导出 Bio-OS 工作空间元信息"""
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    workspace_name: str = Field(..., description="要导出的工作空间名称")
    export_path: str = Field(..., description="导出工作空间元信息保存的路径（绝对路径）")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class BioosCreateIesapp(BaseModel):
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    workspace_name: str = Field(..., description="目标工作空间名称")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    ies_name: str = Field(..., description="要新建的 iesapp 的名字")
    ies_desc: str = Field(..., description="IES描述")
    ies_resource: str = Field(default="2c-4gib", description="资源规格，如 2c-4gib")
    ies_storage: int = Field(default=42949672960, description="存储容量（字节）")
    ies_image: str = Field(default="registry-vpc.miracle.ac.cn/infcprelease/ies-default:latest", description="Docker 镜像地址，必须是可访问的镜像仓库地址")
    ies_ssh: bool = Field(default=True, description="是否开启 SSH")
    ies_run_limit: int = Field(default=10800, description="最长运行时间（秒）")
    ies_idle_timeout: int = Field(default=10800, description="空闲超时（秒）")
    ies_auto_start: bool = Field(default=True, description="是否自动启动")


class Check_iesapp_status(BaseModel):
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    workspace_name: str = Field(..., description="要查看的工作空间名称")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    ies_name: str = Field(..., description="要查看的 iesapp 的名字")


class GetIesEvents(BaseModel):
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    workspace_name: str = Field(..., description="要查看的工作空间名称")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    ies_name: str = Field(..., description="要查看的iesapp的名字")


class BioosS3FileUploader(BaseModel):
    """Bio-OS S3文件上传器"""
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    workspace_name: str = Field(..., description="目标工作空间名称")
    local_file_path: str = Field(..., description="本地文件路径")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class BioosWorkflowJsonConfig(BaseModel):
    "Bio-OS 上已导入 workflow 的 inputs.json 构建和任务投递"
    workspace_name: str = Field(..., description="工作空间名称")
    workflow_name: str = Field(..., description="工作流名称")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class BioosDeleteSubmissionConfig(BaseModel):
    """Bio-OS 删除工作流提交配置"""
    workspace_name: str = Field(..., description="工作空间名称")
    submission_id: str = Field(..., description="要删除的提交ID")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class ListWorkspaceConfig(BaseModel):
    """列出工作空间列表配置"""
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    page_size: Optional[int] = Field(default=None, ge=1, description="返回的最大条目数（仅在 MCP 侧进行裁剪，非服务端分页）")


class WorkflowImportConfig(BaseModel):
    """工作流导入配置"""
    workspace_name: str = Field(..., description="工作空间名称")
    workflow_name: str = Field(..., description="工作流名称")
    workflow_source: str = Field(..., description="WDL 源文件或目录的绝对路径")
    workflow_desc: str = Field(..., description="工作流描述")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥，为空时从环境变量获取")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥，为空时从环境变量获取")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    main_workflow_path: Optional[str] = Field(
        default=None,
        description="主 WDL 文件路径。当 workflow_source 是目录时必填，需指定主 WDL 文件的路径"
    )


class WorkflowStatusConfig(BaseModel):
    """工作流运行状态查询配置"""
    workspace_name: str = Field(..., description="工作空间名称")
    submission_id: str = Field(..., description="提交ID")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")


class WorkflowLogsConfig(BaseModel):
    """工作流日志获取配置"""
    workspace_name: str = Field(..., description="工作空间名称")
    submission_id: str = Field(..., description="提交ID")
    ak: Optional[str] = Field(default=None, description="Bio-OS 访问密钥")
    sk: Optional[str] = Field(default=None, description="Bio-OS 私钥")
    endpoint: str = Field(default=DEFAULT_ENDPOINT, description="Bio-OS 实例平台端点")
    output_dir: str = Field(default=".", description="日志输出目录")


class WorkflowInputParams(BaseModel):
    """工作流输入参数配置（支持单/多样本 + 样本数量校验）"""

    template_json: str = Field(..., description="模板 JSON 路径")
    output_json: str   = Field(..., description="生成的 inputs.json 路径")

    sample_count: int = Field(..., gt=0, description="用户声称的样本数量 (>=1)")

    # 接受单样本 dict 或多样本 list[dict]
    params: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(
        ..., description="单样本 dict 或多样本 list[dict]"
    )

    @model_validator(mode="before")
    def _normalize_params(cls, values):
        raw = values.get("params")
        n = values.get("sample_count")

        # --------- 单个 dict ---------
        if isinstance(raw, dict):
            values["params"] = [raw] * n
            return values

        # --------- list[dict] ---------
        if isinstance(raw, list):
            if len(raw) == n:  # 完整列表，直接用
                return values
            if len(raw) == 1 and n > 1:  # 仅 1 条 → 复制
                values["params"] = raw * n
                return values
            raise ValueError(
                f"样本数量不一致：sample_count={n}，但 params 中有 {len(raw)} 条"
            )

        raise TypeError("params 必须是 dict 或 list[dict]")

    @field_validator("params", mode="after")
    def _check_params_list(cls, v):
        """
        此时 v 一定已经是 list[dict]
        """
        if not isinstance(v, list):
            raise TypeError("内部逻辑错误：params 应当被规范化为 list")
        if not all(isinstance(item, dict) for item in v):
            raise TypeError("params 中每个样本必须是 dict")
        return v


class WorkflowInputValidateConfig(BaseModel):
    """工作流输入验证配置"""
    wdl_path: str = Field(..., description="WDL 文件路径")
    input_json: str = Field(..., description="输入 JSON 文件路径")


# ----- Dockstore 相关配置 -----

# 定义支持的搜索字段及其说明
ALLOWED_FIELDS = {
    "full_workflow_path": "工作流完整路径",  # 用于精确定位工作流
    "description": "工作流描述",  # 搜索工作流描述
    "name": "工作流名称",  # 搜索工作流名称
    "author": "作者名称",  # 搜索作者
    "organization": "组织名称",  # 搜索组织
    "labels": "工作流标签",  # 搜索标签
    "content": "工作流源文件内容"  # 搜索源文件内容
}

# 定义查询相关的常量
ALLOWED_QUERY_TYPES = ["match_phrase", "wildcard"]  # 支持的查询类型
DEFAULT_QUERY_TYPE = "match_phrase"  # 默认查询类型


class DockstoreSearchConfig(BaseModel):
    """Dockstore 搜索配置类
    用于定义和验证搜索参数
    """
    top_n: int = Field(default=3, description="返回前 N 条结果")
    query: List[List[str]] = Field(default_factory=list, description="搜索条件列表 [field, match_type, term]")
    query_type: str = Field(default=DEFAULT_QUERY_TYPE, description="查询类型")
    sentence: bool = Field(default=False, description="是否作为句子搜索")
    output_full: bool = Field(default=False, description="是否输出完整结果")
    get_files: Optional[str] = Field(default=None, description="获取特定工作流文件的路径")

    @model_validator(mode="after")
    def validate_config(self):
        """配置验证方法
        确保提供了必要的搜索参数并验证查询类型
        """
        if not self.query and not self.get_files:
            raise ValueError("必须提供搜索条件或工作流路径")
        if self.query_type not in ALLOWED_QUERY_TYPES:
            raise ValueError(f"不支持的查询类型: {self.query_type}")
        return self


class DockstoreDownloadConfig(BaseModel):
    """Dockstore workflow download configuration"""
    url: str = Field(..., description="Workflow URL or path")
    output_path: str = Field(default=".", description="Directory path for saving workflow files")


class DockerBuildConfig(BaseModel):
    """Docker 构建配置"""
    repo_name: str = Field(..., description="仓库名称")
    tag: str = Field(..., description="版本标签")
    source_path: str = Field(..., description="Dockerfile 或压缩包路径")
    registry: str = Field(default="registry-vpc.miracle.ac.cn", description="镜像仓库地址")
    namespace_name: str = Field(default="auto-build", description="命名空间")


@mcp.tool()
async def validate_wdl(config: WDLValidateConfig) -> str:
    """验证 WDL 文件的语法正确性"""
    try:
        validate_wdl_cmd = ["womtool", "validate", config.wdl_path]
        result = subprocess.run(validate_wdl_cmd,
                                capture_output=True,
                                text=True,
                                check=True)

        return f"WDL 文件验证通过！\n{result.stdout if result.stdout else '语法正确'}"

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        return f"WDL 文件验证失败：\n{error_msg}"
    except FileNotFoundError:
        return f"找不到 WDL 文件：{config.wdl_path}"
    except Exception as e:
        return f"验证过程出现错误：{str(e)}"


@mcp.tool(description="列出当前登录环境的工作空间名称与描述")
async def list_workspace(config: ListWorkspaceConfig) -> List[Dict[str, str]]:
    """列出 Bio-OS 工作空间，仅返回 Name 与 Description 字段。

    说明：
    - 该工具使用 `bioos.list_workspaces()` 获取工作空间列表（DataFrame）。
    - 暂不支持服务端分页参数 PageNumber；`page_size` 仅在 MCP 侧进行裁剪。
    """
    ak, sk = get_credentials(config.ak, config.sk)

    bioos.login(endpoint=config.endpoint, access_key=ak, secret_key=sk)

    workspaces = bioos.list_workspaces()

    # 若为空，直接返回空列表
    if getattr(workspaces, "empty", False):
        return []
    
    try:
        df = workspaces[["Name", "Description"]]
    except Exception:
        # 兼容非 DataFrame 返回的情况
        records = getattr(workspaces, "to_dict", lambda **kwargs: workspaces)(orient="records")
        trimmed = records[: config.page_size] if (config.page_size and config.page_size > 0) else records
        return [{"Name": r.get("Name", ""), "Description": r.get("Description", "")} for r in trimmed]

    if config.page_size and config.page_size > 0:
        df = df.head(config.page_size)

    return [
        {"Name": str(row.Name), "Description": str(row.Description) if row.Description is not None else ""}
        for row in df.itertuples(index=False)
    ]

@mcp.tool()
async def import_workflow(config: WorkflowImportConfig) -> str:
    """
    该工具用于将 WDL 工作流上传到 Bio‑OS，支持上传单个文件或整个目录。
    """
    # 获取 ak、sk，用户输入优先于环境变量
    ak, sk = get_credentials(config.ak, config.sk)

    cmd = [
        "bw_import", "--ak", ak, "--sk", sk, "--endpoint", config.endpoint,
        "--workspace_name", config.workspace_name, "--workflow_name", config.workflow_name,
        "--workflow_source", config.workflow_source, "--workflow_desc",
        config.workflow_desc
    ]

    if config.main_workflow_path:
        cmd.extend(["--main_path", config.main_workflow_path])
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # 同时返回 stderr 和 stdout 的内容
    output = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)
    return "\n".join(output)




@mcp.tool(description="Bio-OS 上已导入 workflow 的 inputs.json 查询，并生成符合的输入参数模板")
async def generate_inputs_json_template_bioos(cfg: BioosWorkflowJsonConfig) -> Dict[str, Any]:
    try:
        # 获取 ak、sk，用户输入优先于环境变量
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        # 登录 Bio-OS
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        # 解析工作空间 ID
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        # 获取工作空间和工作流
        ws = bioos.Workspace(workspace_id)
        workflow = ws.workflow(cfg.workflow_name)
        # 获取输入参数模板
        inputs = workflow.get_input_template()
        return inputs
    except Exception as e:
        return {"error": str(e)}

@mcp.tool(description="根据用户给的数值生成input.json")
async def compose_input_json(cfg: WorkflowInputParams) -> str:
    filled, err = build_inputs(cfg.template_json, cfg.params)
    if err:
        return "❌ 参数错误\n" + err
    out = Path(cfg.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(filled, indent=2))
    return f"✅ 已生成 {out}（{len(filled)} 个样本）"

@mcp.tool()
async def validate_workflow_input_json(
        config: WorkflowInputValidateConfig) -> str:
    """验证工作流输入 JSON 文件"""
    try:
        validate_inputs_cmd = [
            "womtool", "validate", config.wdl_path, "--inputs",
            config.input_json
        ]
        result = subprocess.run(validate_inputs_cmd,
                                capture_output=True,
                                text=True,
                                check=True)

        return f"输入文件验证通过！\n{result.stdout if result.stdout else '格式正确，所有必需参数都已提供'}"

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        return f"输入文件验证失败：\n{error_msg}"
    except FileNotFoundError:
        return f"找不到文件：\nWDL文件：{config.wdl_path}\n输入文件：{config.input_json}"
    except Exception as e:
        return f"验证过程出现错误：{str(e)}"



def build_bw_cmd(cfg: SubmitWorkflowConfig) -> list[str]:
    ak, sk = get_credentials(cfg.ak, cfg.sk)
    cmd: list[str] = [
        "bw",
        "--ak", ak,
        "--sk", sk,
        "--endpoint", cfg.endpoint,
        "--workspace_name", cfg.workspace_name,
        "--workflow_name", cfg.workflow_name,
        "--input_json", cfg.input_json,
    ]

    if cfg.data_model_name:
        cmd += ["--data_model_name", cfg.data_model_name]
    if cfg.call_caching:
        cmd += ["--call_caching"]
    if cfg.submission_desc:
        cmd += ["--submission_desc", cfg.submission_desc]
    if cfg.force_reupload:
        cmd += ["--force_reupload"]
    if cfg.mount_tos:
        cmd += ["--mount_tos"]
    if cfg.monitor:
        cmd += ["--monitor"]
    if cfg.monitor_interval is not None:
        cmd += ["--monitor_interval", str(cfg.monitor_interval)]
    if cfg.download_results:
        cmd += ["--download_results"]
    if cfg.download_dir:
        cmd += ["--download_dir", cfg.download_dir]

    return cmd


@mcp.tool()
async def submit_workflow(config: SubmitWorkflowConfig) -> str:
    """提交并监控 Bio-OS 工作流"""
    try:
        cmd = build_bw_cmd(config)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        outs = []
        if result.stdout and result.stdout.strip():
            outs.append(result.stdout.strip())
        if result.stderr and result.stderr.strip():
            outs.append(result.stderr.strip())

        return "\n".join(outs) if outs else "工作流提交成功！可使用 `check_workflow_status` 查询执行状态。"

    except subprocess.CalledProcessError as e:
        msg = []
        if e.stdout:
            msg.append(f"标准输出：\n{e.stdout}")
        if e.stderr:
            msg.append(f"错误输出：\n{e.stderr}")
        return "工作流提交失败：\n" + ("\n".join(msg) if msg else f"退出码：{e.returncode}")
    except Exception as e:
        # 常见：凭证缺失、参数校验失败、bw 不在 PATH 等
        return f"提交过程出现错误：{e}"


@mcp.tool()
async def check_workflow_run_status(config: WorkflowStatusConfig) -> str:
    """查询工作流运行状态"""
    # 获取 ak、sk，用户输入优先于环境变量
    ak, sk = get_credentials(config.ak, config.sk)
    
    cmd = [
        "bw_status_check", "--ak", ak, "--sk", sk, "--endpoint", config.endpoint,
        "--workspace_name", config.workspace_name, "--submission_id",
        config.submission_id
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)
    return "\n".join(output)


@mcp.tool()
async def check_workflow_import_status(config: WorkflowImportStatusConfig) -> str:
    """查询工作流导入状态"""
    # 获取 ak、sk，用户输入优先于环境变量
    ak, sk = get_credentials(config.ak, config.sk)
    
    cmd = [
        "bw_import_status_check", "--ak", ak, "--sk", sk, "--endpoint", config.endpoint,
        "--workspace_name", config.workspace_name, "--workflow_id",
        config.workflow_id
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)
    return "\n".join(output)


@mcp.tool()
async def get_workflow_logs(config: WorkflowLogsConfig) -> str:
    """获取工作流执行日志"""
    # 获取 ak、sk，用户输入优先于环境变量
    ak, sk = get_credentials(config.ak, config.sk)
    
    cmd = [
        "get_submission_logs", "--ak", ak, "--sk", sk, "--endpoint", config.endpoint,
        "--workspace_name", config.workspace_name, "--submission_id",
        config.submission_id
    ]

    if config.output_dir != ".":
        cmd.extend(["--output_dir", config.output_dir])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)
    return "\n".join(output)


@mcp.tool(description="Bio-OS 删除工作流提交")
async def delete_submission(cfg: BioosDeleteSubmissionConfig) -> Dict[str, Any]:
    """删除指定工作空间中的工作流提交"""
    try:
        # 获取 ak、sk，用户输入优先于环境变量
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        result = Submission(workspace_id, cfg.submission_id).delete()
        return {"success": True, "message": f"提交 '{cfg.submission_id}' 已成功删除", "result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(description="Bio-OS 创建新工作空间")
async def create_workspace_bioos(cfg: BioosWorkspaceConfig) -> Dict[str, Any]:
    try:
        # 获取 ak、sk，用户输入优先于环境变量
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)

        result = bioos.create_workspace(
            name=cfg.workspace_name,
            description=cfg.workspace_description
        )
        workspace_id = result.get("ID")
        if not workspace_id:
            return {"error": f"工作空间创建失败或未返回ID: {result}"}

        # 绑定两种类型的集群
        cluster_id = "default"
        ws = bioos.Workspace(workspace_id)
        
        # 绑定 workflow 类型
        workflow_bind_result = ws.bind_cluster(cluster_id=cluster_id, type_="workflow")
        
        # 绑定 webapp-ies 类型
        webapp_bind_result = ws.bind_cluster(cluster_id=cluster_id, type_="webapp-ies")

        return {
            "message": f"工作空间 '{cfg.workspace_name}' 创建并绑定集群成功"
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(description="Bio-OS 导出工作空间元信息")
async def export_bioos_workspace(cfg: BioosExportWorkspace) -> Dict[str, Any]:
    try:
        # 获取 ak、sk，用户输入优先于环境变量
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        ws = bioos.Workspace(workspace_id)
        result = ws.export_workspace_v2(
            download_path=cfg.export_path,
            monitor=True,
            monitor_interval=5,
            max_retries=60
        )
        return {"message": f"Metadata exported successfully, location at {cfg.export_path}"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool(description="在指定的workspace中新建一个 IES 实例，用户可在该 IES 实例上进行分析")
async def create_iesapp(cfg: BioosCreateIesapp) -> Dict[str, Any]:
    try:
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        ws = bioos.Workspace(workspace_id)
        exists = ws.webinstanceapps.check_name_exists(cfg.ies_name)
        if exists:
            return {"error": "名称已存在，请先删除现有实例或使用不同的名称"}
    except Exception as e:
        return {"error": str(e)}
    try:
        params = {
            "name": cfg.ies_name,
            "description": cfg.ies_desc,
            "resource_size": cfg.ies_resource,
            "storage_capacity": cfg.ies_storage,
            "image": cfg.ies_image,
            "ssh_enabled": cfg.ies_ssh,
            "running_time_limit_seconds": cfg.ies_run_limit,
            "idle_timeout_seconds": cfg.ies_idle_timeout,
            "auto_start": cfg.ies_auto_start
        }
        result = ws.webinstanceapps.create_new_instance(**params)
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(description="查看指定workspace中的指定IES 实例的创建状态")
async def check_ies_status(cfg: Check_iesapp_status) -> Dict[str, Any]:
    try:
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        ws = bioos.Workspace(workspace_id)
        app = ws.webinstanceapp(cfg.ies_name)
        app.sync.__wrapped__(app)
        if app.is_running():
            ssh = app.get_ssh_connection_info()
            return {
                "state": "Running",
                "ready": True,
                "ssh": {
                    "ip": ssh["ip"],
                    "port": ssh["port"],
                    "username": ssh["username"],
                    "password": ssh["password"]
                }
            }
        else:
            return {"state": app.status_detail.get("State", ''), "ready": False}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(description="查看指定workspace中的指定IES实例的创建日志")
async def get_ies_events(cfg: GetIesEvents) -> Dict[str, Any]:
    try:
        ak, sk = get_credentials(cfg.ak, cfg.sk)
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        ws = bioos.Workspace(workspace_id)
        app = ws.webinstanceapp(cfg.ies_name)
        events = app.get_events()
        return {"events": events}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(description="上传__dashboard__.md文件到指定工作空间的S3桶")
async def upload_dashboard_file(cfg: BioosS3FileUploader) -> Dict[str, Any]:
    """
    上传__dashboard__.md文件到指定工作空间的S3桶
    """
    try:
        # 获取 ak、sk，用户输入优先于环境变量
        ak, sk = get_credentials(cfg.ak, cfg.sk)

        # 检查本地文件是否存在
        if not os.path.exists(cfg.local_file_path):
            return {"error": f"本地文件不存在: {cfg.local_file_path}"}

        # 检查文件名是否为__dashboard__.md
        filename = os.path.basename(cfg.local_file_path)
        if filename != "__dashboard__.md":
            return {"error": f"文件名必须为__dashboard__.md，当前文件名: {filename}"}

        # 登录Bio-OS
        bioos.login(endpoint=cfg.endpoint, access_key=ak, secret_key=sk)

        # 获取工作空间
        workspace_id = get_workspace_id_by_name(cfg.workspace_name)
        ws = bioos.workspace(workspace_id)

        # 上传文件到根目录
        upload_result = ws.files.upload(
            sources=[cfg.local_file_path],
            target="",  # 上传到根目录
            flatten=True
        )

        if upload_result:
            # 获取S3 URL
            s3_url = ws.files.s3_urls(["__dashboard__.md"])[0]
            expected_s3_url = f"s3://bioos-{workspace_id}/__dashboard__.md"

            return {
                "success": True,
                "message": "文件上传成功",
                "local_file": cfg.local_file_path,
                "s3_url": s3_url,
                "expected_s3_url": expected_s3_url,
                "workspace_id": workspace_id
            }
        else:
            return {"error": "文件上传失败"}

    except Exception as e:
        return {"error": str(e)}


# ===== Dockstore Tools =====
@mcp.tool()
async def search_dockstore(config: DockstoreSearchConfig) -> Dict[str, Any]:
    """
      在Dockstore中检索工作流
    """
    try:
        if not isinstance(getattr(config, "query", None), list):
            return {"error": "配置对象缺少合法 'query' 列表"}

        #构造 ES 查询
        client = DockstoreSearch()
        queries = []
        for item in config.query:
            if isinstance(item, list) and len(item) == 3:
                field, operator, term = item
                queries.append({"terms": [term], "fields": [field],
                                "operator": operator if operator in ("AND", "OR") else "AND"})
        if not queries:
            return {"error": "没有有效的查询条件"}

        try:
            results = await asyncio.wait_for(
                client.search(queries, config.sentence, config.query_type),
                timeout=60
            )
        except asyncio.TimeoutError:
            return {"error": "搜索操作超时（60 秒）"}

        hits = results.get("hits", {}).get("hits", [])
        if not hits:
            return {"error": "未找到匹配的工作流"}

        texts = [
            f"{h['_source'].get('workflowName') or h['_source'].get('name')} — "
            f"{h['_source'].get('description', '')}"
            for h in hits
        ]
        # 把用户关键词拼成一句自然查询
        user_query = " ".join(term for q in config.query for term in (q[2],))

        loop = asyncio.get_running_loop()
        try:
            reranked = await loop.run_in_executor(
                None,
                functools.partial(RERANKER.rerank,
                                  query=user_query,
                                  texts=texts,
                                  top_n=config.top_n)
            )
        except RuntimeError as e:
            # 若重排失败，降级用 ES 原排序
            print(f"[WARN] Rerank 失败，降级为 ES 排序: {e}")
            reranked = [{"index": i, "score": h["_score"]} for i, h in enumerate(hits[:config.top_n])]

        # ---------- 5. 取回 top_n hits ----------
        top_hits = [hits[item["index"]] for item in reranked]
        top_results = {"hits": {"total": {"value": len(top_hits)}, "hits": top_hits}}


        markdown = client.format_results(top_results, output_full=False)
        pattern = re.compile(r"- \[(.*?)\]\((.*?)\)")
        result_map = {match[0]: match[1] for match in pattern.findall(markdown)}

        return {"results": result_map}

    except Exception as e:
        import traceback
        return {"error": f"搜索失败: {e}\n{traceback.format_exc()}"}


@mcp.tool()
async def fetch_wdl_from_dockstore(
        config: DockstoreDownloadConfig) -> Dict[str, Any]:
    """
    从Dockstore下载工作流
    """
    # Create downloader client
    downloader = DockstoreDownloader()

    try:
        # 使用新的 URL 解析和下载方法
        success = await downloader.download_workflow_from_url(
            config.url, config.output_path)

        if not success:
            return {"error": "工作流下载失败，请检查 URL 或网络连接"}

        # 解析组织和工作流名称，以获取保存路径
        org, workflow_name = downloader.parse_workflow_url(config.url)
        if not org or not workflow_name:
            return {"error": "无法从 URL 解析组织和工作流名称"}

        save_dir = Path(config.output_path) / f"{org}_{workflow_name}"

        # 获取已下载的文件列表
        all_files = []
        for root, _, filenames in os.walk(save_dir):
            for filename in filenames:
                file_path = Path(root) / filename
                all_files.append(str(file_path.resolve()))

        # 自动检测 wdl 所在目录（不含子目录，且至少含一个 .wdl 文件）
        wdl_dirs = []
        for root, dirs, files in os.walk(save_dir):
            if dirs:
                continue  # 跳过有子目录的
            if any(file.endswith(".wdl") for file in files):
                wdl_dirs.append(Path(root).resolve())

        if not wdl_dirs:
            return {"error": "未找到包含 WDL 文件的目录"}

        # 默认取第一个符合条件的目录
        wdl_save_dir = wdl_dirs[0]

        return {
            "success": True,
            "save_directory": str(save_dir.resolve()),
            "organization": org,
            "workflow_name": workflow_name,
            "files": all_files,
            "wdl_save_directory": str(wdl_save_dir)
        }
    except Exception as e:
        import traceback
        return {"error": f"下载过程中发生错误: {str(e)}\n{traceback.format_exc()}"}


@mcp.tool()
async def get_docker_image_url(config: DockerBuildConfig) -> str:
    """获取 Docker 镜像的完整 URL"""
    return f"{config.registry}/{config.namespace_name}/{config.repo_name}:{config.tag}"


@mcp.tool()
async def build_docker_image(config: DockerBuildConfig) -> Dict[str, str]:
    """构建 Docker 镜像"""
    with open(config.source_path, "rb") as f:
        files = {"Source": f}
        data = {
            "Registry": config.registry,
            "NamespaceName": config.namespace_name,
            "RepoName": config.repo_name,
            "ToTag": config.tag
        }

        # 移除 timeout 参数
        response = requests.post("http://10.20.16.38:3001/build",
                                 files=files,
                                 data=data)

        result = response.json()
        result["ImageURL"] = await get_docker_image_url(config)
        return result


@mcp.tool()
async def check_build_status(task_id: str) -> Dict[str, Any]:
    """检查 Docker 镜像构建状态"""
    # 移除 timeout 参数
    response = requests.get(f"http://10.20.16.38:3001/build/status/{task_id}")
    return response.json()


if __name__ == "__main__":
    print("mcp running")
    try:
        load_miracle_env_from_parent_proc()
    except Exception as e:
        print(f"Warning: failed to load parent MIRACLE env: {e}")
    mcp.run()
