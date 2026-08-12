# Exo Control 1.3 architecture

```
Agent (any model / any harness)
        │ MCP / CLI / Python
        ▼
 ExoExecEngine.execute(steps, finally)
   ├─ lease + policy + safety gates
   ├─ ops_catalog (source of truth for lease / help)
   ├─ SmartController (internal hands/eyes)
   │    ├─ UIA cache + STA marshal
   │    ├─ synthetic inject (preferred)
   │    └─ compact observe / read / verify
   ├─ files / registry / infra (allowrooted, confirm-gated)
   └─ BrowserEngine (optional Playwright, loopback CDP)
```

Public import: `from exo_control import ExoExecEngine`.  
MCP: `python -m exo_control.slim_mcp_server` (`exo_exec`, `exo_screenshot`, `exo_help`).
