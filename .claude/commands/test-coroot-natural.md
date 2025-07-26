# Test Coroot Integration

Perform a comprehensive test of the Coroot integration using natural language to verify all functionality works correctly.

## Test Sequence

1. **Connection Test**
   - Check if the Coroot server is healthy and responding

2. **Authentication Check**
   - Show me who I'm logged in as and what permissions I have

3. **Explore Projects**
   - List all the projects I have access to
   - Show me details about the first project
   - Check the health status of that project

4. **Create Test Environment**
   - Create a new test project with a unique name including today's date and time
   - Verify the project was created successfully

5. **Application Monitoring**
   - Show me an overview of all applications in an existing project
   - If there are any applications running, show me detailed metrics for one

6. **Infrastructure Inspection**
   - Display the infrastructure nodes and their resource usage
   - Show me the distributed tracing overview
   - List recent deployments and their impact

7. **Logs and Traces** (if applications exist)
   - Search for any error logs from the last hour
   - Show me some recent traces to understand request flow

8. **Integration Review**
   - List all the integrations that are configured
   - Set up a test webhook integration to demonstrate configuration

9. **Configuration Management**
   - Show me what inspection types are available for monitoring
   - Display the current application categorization rules
   - Check if there are any custom application definitions
   - If applications exist, show me the SLO configuration for one
   - Test updating an inspection threshold (using the same value to avoid changes)

10. **Advanced Troubleshooting**
    - If any applications have issues, analyze the root cause
    - Show me CPU and memory profiling data for a busy application
    - Review the risk configuration for critical applications

11. **User & Role Management**
    - Update my user profile (keeping the same values)
    - List all users in the system (if I have admin access)
    - Show me the available roles and permissions

12. **Advanced Project Management**
    - Update the test project settings (keeping the same values)
    - List all API keys for the test project
    - Create a new API key for testing

13. **Infrastructure Details**
    - If nodes are found, get detailed information about one
    - If any incidents exist, show me the details and timeline

14. **Dashboard Management**
    - List all custom dashboards in a project
    - Create a simple test dashboard
    - Retrieve the test dashboard configuration
    - Update the test dashboard (keeping the same config)
    - Delete the test dashboard

15. **Integration Testing**
    - Test an existing integration's connectivity
    - Delete the test webhook integration created earlier

16. **Cost Management**
    - Show me the custom cloud pricing configuration
    - Set some test custom pricing values
    - Remove the custom pricing configuration

17. **System Administration**
    - Display the SSO configuration
    - Show me the AI provider settings for root cause analysis
    - Test updating these configurations (keeping the same values)

18. **Database Monitoring**
    - If applications use databases, show me the instrumentation settings
    - Test updating database monitoring configuration

19. **Risk Analysis**
    - Give me a comprehensive risk assessment overview for all applications

20. **Panel Data & Advanced Features**
    - If custom dashboards exist, show me the data for a specific panel
    - Get detailed configuration for the Prometheus integration
    - Configure profiling settings for an application (enable with 0.1 sample rate)
    - Set up trace collection with specific excluded paths
    - Configure log collection with warning level minimum
    - Create a custom role with read-only permissions

21. **Cleanup**
    - Delete the test project created at the beginning
    - Confirm all test resources have been cleaned up

## Expected Behavior

- Create only new test resources (don't modify existing ones)
- Handle any errors gracefully and continue testing
- Provide clear feedback about what's working and what isn't
- Give a final summary of the Coroot system's health and capabilities