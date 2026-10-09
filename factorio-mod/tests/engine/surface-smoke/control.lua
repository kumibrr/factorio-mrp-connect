-- Isolated engine fixture. No network, players, GUI simulation or business writes.
local state=require('__factorio-connect__/scripts/state')
local model=require('__factorio-connect__/scripts/view_model')
local layout=require('__factorio-connect__/scripts/layout')
local surface=require('__factorio-connect__/scripts/surface')
local fixture=require('fixture')
local wire=require('__factorio-connect__/scripts/wire_encode')
local validation=require('__factorio-connect__/scripts/validation')
local loaded,finished=false,false
local function check()
  local current=state.get()
  assert(current.revision==1 and #current.snapshot.work_orders==22)
  local view=model.build(current.snapshot,{verified=false})
  assert(view.centers[2].running_count==1 and view.centers[2].ready_count==3)
  assert(view.centers[3].waiting_count==4 and view.stock[10][1].on_hand_qty==14)
  for _,kind in ipairs({'machining','assembly','inspection','packing','generic'}) do
    assert(prototypes.entity['fc-station-'..kind].type=='simple-entity-with-owner')
  end
  local owned=storage.smoke_owned
  assert(owned.surface.valid and owned.surface.name=='odoo-factory' and owned.surface.peaceful_mode)
  local stations,belts,renders=0,0,0
  for center_id,row in pairs(owned.stations) do
    assert(row.entity.valid and row.entity.unit_number==storage.smoke_identity[center_id])
    assert(not row.entity.minable and not row.entity.destructible and not row.entity.rotatable)
    for _,object in ipairs(row.renders) do assert(object.valid);renders=renders+1 end
    stations=stations+1
  end
  for _,targets in pairs(owned.links) do for _,row in pairs(targets) do
    for _,entity in ipairs(row.entities) do assert(entity.valid and not entity.minable and not entity.destructible and not entity.active);belts=belts+1 end
    for _,object in ipairs(row.renders) do assert(object.valid);renders=renders+1 end
  end end
  assert(stations==4 and belts>0 and renders==27)
  assert(storage.smoke_unrelated.valid)
  return {factorio_version=script.active_mods.base,stations=stations,belts=belts,renders=renders,
    assembly_running=view.centers[2].running_count,assembly_ready=view.centers[2].ready_count,
    inspection_waiting=view.centers[3].waiting_count,posted_pump_stock=view.stock[10][1].on_hand_qty,
    save_load=loaded,gui_executed=false,wire_json=storage.smoke_wire,
    safe_integer_record_url=storage.smoke_safe_url,safe_integer_scope_valid=true}
end
script.on_init(function()
  storage.smoke_wire=wire.encode({version=1,type='heartbeat_ack',token='quote" braces{} snowman ☃',
    hello_nonce='engine-codec',session_id='cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    source_id='12345678-1234-5678-1234-567812345679',scope_id='company:1/warehouse:1',
    sequence=9007199254740991},helpers.table_to_json)
  assert(helpers.json_to_table(storage.smoke_wire).sequence==9007199254740991)
  local boundary=helpers.json_to_table(fixture)
  boundary.meta.company_id=9007199254740991
  boundary.meta.scope_id='company:9007199254740991/warehouse:1'
  assert(validation.validate(boundary))
  local prior=boundary.manufacturing_orders[1].id
  boundary.manufacturing_orders[1].id=9007199254740991
  for _,wo in ipairs(boundary.work_orders) do if wo.mo_id==prior then wo.mo_id=9007199254740991 end end
  storage.smoke_safe_url=model.build(boundary,{verified=false}).orders[9007199254740991].record_url
  assert(storage.smoke_safe_url:find('/9007199254740991',1,true))
  state.init()
  local snapshot=helpers.json_to_table(fixture)
  assert(state.accept(snapshot,1))
  storage.smoke_owned={}
  state.get().entity_slots=layout.reconcile(snapshot.work_centers,{})
  local view=model.build(snapshot,{verified=false})
  assert(#surface.reconcile(view,state.get().entity_slots,storage.smoke_owned)==0)
  storage.smoke_identity={}
  for center_id,row in pairs(storage.smoke_owned.stations) do storage.smoke_identity[center_id]=row.entity.unit_number end
  storage.smoke_unrelated=storage.smoke_owned.surface.create_entity{name='steel-chest',position={150,0},force='player'}
  assert(#surface.reconcile(view,state.get().entity_slots,storage.smoke_owned)==0)
  snapshot.work_centers[2].name='Assembly renamed';snapshot.work_centers[2].active=false
  local renamed=model.build(snapshot,{verified=false})
  assert(#surface.reconcile(renamed,state.get().entity_slots,storage.smoke_owned)==0)
  assert(storage.smoke_owned.stations[2].renders[1].text=='Assembly renamed (Archived)')
  assert(#surface.reconcile(view,state.get().entity_slots,storage.smoke_owned)==0)
  -- Exercise actual ownership cleanup, then leave a generated view in the save.
  surface.clear(storage.smoke_owned);assert(storage.smoke_unrelated.valid)
  assert(#surface.reconcile(view,state.get().entity_slots,storage.smoke_owned)==0)
  for center_id,row in pairs(storage.smoke_owned.stations) do storage.smoke_identity[center_id]=row.entity.unit_number end
  log('FC_SURFACE_SMOKE '..helpers.table_to_json(check()))
end)
script.on_load(function() loaded=true end)
script.on_event(defines.events.on_tick,function()
  if finished then return end
  finished=true
  assert(#surface.reconcile(model.build(state.get().snapshot,{verified=false}),state.get().entity_slots,storage.smoke_owned)==0)
  log('FC_SURFACE_SMOKE '..helpers.table_to_json(check()))
end)
