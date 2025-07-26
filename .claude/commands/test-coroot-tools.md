# Test Coroot MCP Tools

Execute a comprehensive test of all Coroot MCP tools in a safe, non-destructive manner.

## Test Sequence

1. **Health Check**
   - Use the `health_check` tool to verify Coroot server connectivity

2. **Authentication Verification**
   - Use the `get_current_user` tool to verify authentication is working

3. **Project Discovery**
   - Use the `list_projects` tool to list all available projects
   - If projects exist, use the `get_project` tool on the first project
   - Use the `get_project_status` tool to check project health

4. **Create Test Project**
   - Use the `create_project` tool to create a new project named `mcp-test-{timestamp}`
   - Use the `get_project` tool to verify the project was created

5. **Applications Overview**
   - Use the `get_applications_overview` tool on an existing project
   - If applications exist, use the `get_application` tool on the first application

6. **Infrastructure Overview**
   - Use the `get_nodes_overview` tool to view infrastructure nodes
   - Use the `get_traces_overview` tool to view distributed tracing summary
   - Use the `get_deployments_overview` tool to view deployment history

7. **Application Deep Dive** (if applications exist)
   - Use the `get_application_logs` tool to retrieve recent logs
   - Use the `get_application_traces` tool to view traces

8. **Integrations**
   - Use the `list_integrations` tool to view all configured integrations
   - Use the `configure_integration` tool to set up a test webhook integration

9. **Configuration Management**
   - Use the `list_inspections` tool to view available inspection types
   - Use the `get_application_categories` tool to view current app categories
   - Use the `get_custom_applications` tool to view custom app definitions
   - If applications exist:
     - Use the `get_inspection_config` tool to get inspection configuration for an app
     - Use the `update_inspection_config` tool to test updating a configuration (with same values)
   - Use the `update_application_categories` tool to test category updates (optional)
   - Use the `update_custom_applications` tool to test custom app updates (optional)

10. **Advanced Application Features**
    - If applications exist:
      - Use the `get_application_rca` tool to get root cause analysis for any issues
      - Use the `get_application_profiling` tool to view CPU/memory profiling data
      - Use the `update_application_risks` tool to test risk configuration (with same values)

11. **User & Role Management**
    - Use the `update_current_user` tool to test user profile update (with same values)
    - Use the `list_users` tool to view all users (if admin)
    - Use the `get_roles` tool to view available roles

12. **Advanced Project Management**
    - Use the `update_project_settings` tool to test project settings update (with same values)
    - Use the `list_api_keys` tool to view project API keys
    - Use the `create_api_key` tool to create a test API key

13. **Node & Incident Management**
    - If nodes exist from overview:
      - Use the `get_node` tool to get detailed node information
    - If incidents exist:
      - Use the `get_incident` tool to view incident details

14. **Dashboard Management**
    - Use the `list_dashboards` tool to view all dashboards
    - Use the `create_dashboard` tool to create a test dashboard
    - Use the `get_dashboard` tool to retrieve the created dashboard
    - Use the `update_dashboard` tool to update the test dashboard
    - Use the `delete_dashboard` tool to remove the test dashboard

15. **Integration Management**
    - Use the `test_integration` tool to test any existing integration
    - Use the `delete_integration` tool to remove the test webhook integration

16. **Custom Cloud Pricing**
    - Use the `get_custom_cloud_pricing` tool to view current pricing
    - Use the `update_custom_cloud_pricing` tool to test setting custom pricing
    - Use the `delete_custom_cloud_pricing` tool to remove custom pricing

17. **System Configuration**
    - Use the `get_sso_config` tool to view SSO settings
    - Use the `update_sso_config` tool to test SSO configuration (with same values)
    - Use the `get_ai_config` tool to view AI provider settings
    - Use the `update_ai_config` tool to test AI configuration (with same values)

18. **Database Instrumentation**
    - If applications exist:
      - Use the `get_db_instrumentation` tool for mysql type
      - Use the `update_db_instrumentation` tool to test configuration (with same values)

19. **Risk Assessment**
    - Use the `get_risks_overview` tool to view comprehensive risk analysis

20. **Panel Data & Advanced Features**
    - If dashboards exist:
      - Use the `get_panel_data` tool to retrieve data for a specific panel
    - Use the `get_integration` tool to get detailed config for a specific integration
    - Use the `configure_profiling` tool to test profiling configuration
    - Use the `configure_tracing` tool to test trace collection settings
    - Use the `configure_logs` tool to test log collection configuration
    - Use the `create_or_update_role` tool to create a test role

21. **Cleanup**
    - Use the `delete_project` tool to remove the test project (mcp-test-{timestamp})

## Important Notes

- Generate a unique project name using current timestamp to avoid conflicts
- Only query existing resources, don't modify them
- For each tool call, report success/failure and key findings
- If a tool fails, note the error but continue with other tests
- Summarize overall MCP server health at the end