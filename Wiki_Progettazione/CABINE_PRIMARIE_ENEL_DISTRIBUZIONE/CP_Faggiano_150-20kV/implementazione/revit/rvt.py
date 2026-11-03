"""Client MCP minimo per Revit (server npm mcp-server-for-revit, stdio) -> add-in mcp-servers-for-revit (porta 8080)."""
import json, subprocess, sys, os

class Revit:
    def __init__(self):
        self.p = subprocess.Popen(["node", os.path.join(os.environ["LOCALAPPDATA"], "mcp-server-for-revit", "build", "index.js")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=open(os.path.join(os.environ.get("TEMP","."), "rvt_mcp_err.txt"), "w"), text=True, encoding="utf-8")
        self.i = 0
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cpf", "version": "1"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); self.p.stdin.flush()

    def _rpc(self, method, params):
        self.i += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.i, "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        while True:
            l = self.p.stdout.readline()
            if not l:
                raise RuntimeError("server MCP chiuso")
            try:
                m = json.loads(l)
            except Exception:
                continue
            if m.get("id") == self.i:
                return m

    def tools(self):
        return [t["name"] for t in self._rpc("tools/list", {})["result"]["tools"]]

    def tool(self, name, args=None):
        r = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        if "error" in r:
            raise RuntimeError(f"{name}: {r['error']}")
        return "\n".join(x.get("text", "") for x in r["result"].get("content", []) if x.get("type") == "text")

    def code(self, code, parameters=None):
        txt = self.tool("send_code_to_revit", {"code": code, "parameters": parameters or []})
        if "failed" in txt[:40].lower() or '"success": false' in txt or ('"errorMessage": "' in txt and '"errorMessage": ""' not in txt):
            raise RuntimeError(txt[:3000])
        return txt

    def close(self):
        self.p.stdin.close(); self.p.terminate()

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = Revit()
    print(r.tools())
    print(r.code('return document.Title + " | " + document.ActiveView.Name + " | unita: " + document.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId().TypeId + " | modificabile: " + document.IsModifiable;'))
    r.close()
