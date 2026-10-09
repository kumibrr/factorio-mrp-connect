local F=require('fixtures')
local M={}
function M.atomic_state_and_explicit_reset()
  local ok,S=pcall(require,'scripts.state'); assert(ok and S.accept,'state.accept is required')
  storage={}; S.init()
  local p=F.native(F.read('contracts/fixtures/pumpworks-v1.json'))
  assert(S.accept(p,7))
  local before=storage.factorio_connect.snapshot
  p=F.copy(p); p.products[1].unit_id=999
  assert(not S.accept(p,8)); assert(storage.factorio_connect.snapshot==before)
  p=F.copy(before); p.meta.source_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd'
  assert(not S.accept(p,8))
  S.reset_binding(); assert(S.accept(p,1))
end
function M.reload_starts_unverified_without_changing_storage_during_on_load()
  local ok,S=pcall(require,'scripts.state'); assert(ok and S.accept,'save safe state is required')
  storage={}; S.init(); local p=F.native(F.read('contracts/fixtures/pumpworks-v1.json')); assert(S.accept(p,7))
  local persistent=storage.factorio_connect
  local scripts={}
  script={active_mods={base='2.0.77'},on_init=function(fn) scripts.init=fn end,on_load=function(fn) scripts.load=fn end,
    on_configuration_changed=function(fn) scripts.change=fn end,on_event=function(id,fn) scripts[id]=fn end}
  local V=require('view_fixtures');V.engine()
  defines.events={on_tick=1,on_udp_packet_received=2,on_runtime_mod_setting_changed=3,on_gui_click=4,on_player_created=5,on_selected_entity_changed=6}
  settings={global={['fc-pairing-token']={value='pairing-secret'},['fc-bridge-port']={value=34200}}}
  local sent=0
  helpers={table_to_json=function(v) return require('cjson').encode(v) end,json_to_table=function(v) return F.native(require('cjson').decode(v)) end,send_udp=function() sent=sent+1 end,recv_udp=function() end}
  game.tick=0;game.ticks_played=0;game.players={};game.active_mods={base='2.0.77'}
  package.loaded.control=nil; require('control')
  setmetatable(persistent,{__newindex=function() error('storage mutated during on_load') end})
  local before=require("cjson").encode(persistent)
  local running_game=game; game=nil
  scripts.load(); game=running_game
  assert(require("cjson").encode(persistent)==before)
  assert(storage.factorio_connect==persistent and persistent.revision==7)
  assert(persistent.session_id==nil)
  scripts[1]({tick=1}); assert(persistent.revision==7 and sent==1)
  script.active_mods.base='3.0.0'; game.tick=2; scripts[1]({tick=2})
  assert(sent==1 and persistent.revision==7)
end
return M
