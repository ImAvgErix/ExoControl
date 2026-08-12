# Aether v1.4 Architecture

```
Agent (any model / any harness)
        │ MCP
        ▼
 SmartController
   ├─ UIMemory (successful targets)
   ├─ Observation cache (TTL)
   ├─ find_targets: memory → Cua a11y → fused OCR/structure → OCR → coords
   ├─ smart_click / type / scroll / drag / hotkey
   ├─ batch(actions[])
   ├─ backends: CuaBackend | LocalBackend
   ├─ LocalGrounder (OpenCV + OCR)
   └─ BrowserEngine (Playwright Spaces)
```

Loop: Observe → Ground → Act → Verify → Memory update → Retry if needed

