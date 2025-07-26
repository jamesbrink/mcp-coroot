# Known Coroot API Limitations

This document outlines known limitations and quirks of the Coroot API that affect the MCP server implementation.

## Empty Response Bodies

Several Coroot API endpoints return empty response bodies (with 200 status) instead of JSON:
- `POST /api/project/{project_id}/app/{app_id}/inspection/{type}/config` - Update inspection config
- `POST /api/project/{project_id}/api_keys` - Create API key
- `POST /api/project/{project_id}/custom_cloud_pricing` - Update cloud pricing
- `GET/POST /api/project/{project_id}/dashboards` - Dashboard management
- `POST /api/project/{project_id}/app/{app_id}/logs` - Configure log collection

**Workaround**: The MCP client uses `_parse_json_response()` helper that returns `{"status": "success"}` for empty 2xx responses.

## Large Response Sizes

Some endpoints return extremely large responses that can exceed token limits:
- `GET /api/project/{project_id}/app/{app_id}/tracing` - Can return 100k+ tokens
- `GET /api/project/{project_id}/app/{app_id}/profiling` - Can return 180k+ tokens

**Recommendation**: Always use time filters (`from_timestamp`, `to_timestamp`) to limit data size.

## Not Implemented Features

Based on testing, these features appear incomplete in Coroot:
- **Dashboard CRUD** - Returns empty responses or errors
- **RCA (Root Cause Analysis)** - Returns "not implemented yet" message
- **Role Management** - POST endpoint returns 405 Method Not Allowed

## API Inconsistencies

1. **Delete Operations**: Some return 204 No Content, others return 200 with empty body
2. **Error Responses**: Not all errors include JSON bodies, some return plain text
3. **Timestamp Formats**: Some endpoints expect Unix timestamps, others ISO 8601

## Authentication Quirks

- Session cookies expire after inactivity
- API keys only work for data ingestion endpoints, not management APIs
- No refresh token mechanism - requires full re-authentication

## Validation Issues

Some endpoints have strict but undocumented validation:
- `update_db_instrumentation` - Requires specific config format
- `test_integration` - Fails with "invalid data" for webhook type
- `configure_profiling/tracing/logs` - Parameter type validation

## Best Practices

1. **Always handle empty responses** - Many write operations return no body
2. **Use time filters** - Prevent overwhelming response sizes
3. **Catch authentication errors** - Re-authenticate when sessions expire
4. **Validate input types** - The API is strict about parameter types
5. **URL encode IDs** - Application IDs often contain slashes

## Testing Recommendations

When testing the MCP server:
1. Create test projects to avoid affecting production data
2. Use short time windows for trace/profiling queries
3. Expect some endpoints to fail in current Coroot versions
4. Clean up test resources (projects, integrations) after testing