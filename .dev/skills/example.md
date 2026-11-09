id: "example-skill"
type: "mcp" | "local_script" | "prompt_only"
description: "Replace with a real skill when you automate a workflow for this repo."

# Required if type is 'local_script'
local_handler:
  path: "./handler.sh"
  runtime: "bash"

# Required if type is 'mcp'
mcp_config:
  server_url: "http://mcp-proxy:8080"
  tool_name: "example_tool"

inputs:
  - name: "example_input"
    type: "string"
    description: "Describe inputs agents should provide"
