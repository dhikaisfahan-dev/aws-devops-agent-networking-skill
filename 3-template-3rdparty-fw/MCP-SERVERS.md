# Fortinet MCP Servers Reference

For integrating with AWS DevOps Agent or Kiro for direct firewall investigation.

## Available MCP Servers

| MCP Server | Connects To | GitHub |
|---|---|---|
| FortiGate MCP | FortiGate directly (individual firewall) | https://github.com/alpadalar/fortigate-mcp-server |
| FortiManager Code Mode MCP | FortiManager (centralized management) | https://github.com/jmpijll/fortimanager-code-mode-mcp |
| FortiAnalyzer MCP | FortiAnalyzer (centralized logging) | https://github.com/rstierli/fortianalyzer-mcp |

## When to Use Each

| Scenario | Use |
|---|---|
| Single firewall / quick check | FortiGate MCP |
| Centralized policy management (many firewalls) | FortiManager MCP |
| Log search, alerts, incidents, PCAPs | FortiAnalyzer MCP |
| Small environment (1-2 firewalls, no FAZ/FMG) | FortiGate MCP only |
| Enterprise (many firewalls + FAZ + FMG) | All three |

## Integration Notes

- These MCP servers connect directly to Fortinet appliances (not via AWS)
- For AWS DevOps Agent: run as Docker containers, connect via Agent Space → MCP Servers
- For Kiro: add to `~/.kiro/settings/mcp.json`
- All require API tokens from the respective Fortinet appliance
