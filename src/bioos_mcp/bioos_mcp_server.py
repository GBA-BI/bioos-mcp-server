"""Bio-OS MCP 服务器

这个模块实现了一个 MCP 服务器，提供了 Bio-OS 工作流管理和 Docker 镜像构建的功能。
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple,Optional
from pydantic import BaseModel, Field
import requests
from mcp.server.fastmcp import FastMCP

from bioos_mcp.tools.dockstore_search import DockstoreSearch
from bioos_mcp.tools.fetch_wdl_from_dockstore import DockstoreDownloader

# 创建 MCP 服务器，不设置连接超时时间
mcp = FastMCP("Bio-OS-MCP-Server")

# 修改默认 runtime 配置，移除 docker 字段，因为它必须由用户指定
DEFAULT_RUNTIME = {"memory": "8 GB", "disk": "20 GB", "cpu": 4}


# ===== 数据类定义 =====
# ----- WDL 相关配置 -----
@dataclass
class WDLRuntimeConfig:
    """WDL runtime 配置"""
    docker_image: str  # docker 镜像必须指定，不提供默认值
    memory_gb: int = 8
    disk_gb: int = 20
    cpu: int = 4


@dataclass
class WDLValidateConfig:
    """WDL 文件验证配置"""
    wdl_path: str  # WDL 文件路径


# ----- 工作流相关配置 -----
@dataclass
class WorkflowConfig:
    """工作流配置"""
    ak: str
    sk: str
    workspace_name: str
    workflow_name: str
    input_json: str


@dataclass
class WorkflowImportStatusConfig:
    """工作流导入状态查询配置"""
    ak: str
    sk: str
    workspace_name: str
    workflow_id: str

class WorkflowImportConfig(BaseModel):
    """工作流导入配置"""
    ak: str = Field(..., description="Bio-OS 访问密钥")
    sk: str = Field(..., description="Bio-OS 私钥")
    workspace_name: str = Field(..., description="工作空间名称")
    workflow_name: str = Field(..., description="工作流名称")
    workflow_source: str = Field(..., description="WDL 源文件或目录的绝对路径")
    workflow_desc: str = Field(..., description="工作流描述")
    main_workflow_path: Optional[str] = Field(
        default=None,
        description="主 WDL 文件路径。当 workflow_source 是目录时必填，需指定主 WDL 文件的路径"
    )


@dataclass
class WorkflowStatusConfig:
    """工作流运行状态查询配置"""
    ak: str
    sk: str
    workspace_name: str
    submission_id: str


@dataclass
class WorkflowLogsConfig:
    """工作流日志获取配置"""
    ak: str
    sk: str
    workspace_name: str
    submission_id: str
    output_dir: str = "."  # 默认为当前目录


@dataclass
class WorkflowInputConfig:
    """工作流输入配置"""
    wdl_path: str
    output_json: str


@dataclass
class WorkflowInputParams:
    """工作流输入参数配置"""
    template_json: str  # 模板 JSON 文件路径
    output_json: str  # 输出 JSON 文件路径
    params: Dict[str, Any]  # 用户提供的参数键值对


@dataclass
class WorkflowInputValidateConfig:
    """工作流输入验证配置"""
    wdl_path: str  # WDL 文件路径
    input_json: str  # 输入 JSON 文件路径


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


@dataclass
class DockstoreSearchConfig:
    """Dockstore 搜索配置类
    用于定义和验证搜索参数
    """
    query: List[List[str]] = field(
        default_factory=list)  # 搜索条件列表 [field, match_type, term]
    query_type: str = DEFAULT_QUERY_TYPE  # 查询类型
    sentence: bool = False  # 是否作为句子搜索
    output_full: bool = False  # 是否输出完整结果
    get_files: str = None  # 获取特定工作流文件的路径

    def __post_init__(self):
        """配置验证方法
        确保提供了必要的搜索参数并验证查询类型
        """
        if not self.query and not self.get_files:
            raise ValueError("必须提供搜索条件或工作流路径")
        if self.query_type not in ALLOWED_QUERY_TYPES:
            raise ValueError(f"不支持的查询类型: {self.query_type}")


@dataclass
class DockstoreDownloadConfig:
    """Dockstore workflow download configuration"""
    url: str  # Workflow URL or path
    output_path: str = "."  # Directory path for saving workflow files


# ----- Docker 相关配置 -----
@dataclass
class DockerfileConfig:
    """Dockerfile 生成配置"""
    tool_name: str  # 工具名称
    tool_version: str  # 工具版本
    output_path: str  # Dockerfile 输出路径
    python_version: str  # Python 版本
    conda_packages: List[str]  # 需要安装的 conda 包列表
    conda_channels: List[str] = field(
        default_factory=lambda: ["conda-forge", "bioconda", "defaults"
                                 ])  # conda 安装源


@dataclass
class DockerBuildConfig:
    """Docker 构建配置"""
    repo_name: str  # 仓库名称（必需）
    tag: str  # 版本标签（必需）
    source_path: str  # Dockerfile 或压缩包路径（必需）
    registry: str = "registry-vpc.miracle.ac.cn"  # 镜像仓库地址
    namespace_name: str = "auto-build"  # 命名空间


# ===== 工作流开发工具 =====
# ----- 开发流程提示 -----
@mcp.prompt()
def wdl_development_workflow_prompt() -> str:
    """生成 WDL 工作流开发流程的完整指引"""
    return """
    WDL 工作流开发完整流程指南：

    1. WDL 脚本开发
       - 根据需求分析，确定工作流程的各个步骤
       - 为每个步骤创建对应的 task
       - 每个 task 需包含:
         * input 部分：定义输入参数
           - 对于文件类型的输入，必须使用 File 类型而不是 String
           - 禁止使用 String 类型传递文件路径，这可能导致云环境下的路径解析错误
           - 示例：
             √ File input_bam
             × String bam_path
         * command 部分：具体的执行命令
         * output 部分：定义输出结果
           - 输出文件同样必须使用 File 类型
           - 确保输出文件的路径是相对于工作目录的
         * runtime 部分：指定运行环境要求
           - docker 镜像：必须由用户显式指定，不提供默认值
             * 示例：
               runtime {
                 docker: "${docker_image}"  # 通过 workflow 的输入参数指定
               }
           - 内存大小 (默认: 8 GB)
           - 磁盘大小 (默认: 20 GB)
           - CPU 核数 (默认: 4)
       - 使用 workflow 部分组织 task 的执行顺序

    2. WDL 脚本验证
       - 使用 validate_wdl 工具验证语法
       - 修复验证过程中发现的问题
       - 重复验证直到通过

    3. 工作流上传
       - 准备工作流描述信息
       - 使用 import_workflow 工具上传到 Bio-OS
       - 使用 check_workflow_import_status 查询导入状态
         * 等待 WDL 语法验证完成
         * 确认导入成功
       - 如果导入失败，根据错误信息修改 WDL 文件并重试

    4. Docker 镜像准备
       - 为每个 task 准备对应的 Dockerfile
       - 遵循以下规则：
         * 优先使用 Miniconda 作为基础镜像
         * 使用 conda 安装生物信息软件
         * 创建独立的 conda 环境
       - 使用 build_docker_image 构建镜像
       - 使用 check_build_status 监控构建进度
       - 确保所有镜像构建成功

    5. 输入模板生成
       - 使用 generate_inputs_json_template 生成模板
       - 查看生成的模板，了解需要提供的参数

    6. 输入文件准备
       - 根据实际需求修改输入参数
       - 确保所有必需参数都已填写
       - 确保文件路径等参数正确
       - 使用 validate_workflow_input_json 验证修改后的输入文件

    7. 工作流执行与监控
       - 使用 submit_workflow 提交工作流
       - 使用 check_workflow_status 监控执行进度
         * 定期查询任务状态
         * 等待执行完成
       - 如果执行失败：
         * 使用 get_workflow_logs 获取详细的执行日志
         * 分析日志中的错误信息
         * 根据错误信息修改相关配置
         * 重新提交直到成功或决定终止

    在每个步骤中，如果遇到问题，我都会提供具体的指导和帮助。
    让我们开始第一步：请描述您的工作流需求，我来帮您开发 WDL 脚本。
    """


@mcp.prompt()
def wdl_runtime_prompt() -> str:
    """生成 WDL runtime 配置提示模板"""
    return """
    请提供以下 WDL runtime 配置信息：
    1. Docker 镜像 (必需)
    2. 内存大小 (默认: 8 GB)
    3. 磁盘大小 (默认: 20 GB)
    4. CPU 核数 (默认: 4)
    """


# ----- WDL 开发工具 -----
@mcp.tool()
async def generate_wdl_runtime(config: WDLRuntimeConfig) -> str:
    """生成标准的 WDL runtime 配置块
    
    docker 参数必须由用户显式指定，不提供默认值
    """
    if not config.docker_image:
        raise ValueError("必须指定 docker_image 参数")

    runtime_template = f"""    runtime {{
        docker: "{config.docker_image}"
        memory: "{config.memory_gb} GB"
        disk: "{config.disk_gb} GB"
        cpu: {config.cpu}
    }}"""

    return runtime_template


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


@mcp.tool()
async def import_workflow(config: WorkflowImportConfig) -> str:
    """
    该工具用于将 WDL 工作流上传到 Bio‑OS，支持上传单个文件或整个目录。
    """
    cmd = [
        "bw_import", "--ak", config.ak, "--sk", config.sk, "--workspace_name",
        config.workspace_name, "--workflow_name", config.workflow_name,
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


# ----- 工作流输入处理 -----
@mcp.prompt()
def workflow_input_prompt() -> str:
    """生成工作流输入准备提示模板"""
    return """
    工作流输入文件准备流程：

    1. 准备工作流输入
       - WDL 文件路径 (wdl_path)
       - 输出 JSON 文件路径 (output_json)
    
    2. 修改生成的输入文件
       - 填写必需参数
       - 确保文件路径正确
    
    3. 验证输入文件
       - 检查 JSON 格式
       - 验证必需参数
       - 检查文件路径有效性
    
    4. 提交工作流
       - 使用验证通过的输入文件
    """


@mcp.tool()
async def generate_inputs_json_template(config: WorkflowInputConfig) -> str:
    """生成工作流输入 JSON 模板"""
    # 使用 womtool 生成输入框架
    cmd = ["womtool", "inputs", config.wdl_path]
    try:
        result = subprocess.run(cmd,
                                capture_output=True,
                                text=True,
                                check=True)

        # 解析输入框架
        input_template = json.loads(result.stdout)

        # 生成示例输入文件
        output_path = Path(config.output_json)
        with open(output_path, 'w') as f:
            json.dump(input_template, f, indent=2)

        return f"成功生成输入模板文件：{output_path}"
    except subprocess.CalledProcessError as e:
        return f"womtool 执行失败: {e.stderr}"
    except json.JSONDecodeError as e:
        return f"JSON 解析失败: {str(e)}"
    except IOError as e:
        return f"文件写入失败: {str(e)}"


@mcp.tool()
async def compose_input_json(config: WorkflowInputParams) -> str:
    """根据模板和用户参数生成工作流输入文件"""
    try:
        # 读取模板文件
        with open(config.template_json, 'r') as f:
            template = json.load(f)

        # 验证用户提供的参数
        missing_params = []
        invalid_params = []
        for key, value in template.items():
            if "optional" in value:
                if key not in config:
                    del template[key]
                    continue

            if key not in config.params:
                missing_params.append(key)
            elif not isinstance(config.params[key], type(value)):
                invalid_params.append(
                    f"{key}: 期望类型 {type(value)}, 实际类型 {type(config.params[key])}"
                )

        if missing_params:
            return f"缺少必需参数: {', '.join(missing_params)}"
        if invalid_params:
            return "参数类型不匹配:\n" + "\n".join(invalid_params)

        # 更新模板中的参数
        final_params = template.copy()
        final_params.update(config.params)

        # 写入输出文件
        output_path = Path(config.output_json)
        with open(output_path, 'w') as f:
            json.dump(final_params, f, indent=2)

        return f"成功生成工作流输入文件：{output_path}"

    except FileNotFoundError:
        return f"找不到模板文件: {config.template_json}"
    except json.JSONDecodeError as e:
        return f"模板文件 JSON 格式错误: {str(e)}"
    except IOError as e:
        return f"文件写入失败: {str(e)}"


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


# ----- 工作流执行 -----
@mcp.prompt()
def workflow_submission_prompt() -> str:
    """生成工作流提交提示模板"""
    return """
    请提供以下工作流提交信息：
    1. Access Key (ak)
    2. Secret Key (sk)
    3. 工作空间名称 (workspace_name)
    4. 工作流名称 (workflow_name)
    5. 输入 JSON 文件路径 (input_json)
    6. 是否需要监控 (monitor) [可选]
    7. 监控间隔 (monitor_interval) [可选]
    """


@mcp.tool()
async def submit_workflow(config: WorkflowConfig) -> str:
    """提交并监控 Bio-OS 工作流"""
    try:
        cmd = [
            "bw", "--ak", config.ak, "--sk", config.sk, "--workspace_name",
            config.workspace_name, "--workflow_name", config.workflow_name,
            "--input_json", config.input_json
        ]

        result = subprocess.run(cmd,
                                capture_output=True,
                                text=True,
                                check=True)
        # 同时返回 stderr 和 stdout 的内容
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(result.stderr)

        if not output:  # 如果没有任何输出
            return "工作流提交成功！请使用 check_workflow_status 查询执行状态。"

        return "\n".join(output)
    except subprocess.CalledProcessError as e:
        error_msg = []
        if e.stdout:
            error_msg.append(f"标准输出：\n{e.stdout}")
        if e.stderr:
            error_msg.append(f"错误输出：\n{e.stderr}")
        return f"工作流提交失败：\n" + "\n".join(error_msg)
    except Exception as e:
        return f"提交过程出现错误：{str(e)}"


@mcp.tool()
async def check_workflow_run_status(config: WorkflowStatusConfig) -> str:
    """查询工作流运行状态"""
    cmd = [
        "bw_status_check", "--ak", config.ak, "--sk", config.sk,
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
async def check_workflow_import_status(
        config: WorkflowImportStatusConfig) -> str:
    """查询工作流导入状态"""
    cmd = [
        "bw_import_status_check", "--ak", config.ak, "--sk", config.sk,
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
    cmd = [
        "get_submission_logs", "--ak", config.ak, "--sk", config.sk,
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


# ===== Dockstore Tools =====
@mcp.tool()
async def search_dockstore(config: DockstoreSearchConfig) -> Dict[str, Any]:
    """
      在Dockstore中检索工作流
    """
    try:
        # 添加调试信息
        print(f"接收到的查询配置: {config}")

        # 验证输入参数
        if not hasattr(config, 'query'):
            return {"error": f"配置对象缺少 'query' 属性，请确保使用正确的参数格式"}

        if not isinstance(config.query, list):
            return {"error": f"'query' 必须是列表类型，实际类型: {type(config.query)}"}

        # 创建 Dockstore 搜索客户端
        client = DockstoreSearch()

        # 处理查询参数格式
        queries = []
        try:
            for query_item in config.query:
                # 预期格式: [field, match_type, term]
                print()
                if isinstance(query_item, list) and len(query_item) == 3:
                    field, match_type, term = query_item
                    queries.append({
                        "terms": [term],
                        "fields": [field],
                        #"operator": (str(match_type) if isinstance(match_type, str) and
                        #str(match_type).upper() in ["AND", "OR"] else "AND")
                        "operator":
                        match_type if match_type in ["AND", "OR"] else "AND"
                    })
                else:
                    print(f"跳过无效的查询项: {query_item}，预期是一个包含3个元素的列表")
        except Exception as e:
            return {"error": f"处理查询项时出错: {str(e)}"}

        if not queries:
            return {"error": "没有有效的查询条件，请检查输入格式"}

        # 添加超时处理
        import asyncio
        try:
            # 设置60秒超时
            print(
                f"开始执行搜索，参数: queries={queries}, sentence={config.sentence}, query_type={config.query_type}"
            )
            results = await asyncio.wait_for(client.search(
                queries, config.sentence, config.query_type),
                                             timeout=60)
            print("搜索完成，处理结果")
        except asyncio.TimeoutError:
            return {"error": "搜索操作超时（60秒）"}

        if not results:
            return {"error": "搜索未返回结果"}

        if isinstance(results, dict) and "error" in results:
            return results

        if "hits" not in results:
            return {"error": "未找到匹配的工作流"}

        # 格式化结果
        formatted_results = client.format_results(results)
        return formatted_results

    except Exception as e:
        import traceback
        trace_str = traceback.format_exc()
        return {"error": f"搜索失败: {str(e)}\n{trace_str}"}


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
        files = []
        for root, _, filenames in os.walk(save_dir):
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(save_dir)
                files.append(str(rel_path))

        return {
            "success": True,
            "save_directory": str(save_dir),
            "organization": org,
            "workflow_name": workflow_name,
            "files": files
        }
    except Exception as e:
        import traceback
        return {"error": f"下载过程中发生错误: {str(e)}\n{traceback.format_exc()}"}


# 在适当位置添加这个提示函数


@mcp.prompt()
def dockstore_search_prompt() -> str:
    """生成 Dockstore 搜索提示模板"""
    return """
    Dockstore 工作流搜索指南：

    请提供以下搜索参数：

    1. 查询条件列表 (query)
       - 每个查询条件为一个3元素数组: [字段, 匹配类型, 搜索词]
       - 示例: 
         [
            ["organization", "AND", "broadinstitute"],
            ["descriptorType", "AND", "WDL"]
         ]

    2. 查询类型 (query_type) [可选]
       - 默认值: "match_phrase" (精确短语匹配)
       - 可选值: "wildcard" (通配符匹配，会在搜索词前后添加*)

    3. 句子模式 (sentence) [可选]
       - 默认值: false
       - 设为 true 时将搜索词作为完整句子处理

    示例查询:
    {
        "query": [
            [ ["organization", "AND", "broadinstitute"],
            ["descriptorType", "AND", "WDL"]
        ],
        "query_type": "match_phrase",
        "sentence": true
    }
    """


# ===== Docker 镜像工具 =====
# ----- Docker 构建提示 -----
@mcp.prompt()
def docker_build_prompt() -> str:
    """生成 Docker 构建提示模板"""
    return """
    Docker 镜像构建流程：

    1. 生成 Dockerfile
       请提供以下信息：
       - 工具名称 (tool_name)
       - 工具版本 (tool_version)
       - Dockerfile 输出路径 (output_path)
       - 需要安装的 conda 包列表 (conda_packages)
       - conda 安装源 [可选，默认使用 conda-forge 和 bioconda]
       - Python 版本 [可选，默认 3.10]
       

    2. 构建镜像
       请提供以下信息：
       - 仓库名称 (repo_name)
       - 版本标签 (tag)
       - Dockerfile 或压缩包路径 (source_path)
       - 镜像仓库地址 [可选，默认 registry-vpc.miracle.ac.cn]
       - 命名空间 [可选，默认 auto-build]

    3. 监控构建状态
       - 使用返回的 TaskID 查询构建进度
       - 等待构建完成
       - 构建完成后可获取镜像完整 URL：{Registry}/{NamespaceName}/{RepoName}:{ToTag}
    """


# ----- Docker 构建工具 -----
@mcp.tool()
async def generate_dockerfile(config: DockerfileConfig) -> str:
    """生成用于构建生物信息工具的 Dockerfile
    """
    try:
        output_path = config.output_path
        # 生成 conda channels 配置命令
        channels_config = ' && \\\n    '.join(
            f'conda config --add channels {channel}'
            for channel in config.conda_channels)

        # 生成 conda 包安装列表
        packages_list = ' '.join(config.conda_packages)

        # 生成 Dockerfile 内容
        dockerfile_content = f"""FROM continuumio/miniconda3
            # 设置工作目录
            WORKDIR /app

            # 配置 Conda channels 并创建独立环境
            RUN {channels_config} && \\
                conda config --set channel_priority strict && \\
                conda create -n {config.tool_name} python={config.python_version} {packages_list} -y && \\
                conda clean -afy

            # 将环境路径添加到系统 PATH
            ENV PATH /opt/conda/envs/{config.tool_name}/bin:$PATH

            # 设置默认命令
            CMD ["/bin/bash"]
            """

        # 写入 Dockerfile
        with open(output_path, 'w') as f:
            f.write(dockerfile_content)

        return f"成功生成 Dockerfile：{output_path}"
    except IOError as e:
        return f"Dockerfile 生成失败: {str(e)}"
    except Exception as e:
        return f"生成 Dockerfile 时出错: {str(e)}"


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
    mcp.run()
