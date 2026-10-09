local validation=require('scripts.validation')
local json_shape=require('scripts.json_shape')
local M={}
local identity={'version','token','hello_nonce','session_id','source_id','scope_id'}
function M.new(config,callbacks)
  local session,assembly,completed,stage,nonce,initial,started,last_send,last_tick,last_played,last_heartbeat
  local attempts,counter,highest,heartbeat_sequence=0,0,config.revision or 0,-1
  local snapshot_received,heartbeat_received=false,false
  local heartbeat_count=0
  local snapshot_read_at=config.snapshot_read_at
  local binding=config.binding
  local challenged_source,challenged_scope
  local api={}
  local function send(kind,fields)
    local row={type=kind}
    if session then for _,k in ipairs(identity) do row[k]=session[k] end
    else row.version=1; row.token=config.token; row.hello_nonce=nonce
      if binding then row.source_id=binding.source_id; row.scope_id=binding.scope_id end
    end
    for k,v in pairs(fields or {}) do row[k]=v end
    callbacks.send(row)
  end
  local function restart(tick)
    session,assembly,completed=nil,nil,nil
    snapshot_received,heartbeat_received=false,false; heartbeat_sequence=-1; heartbeat_count=0
    challenged_source,challenged_scope=nil,nil
    stage='challenge'; counter=counter+1
    initial=counter==1 and (config.initial_nonce or 'client-hello') or (config.initial_nonce or 'client-hello')..':'..counter
    nonce=initial; started=tick; attempts=0; last_send=nil; last_heartbeat=nil
  end
  local function hello(tick)
    if not last_send or tick-last_send>=60 then
      if attempts>=8 or tick-started>=600 then restart(tick) end
      send('hello',stage=='ack' and {challenge_id=nonce} or nil)
      attempts=attempts+1; last_send=tick
    end
  end
  local function same(row)
    if not session then return false end
    for _,k in ipairs(identity) do if row[k]~=session[k] then return false end end
    return true
  end
  function api.status()
    return {verified=session~=nil and snapshot_received and heartbeat_count>=4 and api.health~=nil
        and api.health.source_ok and api.health.source_read_at~=nil and api.health.source_read_at==snapshot_read_at,
      connected=session~=nil,stage=stage,revision=highest,health=heartbeat_received and api.health or nil,
      last_heartbeat_tick=last_heartbeat}
  end
  function api.reset_connection(new_binding)
    binding=new_binding or binding
    restart(last_tick or 0)
  end
  function api.on_tick(tick,ticks_played)
    if last_tick and last_played and ticks_played-last_played~=tick-last_tick then restart(tick) end
    last_tick,last_played=tick,ticks_played
    if not stage then restart(tick) end
    if session and tick-(last_heartbeat or started)>=900 then restart(tick) end
    if assembly and tick-assembly.started>=600 then assembly=nil; if session then send('resync_request') end end
    if not session then hello(tick) end
  end
  function api.on_message(row,tick,shape)
    if not validation.wire(row,shape) or row.token~=config.token then return end
    if row.type=='hello_challenge' then
      if stage~='challenge' or row.hello_nonce~=initial then return end
      if binding and (row.source_id~=binding.source_id or row.scope_id~=binding.scope_id) then return end
      challenged_source,challenged_scope=row.source_id,row.scope_id
      nonce=row.challenge_id; stage='ack'; started=tick; attempts=0; last_send=nil; hello(tick); return
    elseif row.type=='hello_ack' then
      if stage~='ack' or row.hello_nonce~=nonce or row.source_id~=challenged_source or row.scope_id~=challenged_scope then return end
      if binding and (row.source_id~=binding.source_id or row.scope_id~=binding.scope_id) then return end
      session=row; stage='bound'; started=tick; last_heartbeat=tick; send('resync_request'); return
    end
    if not same(row) then return end
    -- Check timeout here as well, before a buffered packet can revive authority.
    if tick-(last_heartbeat or started)>=900 then restart(tick); return end
    if row.type=='heartbeat' then
      if row.sequence<=heartbeat_sequence then return end
      heartbeat_sequence=row.sequence; heartbeat_count=math.min(4,heartbeat_count+1); last_heartbeat=tick; heartbeat_received=true
      api.health={source_ok=row.source_ok,source_read_at=row.source_read_at,source_age_seconds=row.source_age_seconds,
        last_success_at=row.last_success_at,last_error=row.last_error,refreshing=row.refreshing or false,received_tick=tick}
      send('heartbeat_ack',{sequence=row.sequence}); return
    end
    if row.type=='snapshot_begin' then
      if row.revision<highest then return end
      if completed and row.snapshot_id==completed.id and row.revision==completed.revision then
        send('snapshot_applied',{revision=row.revision,snapshot_id=row.snapshot_id}); return
      end
      if assembly then
        if row.revision<assembly.revision then return end
        if row.snapshot_id==assembly.id then
          if row.revision~=assembly.revision or row.chunk_count~=assembly.count or row.byte_length~=assembly.length then return end
          return -- Repeated begin cannot prolong expiry or discard received parts.
        end
      end
      assembly={id=row.snapshot_id,revision=row.revision,count=row.chunk_count,length=row.byte_length,started=tick,parts={},bytes=0,received=0}
      return
    elseif row.type~='snapshot_chunk' then return end
    if completed and row.snapshot_id==completed.id and row.revision==completed.revision then
      send('chunk_ack',{snapshot_id=row.snapshot_id,index=row.index})
      send('snapshot_applied',{snapshot_id=row.snapshot_id,revision=row.revision}); return
    end
    local a=assembly
    if not a or tick-a.started>=600 or row.snapshot_id~=a.id or row.revision~=a.revision or row.index>=a.count then return end
    local existing=a.parts[row.index+1]
    if existing and existing~=row.data then assembly=nil; return end
    if not existing then
      if a.bytes+#row.data>a.length or a.bytes+#row.data>262144 then assembly=nil; return end
      a.parts[row.index+1]=row.data; a.bytes=a.bytes+#row.data; a.received=a.received+1
    end
    send('chunk_ack',{snapshot_id=row.snapshot_id,index=row.index})
    if a.received~=a.count then return end
    assembly=nil
    if a.bytes~=a.length then return end
    local text=table.concat(a.parts)
    local rawshape=json_shape.inspect(text,callbacks.decode)
    if not rawshape then return end
    local ok,snapshot=pcall(callbacks.decode,text)
    if not ok or not validation.validate(snapshot,rawshape) then return end
    if snapshot.meta.source_id~=session.source_id or snapshot.meta.scope_id~=session.scope_id then return end
    if a.revision>highest then
      if callbacks.apply(snapshot,a.revision,rawshape)==false then return end
      highest=a.revision; snapshot_read_at=snapshot.meta.source_read_at
    end
    binding={source_id=session.source_id,scope_id=session.scope_id}
    completed={id=a.id,revision=a.revision}; snapshot_received=true
    send('snapshot_applied',{snapshot_id=a.id,revision=a.revision})
  end
  return api
end
return M
