local cjson = require('cjson')
local M = {}
function M.read(path)
  local f = assert(io.open('/repo/'..path)); local text = f:read('*a'); f:close()
  return cjson.decode(text)
end
function M.copy(v)
  if type(v) ~= 'table' then return v end
  local out = {}; for k,x in pairs(v) do out[k] = M.copy(x) end; return out
end
-- Reproduce actual Factorio JSON: object null disappears; arrays can have holes.
function M.native(v)
  if v == cjson.null then return nil end
  if type(v) ~= 'table' then return v end
  local out = {}; for k,x in pairs(v) do out[k] = M.native(x) end; return out
end
function M.rig(binding)
  local ok, module = pcall(require, 'scripts.receiver')
  assert(ok and module.new, 'receiver.new must implement verified snapshot reception')
  local vectors = M.native(M.read('contracts/fixtures/wire-v1.json'))
  local sent, applied = {}, {}
  local r = module.new({token=vectors.session.token, initial_nonce='saved-nonce', binding=binding}, {
    send=function(row) sent[#sent+1] = row end,
    decode=function(text) return M.native(cjson.decode(text)) end,
    apply=function(snapshot, revision) applied[#applied+1]={snapshot=snapshot, revision=revision}; return true end
  })
  r.on_tick(0, 0)
  local challenge = M.copy(vectors.session)
  challenge.type='hello_challenge'; challenge.session_id=nil; challenge.hello_nonce='saved-nonce'
  challenge.challenge_id='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
  r.on_message(challenge, 1)
  local session=M.copy(vectors.session); session.hello_nonce=challenge.challenge_id
  r.on_message(session, 2)
  for _, frame in ipairs(vectors.frames) do frame.hello_nonce=challenge.challenge_id end
  return r, vectors, sent, applied, challenge
end
return M
