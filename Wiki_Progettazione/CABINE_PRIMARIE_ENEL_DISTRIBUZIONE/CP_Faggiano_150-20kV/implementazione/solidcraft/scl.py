"""Client MCP minimo per SolidCraft (solidcraft-cli mcp --connect 127.0.0.1:7878)."""
import json, subprocess, sys
CLI = r"C:\Program Files\SolidCraft\solidcraft-cli.exe"

class SC:
    def __init__(self, port=7878):
        self.p = subprocess.Popen([CLI, "mcp", "--connect", f"127.0.0.1:{port}",
                                   "--allow-path", r"C:\Users\pietr\Desktop", "--allow-path", r"C:\Users\pietr\Workspace"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8")
        self.i = 0
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "scl", "version": "1"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); self.p.stdin.flush()

    def _rpc(self, method, params):
        self.i += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.i, "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        while True:
            l = self.p.stdout.readline()
            if not l:
                raise RuntimeError("connessione chiusa")
            try:
                m = json.loads(l)
            except Exception:
                continue
            if m.get("id") == self.i:
                return m

    def tool(self, name, args):
        r = self._rpc("tools/call", {"name": name, "arguments": args})
        if "error" in r:
            raise RuntimeError(f"{name}: {r['error']}")
        res = r["result"]
        txt = "\n".join(x.get("text", "") for x in res.get("content", []) if x.get("type") == "text")
        if res.get("isError"):
            raise RuntimeError(f"{name} {json.dumps(args)[:300]}: {txt}")
        try:
            return json.loads(txt)
        except Exception:
            return txt

    def ex(self, command, **params):
        return self.tool("execute", {"command": command, "params": params, "verbose": False})

    def close(self):
        self.p.stdin.close(); self.p.terminate()
