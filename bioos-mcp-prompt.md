# Bio-OS MCP 工作流开发指南

本指南提供了使用 Bio-OS MCP 工具进行工作流开发的完整流程和最佳实践，给出了 LLM Agent 在收到终端用户的开发指令后使用 Bio-OS MCP Server 提供的各项工具时的通用原则，如无用户刻意强调，请严格按照以下原则和流程执行。

## 1. 基本原则

### 1.1 路径使用规范
- 与 MCP 进行交互时，必须使用文件的绝对路径
- 避免使用相对路径，以防止路径解析错误
- 确保路径中包含完整的目录结构

### 1.2 交互语言规范
- 所有的用户交互必须使用中文
- 保持专业术语的准确性和一致性

### 1.3 环境变量约定
- 在需要用到和Bio-OS 交互时所需要的 ak，sk 和 workspace_name 这三个变量值时，如你没有记录，请优先执行不附加变量参数的`printenv`命令，从输出结果环境变量中获取MIRACLE_ACCESS_KEY、MIRACLE_SECRET_KEY和MIRACLE_WORKSPACE_NAME做为ak，sk 和 workspace_name使用，如环境变量中不存在某个变量值时，再向用户询问。请妥善准确记住三个变量值，这三个值在整个交互生命周期中必须保持不变，不能也不准发生变化，供 tool调用时使用。

## 2. WDL 工作流开发流程
以下章节给出了开发 WDL 流程并完成在 Bio-OS 平台上分析的完整流程。当终端用户提出要进行一次开发实践时，请按照以下章节的顺序引导用户完成从开发到上传再到提交运行的完整流程。如果用户提供了中间步骤的材料，如提供了已写好的 WDL 脚本，或者提供了 Docker image 的 URL，则可以直接使用用户提供的材料，跳过对应的步骤，但仍需要引导用户完成后续的步骤。在 WDL 中请始终使用 docker: "${docker_image}"的方式将 Task 中使用的 docker 镜像暴露到用户参数。引导用户提供或者开发每个需要的 docker 镜像。

### 2.1 WDL 工作流检索
- 用户提供一个开发任务时，请首先询问用户是否需要检索 Dockstore 中是否已有这方面的流程，如用户选择需要，则进行这一步的 WDL 工作流检索
- 使用 search_dockstore 工具配置搜索配置（DockstoreSearchConfig）查询工作流：  
  - 查询条件 -q/--query: 指定一个包含三个元素的列表 [搜索字段, 布尔操作符,搜索词]
    * 搜索字段: 在哪个字段中搜索，如 description, full_workflow_path, organization 等
    * 布尔操作符: AND（必须匹配所有词）或 OR（匹配任一词）
    * 搜索词: 需要查找的关键字或短语
    * 查询类型 --type:
  - match_phrase: 精确匹配（默认）
  - wildcard: 通配符模式（支持 * 匹配任意字符）
  - 筛选选项:
    * descriptor-type: 指定描述符类型（WDL, CWL, NFL）
    * verified-only: 仅显示已验证的工作流
    * sentence: 将搜索词作为完整句子处理
    * outputfull: 显示详细工作流信息
  - 可检索字段
    * description: 工作流描述
    * full_workflow_path: 完整工作流路径
    * name: 工作流名称
    * workflowName: 工作流显示名称
    * organization: 组织名称
    * all_authors.name: 作者姓名
    * categories.name: 工作流类别
    * input_file_formats.value: 输入文件格式
    * output_file_formats.value: 输出文件格式

  示例：
  {
    "config": {
      "query": [
        ["description", "AND", "WGS"],
        ["description", "AND", "variant calling"],
        ["organization", "OR","gzlab"]
      ],
      "query_type": "match_phrase",
      "sentence": false,
      "descriptor_type": "WDL",
      "output_full": true
    }
  }
- 默认情况下请只查询["organization", "AND", "gzlab"]下的 WDL 流程，并根据用户提供的信息构建其他的 query 元组，如"description"相关信息
- 给用户列出检索返回的列表，供用户查看并选择
- 查询结果为空时，建议用户自行开发工作流

### 2.2 WDL 工作流下载
- 如用户确认上一步的检索结果中有其需要的 WDL 流程，则在这一步中触发 WDL 工作流下载
- 使用 fetch_wdl_from_dockstore 工具下载 Dockstore 平台上的已有工作流
- 配置下载参数（DockstoreDownloadConfig）：
  - url: Dockstore 上工作流的完整URL
    - 格式: https://dockstore.miracle.ac.cn/workflows/{组织路径}/{工作流名称}
    - 示例: https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq
  - output_path: 保存工作流文件的本地目录
    - 默认为当前目录
    - 使用绝对路径以避免路径解析问题
- 下载后处理工作流：
    - 使用 `ls -R `命令 list下载到的文件或者文件夹，从中解析出 wdl 文件和 input.json文件的绝对路径
    - 使用 validate_wdl 工具验证WDL语法
    - 引导用户使用利用下载到的 wdl 文件和 input.json文件向 Bio-OS 系统平台提交先上传工作流，然后再提交工作流运行

- 常见问题排查：
  URL格式不正确：确保包含完整的组织和工作流信息
  工作流未找到：检查组织名和工作流名是否正确
  下载失败：检查网络连接和权限设置
  WDL验证失败：可能需要修改工作流以适应您的环境

### 2.3 WDL 脚本开发
- 如用户要求新开发，或者上步的检索结果中没有其需要的 WDL 流程时，进行 WDL 脚本开发
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
- 请将 WDL 的所有内容生成在一个 WDL 脚本文件中

### 2.4 WDL 脚本验证
- 使用 validate_wdl 工具验证语法
- 修复验证过程中发现的问题
- 重复验证直到通过

### 2.5 工作流上传
- 准备工作流描述信息
- 在需要用到和Bio-OS 交互时所需要的 ak，sk 和 workspace_name 这三个变量值时，如你没有记录，请优先执行不附加变量参数的`printenv`命令，从输出结果环境变量中获取MIRACLE_ACCESS_KEY、MIRACLE_SECRET_KEY和MIRACLE_WORKSPACE_NAME做为ak，sk 和 workspace_name使用，如环境变量中不存在某个变量值时，再向用户询问。请妥善准确记住三个变量值，这三个值在整个交互生命周期中必须保持不变，不能也不准发生变化，供 tool调用时使用。
- 使用 import_workflow 工具上传到 Bio-OS
- 使用 check_workflow_import_status 查询导入状态
  * 等待 WDL 语法验证完成
  * 确认导入成功
- 如果导入失败，根据错误信息修改 WDL 文件并重试

### 2.6 Docker 镜像准备
- 如用户未提供 task 要使用的 docker image 的 URL，则为每个 task 准备对应的 Dockerfile
- 遵循以下规则：
  * 优先使用 Miniconda 作为基础镜像
  * 使用 conda 安装生物信息软件
  * 创建独立的 conda 环境
- 使用 build_docker_image 构建镜像
- 使用 check_build_status 监控构建进度
- 确保所有镜像构建成功

### 2.7 输入模板生成
- 使用 generate_inputs_json_template 生成模板
- 查看生成的模板，了解需要提供的参数

### 2.8 输入文件准备
- 根据实际需求修改输入参数，优先向用户询问
- 确保所有必需参数都已填写
- 确保文件路径等参数正确
- 使用 validate_workflow_input_json 验证修改后的输入文件

### 2.9 工作流执行与监控
- 在需要用到和Bio-OS 交互时所需要的 ak，sk 和 workspace_name 这三个变量值时，如你没有记录，请优先执行不附加变量参数的`printenv`命令，从输出结果环境变量中获取MIRACLE_ACCESS_KEY、MIRACLE_SECRET_KEY和MIRACLE_WORKSPACE_NAME做为ak，sk 和 workspace_name使用，如环境变量中不存在某个变量值时，再向用户询问。请妥善准确记住三个变量值，这三个值在整个交互生命周期中必须保持不变，不能也不准发生变化，供 tool调用时使用。
- 使用 submit_workflow 提交工作流
- 使用 check_workflow_status 监控执行进度
  * 定期查询任务状态
  * 等待执行完成
- 如果执行失败：
  * 使用 get_workflow_logs 获取详细的执行日志
  * 分析日志中的错误信息
  * 根据错误信息修改相关配置
  * 重新提交直到成功或决定终止

## 3. 配置参数说明

### 3.1 WDL Runtime 配置
请提供以下 WDL runtime 配置信息：
1. Docker 镜像 (必需)
2. 内存大小 (默认: 8 GB)
3. 磁盘大小 (默认: 20 GB)
4. CPU 核数 (默认: 4)

### 3.2 工作流输入准备
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

### 3.3 工作流提交配置
请提供以下工作流提交信息：
1. Access Key (ak)
2. Secret Key (sk)
3. 工作空间名称 (workspace_name)
4. 工作流名称 (workflow_name)
5. 输入 JSON 文件路径 (input_json)
6. 是否需要监控 (monitor) [可选]
7. 监控间隔 (monitor_interval) [可选]

### 3.4 Docker 构建配置
Docker 镜像构建流程：

1. 生成 Dockerfile
   请提供以下信息：
   - 工具名称 (tool_name)
   - 工具版本 (tool_version)
   - Dockerfile 输出路径 (output_path)
   - 需要安装的 conda 包列表 (conda_packages)
   - conda 安装源 [可选，默认使用 conda-forge 和 bioconda]
   - Python 版本 [可选，默认 3.10]
   - Dockerfile 输出路径 [可选，默认 "Dockerfile"]

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

## 4. 最佳实践建议

### 4.1 WDL 开发
- 保持 task 功能单一，便于维护和复用
- 合理设置 runtime 参数，避免资源浪费
- 使用有意义的变量名和注释

### 4.2 Docker 镜像
- 遵循最小化原则，只安装必需的包
- 使用固定版本号，确保可重复性
- 做好版本管理和文档记录

### 4.3 工作流管理
- 定期检查工作流状态
- 保存重要的日志信息
- 建立问题排查和解决流程

### 4.4 安全性
- 遵循最小权限原则