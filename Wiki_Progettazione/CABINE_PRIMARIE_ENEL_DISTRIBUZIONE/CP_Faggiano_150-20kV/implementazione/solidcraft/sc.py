import json, subprocess, sys
CLI = r"C:\Program Files\SolidCraft\solidcraft-cli.exe"
calls = json.load(open(sys.argv[1], encoding="utf-8"))
p = subprocess.Popen([CLI, "mcp", "--connect", "127.0.0.1:7878", "--allow-path", r"C:\Users\pietr\Desktop", "--allow-path", r"C:\Users\pietr\Workspace"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
def send(o):
    p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
def recv(i):
    while True:
        l = p.stdout.readline()
        if not l: return None
        try: m = json.loads(l)
        except Exception: continue
        if m.get("id") == i: return m
send({"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sc","version":"1"}}})
recv(0)
send({"jsonrpc":"2.0","method":"notifications/initialized"})
lim = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
if len(sys.argv) > 3:
    send({"jsonrpc":"2.0","id":999,"method":"tools/list"})
    for t in recv(999)["result"]["tools"]:
        if t["name"] in sys.argv[3].split(","):
            print(t["name"], json.dumps(t.get("description",""))[:1500], json.dumps(t["inputSchema"])[:2500], "\n")
for k, c in enumerate(calls, 1):
    send({"jsonrpc":"2.0","id":k,"method":"tools/call","params":{"name":c[0],"arguments":c[1]}})
    r = recv(k)
    txt = json.dumps(r, ensure_ascii=False)
    if r and "result" in r:
        txt = "\n".join(x.get("text","") for x in r["result"].get("content",[]) if x.get("type")=="text") or txt
        if r["result"].get("isError"): txt = "ERROR: " + txt
    print(f"=== {c[0]} ===\n{txt[:lim]}\n", flush=True)
p.stdin.close(); p.terminate()
