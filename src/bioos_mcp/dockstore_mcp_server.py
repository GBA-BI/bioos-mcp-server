"""Dockstore MCP 服务器
这个服务器提供了三个主要功能：
1. 搜索 Dockstore 工作流
2. 生成搜索结果摘要
3. 下载工作流文件
"""

# 导入所需模块
import json  # 用于 JSON 数据处理
import os    # 用于文件和目录操作
from dataclasses import dataclass, field  # 用于定义数据类
from typing import List, Tuple, Dict, Any  # 类型注解
from mcp.server import FastMCP  # MCP 服务器框架
# 导入自定义工具类
from bioos_mcp.tools.dockstore_search import DockstoreSearch  # 搜索工具
#from bioos_mcp.tools.workflowfile_download import process_workflow  # 文件下载工具
from bioos_mcp.tools.output_demo import WorkflowFormatter  # 结果格式化工具
from bioos_mcp.tools.wf_select import WorkflowSelector  # 工作流选择器

# 创建 MCP 服务器实例
mcp = FastMCP("Dockstore-MCP-Server")

# 定义支持的搜索字段及其说明
ALLOWED_FIELDS = {
    "full_workflow_path": "工作流完整路径",  # 用于精确定位工作流
    "description": "工作流描述",            # 搜索工作流描述
    "name": "工作流名称",                  # 搜索工作流名称
    "author": "作者名称",                  # 搜索作者
    "organization": "组织名称",            # 搜索组织
    "labels": "工作流标签",                # 搜索标签
    "content": "工作流源文件内容"          # 搜索源文件内容
}

# 定义查询相关的常量
ALLOWED_QUERY_TYPES = ["match_phrase", "wildcard"]  # 支持的查询类型
DEFAULT_QUERY_TYPE = "match_phrase"                 # 默认查询类型
DEFAULT_RESULTS_FILE = "dockstore_results.json"     # 默认结果文件名
DEFAULT_SUMMARY_FILE = "formatted_workflows.md"      # 默认摘要文件名

@dataclass
class DockstoreSearchConfig:
    """Dockstore 搜索配置类
    用于定义和验证搜索参数
    """
    query: List[Tuple[str, str, str]] = field(default_factory=list)  # 搜索条件列表
    query_type: str = DEFAULT_QUERY_TYPE  # 查询类型
    sentence: bool = False    # 是否作为句子搜索
    output_full: bool = False # 是否输出完整结果
    get_files: str = None    # 获取特定工作流文件的路径

    def __post_init__(self):
        """配置验证方法
        确保提供了必要的搜索参数并验证查询类型
        """
        if not self.query and not self.get_files:
            raise ValueError("必须提供搜索条件或工作流路径")
        if self.query_type not in ALLOWED_QUERY_TYPES:
            raise ValueError(f"不支持的查询类型: {self.query_type}")

@dataclass
class DockstoreWorkflowDownloadConfig:
    """工作流下载配置类
    定义下载工作流所需的参数
    """
    json_file: str        # 包含工作流信息的 JSON 文件路径
    workflow_path: str    # 要下载的工作流路径

@dataclass
class ResultSummaryConfig:
    """结果摘要配置类
    用于指定结果文件的路径参数

    Attributes:
        path (str, optional): 结果文件的路径
            - 如果提供，直接使用此路径读取结果文件
            - 如果为None，则自动搜索最新的结果文件
            - 默认值: None
    
    Examples:
        >>> config = ResultSummaryConfig()  # 使用自动搜索
        >>> config = ResultSummaryConfig(path="path/to/results.json")  # 指定文件路径
    """
    path: str = None  # 结果文件路径，默认为None表示自动搜索

    def __post_init__(self):
        """初始化后的验证
        如果提供了路径，验证路径的有效性
        """
        if self.path and not isinstance(self.path, str):
            raise ValueError("路径必须是字符串类型")
        if self.path and not os.path.isfile(self.path):
            raise FileNotFoundError(f"找不到指定的文件: {self.path}")

# 定义统一的文件路径管理
class FileManager:
    """文件路径管理类"""
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.getcwd()
        
    def get_results_path(self) -> str:
        """获取结果文件路径"""
        return os.path.join(self.base_dir, DEFAULT_RESULTS_FILE)
        
    def get_summary_path(self) -> str:
        """获取摘要文件路径"""
        return os.path.join(self.base_dir, DEFAULT_SUMMARY_FILE)

class WorkspaceManager:
    """工作空间管理"""
    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir or os.getcwd()
        
    def create_workspace(self, tool_name: str) -> str:
        """创建工具专用工作目录"""
        workspace = os.path.join(self.root_dir, tool_name)
        os.makedirs(workspace, exist_ok=True)
        return workspace
        
    def cleanup(self):
        """清理临时文件"""
        pass

# === MCP 工具函数定义 ===

@mcp.tool()
async def dockstore_search(config: DockstoreSearchConfig) -> str:
    """搜索 Dockstore 工作流的入口函数
    根据配置决定是搜索工作流还是获取特定工作流文件
    """
    try:
        if config.get_files:
            return await handle_get_files(config.get_files)
        else:
            return await handle_search(config)
    except Exception as e:
        return f"搜索出错: {str(e)}"

async def handle_search(config: DockstoreSearchConfig) -> str:
    """处理工作流搜索请求
    执行实际的搜索操作并保存结果
    """
    client = DockstoreSearch()
    
    queries = [
        {
            "terms": [term],
            "fields": [field],
            "operator": operator.upper(),
            "query_type": config.query_type
        }
        for term, field, operator in config.query
    ]
    
    results = await client.search(queries, is_sentence=config.sentence)
    if not results:
        return "搜索未返回结果"
    
    formatted_results = client.format_results(results, full_output=config.output_full)
    
    with open("dockstore_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    return formatted_results

async def handle_get_files(workflow_path: str) -> str:
    """处理获取工作流文件请求"""
    client = DockstoreSearch()
    
    files = await client.get_workflow_files(workflow_path)
    if not files:
        return f"无法获取工作流文件: {workflow_path}"
        
    # 创建输出目录
    output_dir = os.path.join(os.getcwd(), "workflow_files")
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成输出文件路径
    output_file = os.path.join(
        output_dir, 
        f"workflow_files_{workflow_path.replace('/', '_')}.json"
    )
    
    # 保存文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
        
    return f"工作流文件已保存到: {output_file}"

@mcp.tool()
async def dockstore_workflow_download(config: DockstoreWorkflowDownloadConfig) -> str:
    """下载Dockstore工作流文件"""
    try:
        selector = WorkflowSelector(config.workflow_path, download=True)
        
        with open(config.json_file, 'r', encoding='utf-8') as file:
            search_results = json.load(file)

        workflow = selector.find_workflow(search_results)
        if not workflow:
            return f"未找到工作流: {config.workflow_path}"
            
        wdl_files = selector.extract_wdl_files(workflow)
        if not wdl_files:
            return "未找到WDL文件"
            
        wdl_dir = selector.save_wdl_files(wdl_files)
        if not wdl_dir:
            return "保存WDL文件失败"
            
        return f"已下载 {len(wdl_files)} 个WDL文件到: {wdl_dir}"

    except Exception as e:
        return f"下载出错: {str(e)}"

@mcp.tool()
async def result_summary(config: ResultSummaryConfig = None) -> str:
    """生成检索结果摘要的工具函数"""
    try:
        # 确定结果文件路径
        results_file = config.path if config and config.path else None
        
        if not results_file:
            # 使用 find_latest_results_file 函数搜索最新结果文件
            results_file = find_latest_results_file(os.getcwd())
            
            if not results_file:
                return "错误：未找到任何 dockstore_results.json 文件"
                
            print(f"使用最新的结果文件: {results_file}")
        
        # 读取检索结果
        with open(results_file, "r", encoding="utf-8") as f:
            search_results = json.load(f)
        
        formatter = WorkflowFormatter()
        summary = formatter.format_search_results(search_results)
        
        # 保存格式化结果到同一目录
        summary_path = os.path.join(os.path.dirname(results_file), DEFAULT_SUMMARY_FILE)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
            
        return summary
        
    except FileNotFoundError:
        return f"错误：找不到检索结果文件: {results_file}"
    except Exception as e:
        return f"生成摘要时出错: {str(e)}"

def find_latest_results_file(start_dir: str) -> str:
    """查找最新的结果文件
    
    递归搜索目录树，找出最新的 dockstore_results.json 文件
    使用文件修改时间作为判断依据，返回绝对路径
    
    Args:
        start_dir: 开始搜索的目录路径
        
    Returns:
        str: 找到的文件的绝对路径，未找到则返回 None
    """
    latest_file = None
    latest_time = 0
    
    # 确保使用绝对路径
    abs_start_dir = os.path.abspath(start_dir)
    
    for root, _, files in os.walk(abs_start_dir):
        if DEFAULT_RESULTS_FILE in files:
            file_path = os.path.abspath(os.path.join(root, DEFAULT_RESULTS_FILE))
            file_time = os.path.getmtime(file_path)
            
            if file_time > latest_time:
                latest_time = file_time
                latest_file = file_path
                
    return latest_file

# === 提示模板定义 ===
# 这些函数生成用户界面提示信息，帮助用户正确使用工具

@mcp.prompt()
def dockstore_search_prompt() -> str:
    """生成搜索提示模板
    提供搜索参数说明和使用示例
    """
    field_descriptions = "\n".join([f"       - {field}: {desc}" 
                                  for field, desc in ALLOWED_FIELDS.items()])
    
    return f"""
    请提供 Dockstore 工作流搜索配置。支持多字段复杂搜索和文件获取。

    1. 搜索参数说明:
       A. query: 搜索条件列表，每个条件包含三个元素
          ["搜索词", "搜索字段", "布尔操作符"]
          示例: ["gatk", "description", "AND"]
          
       B. 可用搜索字段:
{field_descriptions}

       C. 布尔操作符:
          - AND: 与其他条件同时满足
          - OR: 满足任一条件

    2. 查询类型 (query_type):
       - match_phrase: 精确短语匹配（默认）
       - wildcard: 通配符匹配（支持*号）

    3. 其他选项:
       - sentence: 是否作为句子搜索（允许词序灵活匹配）
       - output_full: 是否显示完整结果
       - get_files: 指定工作流路径以获取文件

    配置示例:
    1. 基础搜索:
    {{
        "query": [
            ["gatk", "description", "AND"]
        ],
        "query_type": "match_phrase"
    }}

    2. 多条件搜索:
    {{
        "query": [
            ["broadinstitute", "organization", "AND"],
            ["variant", "description", "AND"],
            ["calling", "description", "AND"]
        ],
        "query_type": "match_phrase",
        "sentence": true
    }}

    3. 获取特定工作流文件:
    {{
        "get_files": "github.com/broadinstitute/gatk-workflows/gatk4-cnn-variant-filter"
    }}

    4. 完整功能搜索:
    {{
        "query": [
            ["broad", "organization", "AND"],
            ["gatk", "description", "AND"],
            ["cnv", "content", "OR"]
        ],
        "query_type": "match_phrase",
        "sentence": true,
        "output_full": true
    }}
    """

@mcp.prompt()
def dockstore_workflow_download_prompt() -> str:
    """生成下载提示模板
    说明如何配置工作流下载参数
    """
    return """
    请提供 Dockstore 工作流文件下载配置信息：

    1. JSON文件路径 (json_file):
       - 包含工作流信息的JSON文件的完整路径
       - 通常是使用 dockstore_search 工具生成的结果文件
       - 文件必须包含完整的工作流数据结构
       - 示例: "dockstore_results.json"

    2. 工作流路径 (workflow_path):
       - 要下载的工作流的完整路径
       - 可以从检索结果摘要中获取
       - 示例: "github.com/broadinstitute/gatk-workflows/cnv-workflow"

    配置示例:
    {
        "json_file": "dockstore_results.json",
        "workflow_path": "github.com/broadinstitute/gatk-workflows/cnv-workflow"
    }

    说明:
    - 程序会自动创建以工作流名称命名的目录
    - 所有WDL文件会保存在该目录下
    - 只下载包含实际内容的WDL文件
    """

@mcp.prompt()
def result_summary_prompt() -> str:
    """生成结果摘要提示模板"""
    return """
    生成 Dockstore 搜索结果的摘要报告的配置信息：

    1. JSON文件路径 (json_file):
       - 包含工作流信息的JSON文件的完整路径
       - 通常是使用 dockstore_search 工具生成的结果文件
       - 文件必须包含完整的工作流数据结构
       - 示例: "dockstore_results.json"
        通过 path 参数指定特定的结果文件路径
        示例：
        {
            "path": "./src/bioos_mcp/dockstore_results.json"
        }

        输出：
        - 在结果文件同目录下生成 formatted_workflows.md
        - 返回生成的摘要内容


    2. 自动模式（推荐）：
       不提供任何参数，工具将自动查找最新的搜索结果文件
       示例：
       {
       }
  
    """

# 启动服务器
if __name__ == "__main__":
    mcp.run()