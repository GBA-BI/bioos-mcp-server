# Bio-OS MCP Workflow Development Guide

This guide provides a comprehensive workflow development process and best practices using Bio-OS MCP tools. It outlines general principles for LLM Agents when using Bio-OS MCP Server tools in response to end-user development requests. Unless explicitly specified by users, please follow these principles and procedures strictly.

## 1. Core Principles

### 1.1 Path Usage Specification
- Always use absolute file paths when interacting with MCP
- Avoid relative paths to prevent path resolution errors
- Ensure paths include complete directory structures

### 1.2 Interaction Language Specification
- All user interactions must be conducted in Chinese
- Maintain accuracy and consistency of technical terminology

## 2. WDL Workflow Development Process

The following sections describe the complete workflow development process for WDL pipelines and analysis on the Bio-OS platform. When end-users request development assistance, follow these sections sequentially to guide users through the complete process from development to workflow upload, input file preparation, and submission. If users provide intermediate materials (e.g., pre-written WDL scripts or Docker image URLs), use the provided materials directly and skip corresponding steps, but still guide users through subsequent steps. In WDL scripts, always use `docker: "${docker_image}"` to expose Docker images as user parameters. Guide users to provide or develop required Docker images.

### 2.1 WDL Workflow Retrieval
- When users request a development task, first inquire if they need to search Dockstore for existing workflows
- If users choose to search, proceed with WDL workflow retrieval
- Use the `search_dockstore` tool with DockstoreSearchConfig configuration:
  - Query condition `-q/--query`: Specify a list containing three elements `[search_field, boolean_operator, search_term]`
    * Search fields: `description`, `full_workflow_path`, `organization`, `name`, `workflowName`, `all_authors.name`, `categories.name`, `input_file_formats.value`, `output_file_formats.value`
    * Boolean operators: `AND` (must match all terms) or `OR` (match any term)
    * Search terms: Keywords or phrases to search for
  - Query type `--type`:
    * `match_phrase`: Exact match (default)
    * `wildcard`: Wildcard pattern (supports * for any character)
  - Filter options:
    * `descriptor-type`: Specify descriptor type (WDL, CWL, NFL)
    * `verified-only`: Show only verified workflows
    * `sentence`: Process search terms as complete sentences
    * `outputfull`: Display detailed workflow information

Example configuration:
```json
{
  "config": {
    "query": [
      ["description", "AND", "WGS"],
      ["description", "AND", "variant calling"],
      ["organization", "OR", "gzlab"]
    ],
    "query_type": "match_phrase",
    "sentence": false,
    "descriptor_type": "WDL",
    "output_full": true
  }
}
```

- By default, query WDL workflows under `["organization", "AND", "gzlab"]` and build additional query tuples based on user-provided information (e.g., "description" details)
- Present search results to users for review and selection
- If no results are found, recommend users to develop workflows independently

### 2.2 WDL Workflow Download
- If users confirm that suitable WDL workflows exist in search results, trigger workflow download
- Use `fetch_wdl_from_dockstore` tool to download existing workflows from Dockstore
- Configure download parameters (DockstoreDownloadConfig):
  - `url`: Complete URL of the workflow on Dockstore
    - Format: `https://dockstore.miracle.ac.cn/workflows/{organization_path}/{workflow_name}`
    - Example: `https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq`
  - `output_path`: Local directory to save workflow files (default: current directory, use absolute paths)

Post-download processing:
- Use `ls -R` command to list downloaded files/directories and parse absolute paths of WDL and input.json files
- Use `validate_wdl` tool to verify WDL syntax
- Guide users to use downloaded WDL and input.json files: first upload WDL workflow to Bio-OS platform, then use input.json to submit workflow execution

Troubleshooting common issues:
- Incorrect URL format: Ensure complete organization and workflow information
- Workflow not found: Verify organization and workflow names
- Download failure: Check network connection and permissions
- WDL validation failure: Workflow modifications may be needed for your environment

### 2.3 WDL Script Development
- If users request new development or no suitable workflows are found in search results, proceed with WDL script development
- Analyze requirements and define workflow steps
- Create corresponding tasks for each step
- Each task must include:

**Input section:**
- For file inputs, always use `File` type instead of `String`
- Never use `String` type for file paths to avoid path resolution errors in cloud environments
- Example:
  - ✓ `File input_bam`
  - ✗ `String bam_path`

**Command section:** Execution commands

**Output section:**
- Output files must use `File` type
- Ensure output file paths are relative to working directory

**Runtime section:**
- Docker image: Must be explicitly specified by users, no default values
wdl

runtime {

docker: "${docker_image}"  # Specified via workflow input parameters

}

- Memory size (default: 8 GB)
- Disk size (default: 20 GB) 
- CPU cores (default: 4)

- Use workflow section to organize task execution order
- Generate all WDL content in a single WDL script file

### 2.4 WDL Script Validation
- Before using validation tools, ask users if they require WDL syntax validation
- If users decline validation, proceed directly to workflow upload
- Use `validate_wdl` tool to verify syntax
- Fix issues identified during validation
- Repeat validation until successful

### 2.5 Workflow Upload
- Prepare workflow description information
- Use `import_workflow` tool to upload to Bio-OS:
- `workflow_source`: Absolute path to WDL source file or directory (directory containing WDL files)
- `main_workflow_path`: Absolute path to main WDL file
- If import fails:
- Verify AK/SK credentials are correct
- If credentials are correct, try different `workflow_name`
- Use `check_workflow_import_status` tool to monitor import status
- Wait for WDL syntax validation completion
- Confirm successful import
- If import fails, modify WDL file based on error messages and retry

### 2.6 Docker Image Preparation
- If users don't provide Docker image URLs for tasks, prepare corresponding Dockerfiles for each task
- Follow these rules:
- Prefer Miniconda as base image
- Use conda to install bioinformatics software
- Create isolated conda environments
- Use `build_docker_image` tool to build images
- Use `check_build_status` tool to monitor build progress
- Ensure all images build successfully

### 2.7 Input File Preparation
- Input file preparation must follow this two-step process:
1. Generate standard workflow input template using `generate_inputs_json_template_bioos` tool and save locally
2. Call `compose_input_json` tool to generate final input template
- **Do not skip the template saving step**, even if parameters are available

Process details:
- Use `generate_inputs_json_template_bioos` to generate standard workflow input template
- Save the template (tool return value) locally as `template-{random_number}.json`
- Remember the absolute path of this template file
- After generating the template, call `compose_input_json` tool to create `input-{random_number}.json` based on user-provided sample count and parameters
- Save this input file locally and remember its absolute path
- **Note:** Input template file and input file are two distinct JSON files

### 2.8 Workflow Execution and Monitoring
- Use `submit_workflow` tool to submit workflows
- Use `check_workflow_status` tool to monitor execution progress
- Periodically query task status
- Wait for execution completion
- If execution fails:
- Use `get_workflow_logs` tool to obtain detailed execution logs
- Analyze error messages in logs
- Modify configurations based on error information
- Resubmit until successful or termination decision

## 3. Configuration Parameter Specifications

### 3.1 WDL Runtime Configuration
Provide the following WDL runtime configuration information:
1. Docker image (required)
2. Memory size (default: 8 GB)
3. Disk size (default: 20 GB)
4. CPU cores (default: 4)

### 3.2 Workflow Input Preparation
Workflow input file preparation process:
1. Prepare workflow inputs
 - WDL file path (`wdl_path`)
 - Output JSON file path (`output_json`)
2. Modify generated input files
 - Fill in required parameters
 - Ensure file paths are correct
3. Validate input files
 - Check JSON format
 - Verify required parameters
 - Validate file path effectiveness
4. Submit workflow
 - Use validated input files

### 3.3 Workflow Submission Configuration
Provide the following workflow submission information:
1. Access Key (`ak`)
2. Secret Key (`sk`)
3. Workspace name (`workspace_name`)
4. Workflow name (`workflow_name`)
5. Input JSON file path (`input_json`)
6. Monitoring requirement (`monitor`) [optional]
7. Monitoring interval (`monitor_interval`) [optional]

### 3.4 Docker Build Configuration
Docker image building process:

1. Generate Dockerfile
 Provide the following information:
 - Tool name (`tool_name`)
 - Tool version (`tool_version`)
 - Dockerfile output path (`output_path`)
 - Conda package requirements (`conda_packages`)
 - Conda installation sources [optional, default: conda-forge and bioconda]
 - Python version [optional, default: 3.10]
 - Dockerfile output path [optional, default: "Dockerfile"]

2. Build image
 Provide the following information:
 - Repository name (`repo_name`)
 - Version tag (`tag`)
 - Dockerfile or archive path (`source_path`)
 - Image registry URL [optional, default: registry-vpc.miracle.ac.cn]
 - Namespace [optional, default: auto-build]

3. Monitor build status
 - Use returned TaskID to query build progress
 - Wait for build completion
 - After successful build, obtain complete image URL: `{Registry}/{NamespaceName}/{RepoName}:{ToTag}`

## 4. Best Practices Recommendations

### 4.1 WDL Development
- Maintain single-responsibility tasks for easier maintenance and reuse
- Set appropriate runtime parameters to avoid resource waste
- Use meaningful variable names and comments

### 4.2 Docker Images
- Follow minimization principle, install only essential packages
- Use fixed version numbers to ensure reproducibility
- Implement version management and documentation

### 4.3 Workflow Management
- Regularly check workflow status
- Preserve important log information
- Establish troubleshooting and resolution procedures

### 4.4 Security
- Follow principle of least privilege