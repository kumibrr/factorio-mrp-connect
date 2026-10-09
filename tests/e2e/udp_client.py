"""Test-only socket adapter: all protocol decisions/acks use production Lua."""
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
import time

# Decode like Factorio helpers (object null disappears), preserving raw JSON shape
# for the production receiver. No fabricated session/application acknowledgments.
LUA = r'''
package.path='/repo/factorio-mod/?.lua;'..package.path
local cjson=require('cjson')
local receiver=require('scripts.receiver')
local state=require('scripts.state')
storage={};state.init()
local shape=require('scripts.json_shape')
local wire_encode=require('scripts.wire_encode')
local function native(x)
 if x==cjson.null then return nil end
 if type(x)~='table' then return x end
 local y={} for k,v in pairs(x) do y[k]=native(v) end return y
end
local function decode(text) return native(cjson.decode(text)) end
local token=io.read('*l')
local sent,applied={},nil
local r=receiver.new({token=token,initial_nonce='live-isolated-client'}, {
 send=function(row) sent[#sent+1]=row end,decode=decode,
 apply=function(snapshot,revision,rawshape)
  local accepted=state.accept(snapshot,revision,rawshape)
  if accepted then applied={snapshot=state.get().snapshot,revision=state.get().revision} end
  return accepted end})
for line in io.lines() do
 local input=cjson.decode(line)
 sent={}; applied=nil
 r.on_tick(input.tick,input.tick)
 if input.packet then
  local raw=shape.inspect(input.packet,decode)
  if raw then r.on_message(decode(input.packet),input.tick,raw) end
 end
 local encoded={} for _,row in ipairs(sent) do encoded[#encoded+1]=wire_encode.encode(row,cjson.encode) end
 io.write(cjson.encode({sent=encoded,applied=applied,status=r.status()})..'\n');io.flush()
end
'''


def main():
    state, output = Path(sys.argv[1]), Path(sys.argv[2])
    script = Path('/tmp/live-receiver.lua')
    script.write_text(LUA)
    lua = subprocess.Popen(['lua5.2', str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    lua.stdin.write((state / 'pairing-token').read_text().strip() + '\n')
    lua.stdin.flush()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 34301))
    started = time.monotonic()
    latest = {'status': {}, 'history': []}
    while True:
        packet = None
        if select.select([sock], [], [], .05)[0]:
            data, peer = sock.recvfrom(1025)
            if peer == ('127.0.0.1', 34300) and len(data) <= 1024:
                packet = data.decode('utf-8')
        lua.stdin.write(json.dumps({'tick': int((time.monotonic() - started) * 60), 'packet': packet}) + '\n')
        lua.stdin.flush()
        response = json.loads(lua.stdout.readline())
        for row in response['sent']:
            sock.sendto(row.encode(), ('127.0.0.1', 34300))
        latest['status'] = response['status']
        applied = response.get('applied')
        if applied:
            latest.update(applied)
            latest['received_at'] = time.time()
            latest['history'].append({'revision': applied['revision'], 'source_read_at': applied['snapshot']['meta']['source_read_at'], 'received_at': latest['received_at'], 'center_names': [c['name'] for c in applied['snapshot']['work_centers']]})
        temporary = output.with_suffix('.new')
        temporary.write_text(json.dumps(latest))
        temporary.replace(output)


if __name__ == '__main__':
    main()
