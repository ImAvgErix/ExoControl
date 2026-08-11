"""
Example: Grok-driven loop using Aether smart tools.
Requires: OPENAI_API_KEY or XAI_API_KEY + aether-driver installed.
"""
from __future__ import annotations
import json, os
from aether.smart import SmartController

def main():
    ctrl = SmartController(prefer_cua=True)
    print("status:", json.dumps(ctrl.status(), indent=2))

    # Example autonomous micro-goal (replace with real LLM tool loop)
    goal = os.environ.get("AETHER_GOAL", "Submit")
    print("do:", ctrl.do(goal, max_steps=3))

    # Example form fill pattern
    # print(ctrl.smart_fill({"Email": "demo@x.ai", "Password": "secret"}, submit="Sign in"))

    # Example batch
    # print(ctrl.batch([
    #     {"op": "click", "query": "File"},
    #     {"op": "wait", "seconds": 0.3},
    #     {"op": "click", "query": "Save"},
    # ]))

if __name__ == "__main__":
    main()
