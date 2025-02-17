# Bio-OS MCP Server

A Model Context Protocol (MCP) based tool and prompt server for Bio-OS that provides workflow management and Docker image building capabilities.


## Usage


Whichever way you use it, we highly recommend copying the contents of `bioos-mcp-prompt.md` into your CLINE Custom Instructions for the best experience.

### Miracle Cloud IES Usage （Using MCP through Miracle Cloud Interactive Analysis Instance）
When using Miracle Cloud, you can directly use the custom URL [registry-vpc.miracle.ac.cn/infcprelease/iespro:250217](registry-vpc.miracle.ac.cn/infcprelease/iespro:250217) in the interactive analysis instance. The image has already integrated the MCP scripts and related dependencies. You can access it using either the web-based Code Server or VSCode's SSH Remote locally. You only need to configure your own  LLM model access credentials to start using it. If you want to use GitHub Copilot capabilities inherited by VSCode, ensure the client-side Copilot is properly configured firstly.

<font color="gray"> If you're using the Inside version or another VSCode-based forked IDE, the extension path may vary. You'll need to manually install the CLINE plugin and complete the MCP configuration. </font>

### Local Installation（Using MCP through local VSCode and Cline plugin）
#### Pre-requisite  
Before using this setup, ensure that the following dependencies are installed:

1. VSCode IDE  
Download and install from: [VSCode Official Site](https://code.visualstudio.com/)

2. Cline Plugin (Required for interacting with Miracle Cloud via VSCode)  
Install using the following command:  
    ```sh
    code --install-extension saoudrizwan.claude-dev
    ```
    Users need to configure their own LLM model access credentials.

3. Pybioos (Bio-OS Python SDK for interacting with Bio-OS services)  
Install using pip:  
    ```sh
    pip install pybioos
    ```

4. uv(a fast, standalone Python package manager)
Install using pip:  
    ```sh
    pip install uv
    ```


5. JDK (Java Development Kit, required for certain backend services)  
Recommended version: OpenJDK 11 or later  

- Install on Ubuntu/Debian:  
  ```sh
  sudo apt update && sudo apt install openjdk-11-jdk
  ```

- Install on macOS (via Homebrew):  
    ```sh
    brew install openjdk@11
    ```

- Install on Windows:  Download from: [Adoptium OpenJDK](https://adoptium.net/)

6. Womtool
    ```sh
    wget https://github.com/broadinstitute/cromwell/releases/download/85/womtool-85.jar 
    ```
    You can install womtool using conda, which will automatically generate a womtool script to build the scheduling logic for the JAR file, or you can add alias or doskey information manually.
    
    For Linux/macOS (using alias):
    ```sh
    alias womtool='java -jar womtool-85.jar'
    ```
    For Windows (using doskey):
    ```
    doskey womtool=java -jar womtool-85.jar
    ```


#### Obtaining MCP

```sh
git clone https://github.com/GBA-BI/bioos-mcp-server.git
```

Configure the script path in CLINE's MCP settings like this：
```json
{
  "mcpServers": {
    "bioos": {
      "command": "path/to/uv",
      "args": [
        "--directory",
        "path/to/bioos-mcp-server",
        "run",
        "path/to/bioos-mcp-server/src/bioos_mcp/bioos_mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/bioos-mcp-server/src"
      }
    }
  }
} 
```

## Features

### 1. Workflow Management
- Submit and monitor workflows
- Upload WDL workflows
- Validate WDL scripts
- Generate input file templates

### 2. Docker Image Management
- Build Docker images
- Check build status



## API Reference

### Tools

1. `submit_workflow`
   - Function: Submit Bio-OS workflow
   - Parameters:
     - ak: Access Key
     - sk: Secret Key
     - workspace_name: Workspace name
     - workflow_name: Workflow name
     - input_json: Input JSON file path


2. `import_workflow`
   - Function: Upload WDL workflow to Bio-OS system
   - Parameters:
     - ak: Access Key
     - sk: Secret Key
     - workspace_name: Workspace name
     - workflow_name: Workflow name
     - workflow_source: WDL file path
     - workflow_desc: Workflow description

3. `validate_wdl`
   - Function: Validate WDL workflow script
   - Parameters:
     - wdl_path: WDL file path

4. `generate_inputs`
   - Function: Generate WDL input file template
   - Parameters:
     - wdl_path: WDL file path

5. `build_docker_image`
   - Function: Build Docker image
   - Parameters:
     - registry: Image registry address
     - namespace_name: Namespace
     - repo_name: Repository name
     - tag: Version tag
     - source_path: Dockerfile or archive path

6. `check_build_status`
   - Function: Check Docker image build status
   - Parameters:
     - task_id: Build task ID

### Prompts (Not supported in Cline yet)

1. `wdl_development_workflow_prompt`
   - Function: Generate complete guidance for WDL workflow development
   - Content:
     - WDL script development steps
     - Task structure guidelines
     - Runtime configuration requirements
     - Docker image preparation guide

2. `wdl_runtime_prompt`
   - Function: Generate WDL runtime configuration template
   - Content:
     - Required docker image configuration
     - Memory settings (default: 8 GB)
     - Disk settings (default: 20 GB)
     - CPU settings (default: 4)

3. `workflow_input_prompt`
   - Function: Generate workflow input preparation guide
   - Content:
     - Input file preparation steps
     - Parameter validation guidelines
     - File path requirements

4. `workflow_submission_prompt`
   - Function: Generate workflow submission template
   - Content:
     - Required credentials (ak/sk)
     - Workspace configuration
     - Input file requirements

5. `docker_build_prompt`
   - Function: Generate Docker build process guide
   - Content:
     - Dockerfile generation steps
     - Build configuration requirements
     - Image registry settings
     - Build status monitoring guide

Note: Prompts are currently not supported in Cline environment. These prompts are only available when using the MCP server directly or through Claude Desktop.


## Contributing

Issues and Pull Requests are welcome.

## License

MIT License