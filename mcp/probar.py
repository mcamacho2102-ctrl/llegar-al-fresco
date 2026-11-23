#!/usr/bin/env python3
"""Arranca mcp/servidor.py por stdio y prueba sus herramientas sin cliente de IA.

    LLEGAR_URL=http://127.0.0.1:8768 python3 mcp/probar.py
"""

import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).with_name("servidor.py")


def main():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    counter = 0

    def rpc(method, params=None):
        nonlocal counter
        counter += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    info = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probar", "version": "1"}})
    print("Servidor:", info["result"]["serverInfo"])
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    tools = rpc("tools/list")["result"]["tools"]
    print("Herramientas:", ", ".join(t["name"] for t in tools))
    checks = [
        ("buscar_lugar", {"texto": "centro de dia"}),
        ("ruta_con_descansos", {"origen": "Plaza de la Virgen de la Paloma 1", "destino": "Biblioteca Pedro Salinas", "max_sin_descanso": 200, "salida": "2025-07-01T14:00:00"}),
        ("municipios_prioritarios", {"n": 3}),
        ("impacto_madrid", {}),
    ]
    failed = 0
    for name, args in checks:
        result = rpc("tools/call", {"name": name, "arguments": args})["result"]
        text = result["content"][0]["text"]
        failed += result["isError"]
        print(f"\n## {name} {'ERROR' if result['isError'] else 'ok'}\n{text[:700]}")
    proc.stdin.close()
    proc.wait(timeout=10)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
