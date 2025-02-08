# Use a specific ies base image
FROM registry-vpc.miracle.ac.cn/infcprelease/ies:v1.0.0

# Download the womtool JAR file from the Broad Institute repository
RUN wget -P /usr/local/lib https://github.com/broadinstitute/cromwell/releases/download/85/womtool-85.jar 

# Update package list with a retry mechanism to ensure availability
RUN apt-get update || apt-get update

# Install essential packages: iputils-ping for network diagnostics, OpenJDK 21 for Java execution
# Clean up package cache to reduce image size
RUN apt-get install -y iputils-ping openjdk-21-jdk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install the pybioos Python package using conda's pip
RUN /opt/conda/bin/pip install pybioos

# Install the uv package, possibly for running a web server or API
RUN /opt/conda/bin/pip install uv
    
# Install the Claude Dev VSCode extension for code-server in a specified directory
RUN mkdir -p /opt/code-server/extensions && \
    /app/code-server/bin/code-server --extensions-dir /opt/code-server/extensions --install-extension saoudrizwan.claude-dev

# Clone the bioos-mcp-server repository into the specified directory
RUN git clone https://github.com/GBA-BI/bioos-mcp-server.git /opt/lib/bioos-mcp-server

# Copy and set appropriate permissions for the script that initializes code-server
COPY --chmod=755 ./images/ies/etc/s6-overlay/s6-rc.d/init-code-server/run /etc/s6-overlay/s6-rc.d/init-code-server/run

# Create configuration directory and write settings for the VSCode extension
RUN mkdir -p /home/ies/.local/share/code-server/User/globalStorage/saoudrizwan.claude-dev/settings && \
    cat <<EOF > /home/ies/.local/share/code-server/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
{
  "mcpServers": {
    "bioos": {
      "command": "uv",
      "args": [
        "--directory",
        "/opt/lib/bioos-mcp-server/src/bioos_mcp",
        "run",
        "/opt/lib/bioos-mcp-server/src/bioos_mcp/bioos_mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "/opt/lib/bioos-mcp-server/src"
      }
    }
  }
}
EOF
