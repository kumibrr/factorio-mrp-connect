-- All dependencies load at top level; on_load never mutates persistent storage.
local receiver=require('scripts.receiver')
local state=require('scripts.state')
local json_shape=require('scripts.json_shape')
local wire_encode=require('scripts.wire_encode')
local view_model=require('scripts.view_model')
local layout=require('scripts.layout')
local surface=require('scripts.surface')
local gui=require('scripts.gui')
local skins=require('scripts.skins')
local connection,view,rendered_revision
local connection_reason='startup'
local function owned()
  storage.factorio_connect_surface=storage.factorio_connect_surface or {stations={},links={}}
  return storage.factorio_connect_surface
end
local function refresh(reconcile)
  local current=state.get()
  view=view_model.build(current and current.snapshot,connection and connection.status() or nil)
  view.revision=current and current.revision or 0
  local registry=owned()
  if current and current.snapshot and reconcile then
    current.entity_slots=layout.reconcile(current.snapshot.work_centers,current.entity_slots)
    registry.warnings=surface.reconcile(view,current.entity_slots,registry)
    rendered_revision=current.revision
  end
  if not current or not current.snapshot then rendered_revision=current and current.revision or 0 end
  for _,warning in ipairs(registry.warnings or {}) do view.warnings[#view.warnings+1]=warning end
  view.surface_available=registry.surface~=nil and registry.surface.valid
  surface.update(view,registry,game.tick)
  for _,player in pairs(game.players) do gui.ensure_button(player);gui.update(player,view,registry) end
end
local function supported()
  local base=script.active_mods.base
  return type(base)=='string' and base:match('^2%.')~=nil
end
local function connect()
  if not supported() then connection=nil; return end
  local token=settings.global['fc-pairing-token'].value
  if token=='' then connection=nil; return end
  local current=state.get()
  connection=receiver.new({token=token,initial_nonce='client:'..game.tick,restart_reason=connection_reason,
    revision=current and current.revision or 0,
    snapshot_read_at=current and current.snapshot and current.snapshot.meta.source_read_at or nil,
    binding=current and current.source_id and {source_id=current.source_id,scope_id=current.scope_id} or nil}, {
    decode=function(text) return helpers.json_to_table(text) end,
    send=function(row)
      local ok,text=pcall(wire_encode.encode,row,helpers.table_to_json)
      if ok and type(text)=='string' and #text<=1024 then helpers.send_udp(settings.global['fc-bridge-port'].value,text) end
    end,
    apply=function(snapshot,revision,shape) return state.accept(snapshot,revision,shape) end
  })
end
script.on_init(function() state.init();owned();connection=nil;view=nil;rendered_revision=nil;connection_reason='startup' end)
script.on_load(function() connection=nil;view=nil;rendered_revision=nil;connection_reason='load' end)
script.on_configuration_changed(function() state.init();owned();connection=nil;view=nil;rendered_revision=nil;connection_reason='configuration_changed' end)
script.on_event(defines.events.on_runtime_mod_setting_changed,function(event)
  if event.setting=='fc-bridge-port' or event.setting=='fc-pairing-token' then connection=nil;connection_reason='settings_changed' end
end)
script.on_event(defines.events.on_tick,function(event)
  if not supported() then connection=nil; return end
  state.init()
  if not connection then connect() end
  if connection then connection.on_tick(event.tick,game.ticks_played); helpers.recv_udp() end
  local current=state.get()
  if not view or current.revision~=rendered_revision or event.tick%60==0 then
    refresh(not view or current.revision~=rendered_revision or event.tick%300==0)
  elseif event.tick%6==0 then
    surface.update(view,owned(),event.tick)
  end
end)
script.on_event(defines.events.on_udp_packet_received,function(event)
  if not connection or event.source_port~=settings.global['fc-bridge-port'].value or type(event.payload)~='string' or #event.payload>1024 then return end
  local shape=json_shape.inspect(event.payload,helpers.json_to_table)
  if not shape then return end
  local ok,row=pcall(helpers.json_to_table,event.payload)
  if ok then connection.on_message(row,game.tick,shape) end
end)
script.on_event(defines.events.on_player_created,function(event)
  local player=game.get_player(event.player_index)
  if player then gui.ensure_button(player) end
end)
script.on_event(defines.events.on_selected_entity_changed,function(event)
  local player=game.get_player(event.player_index)
  if not player then return end
  local machine=surface.machine_for_entity(owned(),player.selected)
  if machine then
    if not view then refresh(true) end
    local skin=skins.saved(owned(),machine.op_id and 'production' or 'station')[machine.op_id or machine.center_id]
    gui.show_machine(player,view,machine,skin)
  end
end)
local function handle_gui(event)
  local player=game.get_player(event.player_index)
  if not player then return end
  if not view then refresh(true) end
  -- A click opens the native picker; only its change event applies a skin.
  if event.element and event.element.name=='fc_machine_skin' and event.name~=defines.events.on_gui_elem_changed then return end
  local action=gui.handle(player,event,view)
  if type(action)=='table' and action.action=='skin' then
    local ok,err=surface.set_skin(view,owned(),action.machine,action.skin)
    if ok then gui.show_machine(player,view,action.machine,action.skin)
    else
      local panel=player.gui.screen.fc_machine_panel
      if panel then
        panel.fc_machine_error.caption=err
        panel.fc_machine_appearance.fc_machine_skin.elem_value=skins.saved(owned(),action.machine.op_id and 'production' or 'station')[action.machine.op_id or action.machine.center_id]
      end
    end
  elseif action=='reset' then
    state.reset_binding()
    surface.clear(owned());owned().warnings={}
    state.get().entity_slots={}
    -- reset_connection(nil) preserves the old binding; create a fresh receiver.
    connection=nil;view=nil;rendered_revision=nil;connection_reason='local_repair'
    refresh(false)
    gui.show(player,view,nil)
  end
end
script.on_event(defines.events.on_gui_click,handle_gui)
script.on_event(defines.events.on_gui_elem_changed,handle_gui)
script.on_event(defines.events.on_gui_closed,function(event)
  local player=game.get_player(event.player_index)
  local panel=player and player.gui.screen.fc_machine_panel
  if panel and event.element==panel then panel.destroy() end
end)
