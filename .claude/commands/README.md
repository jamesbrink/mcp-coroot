# Claude Code Slash Commands for Coroot MCP

This directory contains custom slash commands for testing the Coroot MCP server integration.

## Available Commands

### `/test-coroot-tools`
A comprehensive test suite that explicitly calls each MCP tool to verify functionality. This command:
- Tests all 15 Coroot MCP tools in a logical sequence
- Creates test resources with unique names to avoid conflicts
- Provides detailed feedback on each tool's success/failure
- Never modifies or deletes existing resources

### `/test-coroot-natural`
The same comprehensive test but using natural language instead of tool names. This command:
- Performs the same tests as above but with conversational requests
- Useful for testing the LLM's ability to map natural language to appropriate tools
- Creates the same test resources safely
- Provides user-friendly feedback

## Usage

In Claude Code, simply type:
```
/test-coroot-tools
```
or
```
/test-coroot-natural
```

## Prerequisites

Ensure your Coroot MCP server is configured and running:
1. The `.env` file contains valid Coroot credentials
2. The MCP server is accessible to Claude Code
3. Your Coroot instance is running and accessible

## Safety

Both commands are designed to be non-destructive:
- They only create new resources with unique timestamps
- They never delete or modify existing projects or configurations
- They handle errors gracefully and continue testing
- Test resources are clearly named (e.g., `mcp-test-20250126-143022`)