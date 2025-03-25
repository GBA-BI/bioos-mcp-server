# Bio-OS MCP 工作流开发指南

## 1. 基本原则

### 1.1 路径使用规范
- 与 MCP 进行交互时，必须使用文件的绝对路径
- 避免使用相对路径，以防止路径解析错误
- 确保路径中包含完整的目录结构

### 1.2 交互语言规范
- 所有的用户交互必须使用中文
- 保持专业术语的准确性和一致性

本指南提供了使用 Bio-OS MCP 工具进行工作流开发的完整流程和最佳实践。

## 1.3.1 WDL 工作流查询
- 使用 Dockstore 搜索配置（DockstoreSearchConfig）查询工作流
  * terms: 搜索词列表，如 ["WGS", "variant calling"]
  * fields: 搜索字段列表，如 ["description", "full_workflow_path"]
  * operator: 搜索逻辑，"AND"（所有词都匹配）或"OR"（任一词匹配）
  * query_type: 匹配方式，"match_phrase"（精确匹配）或"wildcard"（模糊匹配）
  * sentence: 是否将搜索词作为完整句子处理（布尔值）
  示例：
  {"config":{
            query=[
                ["description", "AND", "SNP CNV workflow WGS variant calling"],
                ["description", "OR", "tumor normal paired somatic variant"],
                ["descriptor-type", "AND", "WDL"]
            ],
            query_type="match_phrase",
            sentence=True,
            output_full=True
    }
  }
- 使用 search_dockstore 工具执行查询
- 分析搜索结果，选择合适的工作流
- 查询结果为空时，建议用户自行开发工作流

## 1.3.2 WDL 工作流下载
- 使用 Dockstore 下载配置（DockstoreDownloadConfig）下载选定的工作流
  * full_workflow_path: 完整的工作流路径，如 "github.com/broadinstitute/wdl-workflows/gatk"
  * output_path: 保存工作流文件的本地目录
- 使用 fetch_wdl_from_dockstore 工具下载工作流文件
- 下载后自动验证 WDL 语法
- 如需修改，确保遵循以下原则：
  * 保留原有文件结构
  * 记录所有修改，便于追溯
  * 更新文档以反映修改内容

## 2. WDL 工作流开发流程

### 2.1 WDL 脚本开发
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

### 2.2 WDL 脚本验证
- 使用 validate_wdl 工具验证语法
- 修复验证过程中发现的问题
- 重复验证直到通过

### 2.3 工作流上传
- 准备工作流描述信息
- 使用 import_workflow 工具上传到 Bio-OS
- 使用 check_workflow_import_status 查询导入状态
  * 等待 WDL 语法验证完成
  * 确认导入成功
- 如果导入失败，根据错误信息修改 WDL 文件并重试

### 2.4 Docker 镜像准备
- 为每个 task 准备对应的 Dockerfile
- 遵循以下规则：
  * 优先使用 Miniconda 作为基础镜像
  * 使用 conda 安装生物信息软件
  * 创建独立的 conda 环境
- 使用 build_docker_image 构建镜像
- 使用 check_build_status 监控构建进度
- 确保所有镜像构建成功

### 2.5 输入模板生成
- 使用 generate_inputs_json_template 生成模板
- 查看生成的模板，了解需要提供的参数

### 2.6 输入文件准备
- 根据实际需求修改输入参数，优先向用户询问
- 确保所有必需参数都已填写
- 确保文件路径等参数正确
- 使用 validate_workflow_input_json 验证修改后的输入文件

### 2.7 工作流执行与监控
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
- 妥善保管 AK/SK
- 定期更新密钥
- 遵循最小权限原则