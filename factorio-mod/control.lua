-- All dependencies load at top level; on_load never mutates persistent storage.
local receiver=require('scripts.receiver')
local state=require('scripts.state')
local json_shape=require('scripts.json_shape')
local connection
local function supported()
  local base=script.active_mods.base
  return type(base)=='string' and base:match('^2%.')~=nil
end
local function connect()
  if not supported() then connection=nil; return end
  local token=settings.global['fc-pairing-token'].value
  if token=='' then connection=nil; return end
  local current=state.get()
  connection=receiver.new({token=token,initial_nonce='client:'..game.tick,
    revision=current and current.revision or 0,
    snapshot_read_at=current and current.snapshot and current.snapshot.meta.source_read_at or nil,
    binding=current and current.source_id and {source_id=current.source_id,scope_id=current.scope_id} or nil}, {
    decode=function(text) return helpers.json_to_table(text) end,
    send=function(row)
      local ok,text=pcall(helpers.table_to_json,row)
      if ok and type(text)=='string' and #text<=1024 then helpers.send_udp(settings.global['fc-bridge-port'].value,text) end
    end,
    apply=function(snapshot,revision,shape) return state.accept(snapshot,revision,shape) end
  })
end
script.on_init(function() state.init(); connection=nil end)
script.on_load(function() connection=nil end)
script.on_configuration_changed(function() state.init(); connection=nil end)
script.on_event(defines.events.on_runtime_mod_setting_changed,function(event)
  if event.setting=='fc-bridge-port' or event.setting=='fc-pairing-token' then connection=nil end
end)
script.on_event(defines.events.on_tick,function(event)
  if not supported() then connection=nil; return end
  state.init()
  if not connection then connect() end
  if connection then connection.on_tick(event.tick,game.ticks_played); helpers.recv_udp() end
end)
script.on_event(defines.events.on_udp_packet_received,function(event)
  if not connection or event.source_port~=settings.global['fc-bridge-port'].value or type(event.payload)~='string' or #event.payload>1024 then return end
  local shape=json_shape.inspect(event.payload,helpers.json_to_table)
  if not shape then return end
  local ok,row=pcall(helpers.json_to_table,event.payload)
  if ok then connection.on_message(row,game.tick,shape) end
end)
