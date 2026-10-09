local f=require('view_fixtures')
local F=require('fixtures')
local function recovery_rig()
  f.engine();local p=f.player();game.players={p};game.tick=0;game.ticks_played=0;game.get_player=function() return p end
  storage={};local state=require('scripts.state');state.init()
  local vectors=F.native(F.read('contracts/fixtures/wire-v1.json'))
  local snapshot=F.native(require('cjson').decode(vectors.canonical_snapshot_utf8))
  assert(state.accept(snapshot,1000))
  local sent,events={},{}
  script={active_mods={base='2.0.77'},on_init=function(fn) events.init=fn end,on_load=function(fn) events.load=fn end,
    on_configuration_changed=function(fn) events.change=fn end,on_event=function(event,fn) events[event]=fn end}
  defines.events={on_tick=1,on_udp_packet_received=2,on_runtime_mod_setting_changed=3,on_gui_click=4,on_player_created=5,on_selected_entity_changed=6}
  settings={global={['fc-pairing-token']={value=vectors.session.token},['fc-bridge-port']={value=34200}}}
  helpers={table_to_json=function(row) sent[#sent+1]=F.copy(row);return require('cjson').encode(row) end,
    json_to_table=function(text) return F.native(require('cjson').decode(text)) end,send_udp=function() end,recv_udp=function() end}
  package.loaded.control=nil;require('control')
  local function tick(value) game.tick=value;game.ticks_played=value;events[1]{tick=value} end
  local function receive(row) events[2]{source_port=34200,payload=require('cjson').encode(row)} end
  local function handshake(challenge_id,session_id)
    local c=F.copy(vectors.session);c.type='hello_challenge';c.session_id=nil
    c.hello_nonce=sent[#sent].hello_nonce;c.challenge_id=challenge_id;receive(c)
    local ack=F.copy(vectors.session);ack.hello_nonce=challenge_id;ack.session_id=session_id or ack.session_id;receive(ack)
    return ack
  end
  local function snapshot_frames(ack,revision)
    for _,original in ipairs(vectors.frames) do
      local frame=F.copy(original);frame.hello_nonce=ack.hello_nonce;frame.session_id=ack.session_id;frame.revision=revision
      if frame.data then frame.data=frame.data:gsub('2026%-10%-09T12:00:00Z','2026-10-09T13:00:00Z'):gsub('pump','valv') end
      receive(frame)
    end
  end
  return p,state,events,tick,handshake,snapshot_frames,receive
end
return {
  lost_cache_same_uuid_requires_confirmed_local_repair_to_accept_lower_revision=function()
    local p,state,events,tick,handshake,frames,receive=recovery_rig()
    events.load();tick(1);events[4]{player_index=1,element=p.gui.top.fc_open}
    assert(f.texts(p.gui.screen):find('Resynchronizing',1,true))
    assert(f.texts(p.gui.screen):find('Restart reason load',1,true))
    local ack=handshake('cccccccc-cccc-4ccc-8ccc-cccccccccccc')
    frames(ack,1);frames(ack,1000)
    assert(state.get().revision==1000 and state.get().snapshot.meta.source_read_at=='2026-10-09T12:00:00Z')
    assert(state.get().snapshot.products[1].name:find('pump',1,true))
    local old_source=state.get().source_id
    events[4]{player_index=1,element=f.find(p.gui.screen,'fc_repair')}
    assert(state.get().revision==1000,'unconfirmed repair cleared retained state')
    events[4]{player_index=1,element=f.find(p.gui.screen,'fc_confirm_repair')}
    assert(state.get().revision==0 and state.get().source_id==nil)
    tick(2);ack=handshake('dddddddd-dddd-4ddd-8ddd-dddddddddddd','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee');frames(ack,1)
    assert(state.get().revision==1 and state.get().source_id==old_source)
    assert(state.get().snapshot.meta.source_read_at=='2026-10-09T13:00:00Z')
    assert(state.get().snapshot.products[1].name:find('valv',1,true))
    local heartbeat=F.copy(ack);heartbeat.type='heartbeat';heartbeat.source_ok=true;heartbeat.source_age_seconds=0
    heartbeat.source_read_at='2026-10-09T13:00:00Z'
    for sequence=1,4 do heartbeat.sequence=sequence;receive(heartbeat) end
    tick(60)
    assert(f.texts(p.gui.screen):find('Synchronization: Healthy',1,true))
  end,
  ordinary_durable_cache_restart_accepts_advancing_revision_without_repair=function()
    local p,state,events,tick,handshake,frames=recovery_rig()
    events.load();tick(1);local ack=handshake('cccccccc-cccc-4ccc-8ccc-cccccccccccc');frames(ack,1001)
    assert(state.get().revision==1001 and state.get().snapshot.meta.source_read_at=='2026-10-09T13:00:00Z')
  end,
  confirmed_reset_clears_only_generated_view_and_rebuilds_unbound_receiver=function()
    f.engine();local p=f.player();game.players={p};game.tick=0;game.ticks_played=0;game.get_player=function() return p end
    storage={};local state=require('scripts.state');state.init();assert(state.accept(f.snapshot(),7))
    local sent,events={},{}
    script={active_mods={base='2.0.77'},on_init=function(fn) events.init=fn end,on_load=function(fn) events.load=fn end,
      on_configuration_changed=function(fn) events.change=fn end,on_event=function(event,fn) events[event]=fn end}
    defines.events={on_tick=1,on_udp_packet_received=2,on_runtime_mod_setting_changed=3,on_gui_click=4,on_player_created=5,on_selected_entity_changed=6}
    settings={global={['fc-pairing-token']={value='pairing-secret'},['fc-bridge-port']={value=34200}}}
    helpers={table_to_json=function(row) sent[#sent+1]=row;return '{}' end,json_to_table=function() return {} end,send_udp=function() end,recv_udp=function() end}
    package.loaded.control=nil;require('control');events[1]{tick=1}
    assert(sent[1].source_id==f.snapshot().meta.source_id)
    assert(events[4],'GUI local reset handler is required')
    local gui=require('scripts.gui');local view=require('scripts.view_model').build(state.get().snapshot,f.healthy())
    gui.show(p,view,2);events[4]{player_index=1,element=f.find(p.gui.screen,'fc_repair')}
    assert(state.get().snapshot)
    events[4]{player_index=1,element=f.find(p.gui.screen,'fc_confirm_repair')}
    assert(state.get().snapshot==nil and state.get().source_id==nil and state.get().revision==0)
    game.tick=2;game.ticks_played=2;events[1]{tick=2}
    assert(sent[#sent].source_id==nil and sent[#sent].scope_id==nil)
    assert(f.texts(p.gui.screen):find('Awaiting snapshot',1,true))
  end
}
