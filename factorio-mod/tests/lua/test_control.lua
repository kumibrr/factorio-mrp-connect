local f=require('view_fixtures')
return {
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
