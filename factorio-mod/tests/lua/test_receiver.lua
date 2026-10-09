local F = require('fixtures')
local M = {}
function M.complete_out_of_order_applies_once()
  local r,v,s,a=F.rig()
  r.on_message(v.frames[1], 10)
  for i=#v.frames,2,-1 do r.on_message(v.frames[i],10) end
  r.on_message(v.frames[2],11); r.on_message(v.frames[1],12)
  assert(#a==1 and a[1].revision==7)
  assert(s[#s].type=='snapshot_applied')
end
function M.partial_bad_length_or_reference_keeps_previous()
  local r,v,s,a=F.rig()
  v.frames[1].byte_length=v.frames[1].byte_length+1
  r.on_message(v.frames[1],10)
  for i=2,#v.frames do r.on_message(v.frames[i],10) end
  assert(#a==0)
  local validation=require('scripts.validation')
  local payload=F.native(F.read('contracts/fixtures/pumpworks-v1.json'))
  payload.products[1].unit_id=99999
  assert(not validation.validate(payload))
end
function M.wrong_nonce_session_token_and_lower_revision_are_rejected()
  local r,v,s,a=F.rig()
  for _,field in ipairs({'token','hello_nonce','session_id'}) do
    local b=F.copy(v.frames[1]); b[field]='wrong'; r.on_message(b,10)
    for i=2,#v.frames do r.on_message(v.frames[i],10) end
  end
  assert(#a==0)
  r.on_message(v.frames[1],11); for i=2,#v.frames do r.on_message(v.frames[i],11) end
  assert(#a==1)
  for _,f in ipairs(v.frames) do f.revision=6; r.on_message(f,12) end
  assert(#a==1)
end
function M.assembly_limits_and_expiry_bound_memory()
  local r,v,s,a=F.rig()
  for _,bad in ipairs({{chunk_count=513},{byte_length=262145},{chunk_count=0}}) do
    local b=F.copy(v.frames[1]); for k,x in pairs(bad) do b[k]=x end
    r.on_message(b,10); for i=2,#v.frames do r.on_message(v.frames[i],10) end
  end
  assert(#a==0)
  r.on_message(v.frames[1],20); r.on_message(v.frames[2],20)
  r.on_tick(620,620)
  for i=3,#v.frames do r.on_message(v.frames[i],621) end
  assert(#a==0)
end
function M.pause_delta_invalidates_connection()
  local r,v,s,a=F.rig()
  r.on_tick(3,3); r.on_tick(4,1000)
  for _,f in ipairs(v.frames) do r.on_message(f,5) end
  assert(#a==0 and not r.status().verified)
  assert(s[#s].type=='hello')
end
function M.source_change_requires_explicit_binding_reset()
  local r,v,s,a=F.rig({source_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd',scope_id='company:1/warehouse:1'})
  for _,f in ipairs(v.frames) do r.on_message(f,10) end
  assert(#a==0)
end
function M.delayed_challenge_and_ack_cannot_claim_authority()
  local r,v,s,a,c=F.rig()
  local old=F.copy(c); old.hello_nonce='wrong'; r.on_message(old,3)
  r.on_message(c,4) -- First stage challenge is ignored after final authority.
  local ack=F.copy(v.session); ack.hello_nonce='saved-nonce'; r.on_message(ack,5)
  for _,f in ipairs(v.frames) do r.on_message(f,10) end
  assert(#a==1)
end
function M.shared_wire_vectors_shape_parity()
  local validation=require('scripts.validation')
  local v=F.read('contracts/fixtures/wire-v1.json')
  for _,case in ipairs(v.cases) do
    local text=case.payload_json
    local shape=require('scripts.json_shape').inspect(text,function(raw) return F.native(require('cjson').decode(raw)) end)
    local ok=validation.wire(F.native(case.payload),shape)
    assert(ok==case.shape_valid, case.name or 'wire case')
  end
end
function M.raw_json_shape_guards_native_codec_ambiguity()
  local decode=function(text) return F.native(require('cjson').decode(text)) end
  local validation=require('scripts.validation'); local guard=require('scripts.json_shape')
  local v=F.read('contracts/fixtures/wire-v1.json'); local text=v.canonical_snapshot_utf8
  assert(validation.validate(decode(text),guard.inspect(text,decode)))
  for _,bad in ipairs({text:gsub('"boms":%[%]','"boms":{}'),text:gsub('"code":null,',''),text:gsub('"id":1,','"id":1.0,'),text:gsub('"stock":%[%]','"stock":[null]'),text:gsub('"id":1,','"id":9007199254740992,')}) do
    assert(not validation.validate(decode(bad),guard.inspect(bad,decode)))
  end
end
function M.shared_raw_snapshot_vectors()
  local validation=require('scripts.validation'); local guard=require('scripts.json_shape')
  local decode=function(text) return F.native(require('cjson').decode(text)) end
  for _,case in ipairs(F.read('contracts/fixtures/snapshot-validation-v1.json')) do
    assert(validation.validate(decode(case.json),guard.inspect(case.json,decode))==case.valid,case.name)
  end
end
function M.final_ack_must_match_challenged_source()
  local receiver=require('scripts.receiver')
  local v=F.native(F.read('contracts/fixtures/wire-v1.json')); local sent={}
  local r=receiver.new({token=v.session.token,initial_nonce='initial'},{send=function(row) sent[#sent+1]=row end,decode=function() end,apply=function() error('unexpected apply') end})
  r.on_tick(0,0)
  local c=F.copy(v.session); c.type='hello_challenge'; c.hello_nonce='initial'; c.session_id=nil; c.challenge_id='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
  r.on_message(c,1)
  local a=F.copy(v.session); a.source_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd'
  r.on_message(a,2)
  assert(not r.status().connected)
end
function M.retry_after_missing_confirmation_and_old_heartbeat_is_unverified()
  local r,v,s,a=F.rig()
  r.on_tick(902,902)
  assert(not r.status().verified and not r.status().connected)
  local hb=F.copy(v.session); hb.type='heartbeat'; hb.sequence=1; hb.source_ok=true; hb.source_age_seconds=0; hb.source_read_at='2026-10-09T12:00:00Z'
  r.on_message(hb,902); assert(not r.status().verified)
  for tick=961,1501,60 do r.on_tick(tick,tick) end
  assert(s[#s].type=='hello' and s[#s].challenge_id==nil)
end
function M.fresh_session_needs_both_snapshot_and_heartbeat()
  local r,v,s,a=F.rig()
  assert(not r.status().verified)
  for _,f in ipairs(v.frames) do r.on_message(f,10) end
  assert(not r.status().verified)
  local h=F.copy(v.session); h.type='heartbeat'; h.sequence=1; h.source_ok=true; h.source_age_seconds=0; h.source_read_at='2026-10-09T12:00:00Z'
  for sequence=1,3 do h.sequence=sequence; r.on_message(h,11+sequence); assert(not r.status().verified) end
  h.sequence=4; r.on_message(h,15); assert(r.status().verified)
  r.on_tick(16,16); r.on_tick(17,1017)
  r.on_message(h,18); assert(not r.status().verified)
end
function M.identical_save_buffered_current_transcript_cannot_verify_recovery()
  local r,v,s,a=F.rig({source_id='12345678-1234-5678-1234-567812345679',scope_id='company:1/warehouse:1'})
  -- F.rig represents a freshly restored deterministic client receiving the
  -- buffered challenge/ack from the still-current bridge session.
  for _,frame in ipairs(v.frames) do r.on_message(frame,10) end
  local h=F.copy(v.session); h.type='heartbeat'; h.sequence=1; h.source_ok=true
  h.source_read_at='2026-10-09T12:00:00Z'; h.source_age_seconds=0
  for sequence=1,3 do h.sequence=sequence; r.on_message(h,11+sequence) end
  assert(not r.status().verified,'buffered current transcript verified a restored connection')
  h.sequence=3; r.on_message(h,15); assert(not r.status().verified)
  h.sequence=4; r.on_message(h,300); assert(r.status().verified,'fourth live heartbeat failed to establish recovery')
end
function M.recovery_fence_requires_healthy_matching_accepted_source_time()
  local r,v,s,a=F.rig(); for _,frame in ipairs(v.frames) do r.on_message(frame,10) end
  local h=F.copy(v.session); h.type='heartbeat'; h.source_age_seconds=0
  h.source_read_at='2026-10-09T12:00:00Z'; h.source_ok=false
  for sequence=1,4 do h.sequence=sequence; r.on_message(h,10+sequence) end
  assert(not r.status().verified)
  h.sequence=5; h.source_ok=true; h.source_read_at='2026-10-09T12:00:01Z'; r.on_message(h,20)
  assert(not r.status().verified)
  h.sequence=6; h.source_read_at='2026-10-09T12:00:00Z'; r.on_message(h,21)
  assert(r.status().verified)
end
function M.validator_success_has_nil_error_and_failure_has_string()
  local V=require('scripts.validation')
  local p=F.native(F.read('contracts/fixtures/pumpworks-v1.json'))
  local ok,err=V.validate(p); assert(ok and err==nil,'snapshot success error must be nil')
  p.products[1].unit_id=999; ok,err=V.validate(p); assert(not ok and type(err)=='string')
  local v=F.native(F.read('contracts/fixtures/wire-v1.json'))
  ok,err=V.wire(v.session); assert(ok and err==nil,'wire success error must be nil')
  v.session.token=''; ok,err=V.wire(v.session); assert(not ok and type(err)=='string')
end
function M.shared_client_vectors_enforce_stage_nonce_and_outcome()
  local receiver=require('scripts.receiver'); local guard=require('scripts.json_shape')
  local decode=function(text) return F.native(require('cjson').decode(text)) end
  local v=F.native(F.read('contracts/fixtures/wire-v1.json'))
  for _,case in ipairs(v.cases) do if case.direction=='client' then
    local ctx=case.context; local sent={}; local applied=0
    local r=receiver.new({token=ctx.token,initial_nonce=ctx.initial_hello_nonce or 'nonce-vector-1',
      binding={source_id=ctx.source_id,scope_id=ctx.scope_id},revision=ctx.applied_revision or 0},
      {send=function(row) sent[#sent+1]=row end,decode=decode,apply=function() applied=applied+1; return true end})
    r.on_tick(0,0)
    local stage=ctx.handshake_stage or (ctx.session_id and 'bound' or 'ack')
    if stage~='challenge' then
      local c=F.copy(v.session); c.type='hello_challenge'; c.session_id=nil
      c.hello_nonce=ctx.initial_hello_nonce or 'nonce-vector-1'; c.challenge_id=ctx.pending_hello_nonce
      r.on_message(c,1); assert(r.status().stage=='ack',case.name..' final stage context')
    end
    if stage=='bound' then
      local ack=F.copy(v.session); ack.hello_nonce=ctx.pending_hello_nonce; ack.session_id=ctx.session_id
      r.on_message(ack,2); assert(r.status().connected,case.name..' bound context')
      if ctx.active_transfer then r.on_message(ctx.active_transfer,3) end
    end
    local before=#sent; local connected=r.status().connected
    r.on_message(case.payload,4,guard.inspect(case.payload_json,decode))
    local outcome='ignore'; local accepted=false
    if case.payload.type=='snapshot_begin' then
      -- A begin has no immediate response; observe the assembly independently
      -- of the vector's acceptance expectation, including malformed begins.
      r.on_message(v.frames[2],5)
      if #sent>before then
        assert(#sent==before+1 and sent[#sent].type=='chunk_ack',case.name..' assembly')
        outcome='start_assembly'; accepted=true
      end
    elseif #sent>before then
      local last=sent[#sent]
      if last.type=='hello' then
        assert(r.status().stage=='ack' and not r.status().connected and last.hello_nonce==case.payload.challenge_id and last.challenge_id==case.payload.challenge_id,case.name)
        outcome='send_final_hello_preserve_binding'; accepted=true
      elseif last.type=='resync_request' then
        assert(r.status().connected and not r.status().verified and last.hello_nonce==ctx.pending_hello_nonce and last.session_id==case.payload.session_id,case.name)
        outcome='bind_session_preserve_source'; accepted=true
      elseif last.type=='chunk_ack' then
        assert(last.index==case.payload.index and last.snapshot_id==case.payload.snapshot_id,case.name)
        outcome='store_and_ack_chunk'; accepted=true
      elseif last.type=='heartbeat_ack' then
        assert(last.sequence==case.payload.sequence and not r.status().verified and not r.status().health.source_ok,case.name)
        outcome='ack_transport_keep_source_stale'; accepted=true
      end
    end
    assert(accepted==case.accepted and outcome==case.outcome,case.name..' acceptance/outcome')
    if not accepted then assert(r.status().connected==connected and applied==0,case.name..' retained authority') end
  end end
end
return M
