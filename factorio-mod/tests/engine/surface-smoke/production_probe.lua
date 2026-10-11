-- Real transport acceptance: no mocked inventories, belts or inserters.
local model=require('__factorio-connect__/scripts/view_model')
local physical=require('__factorio-connect__/scripts/production_surface')
local fixture=require('fixture')
local M={}
local cached_view
local function view()
  local s=helpers.json_to_table(fixture)
  local order=s.manufacturing_orders[6];order.requested_qty=80
  s.manufacturing_orders={order}
  local operations={}
  for _,wo in ipairs(s.work_orders) do if wo.mo_id==6 then
    wo.required_qty=80;wo.remaining_qty=80;wo.carried_qty=0;wo.output_qty=0
    if wo.id==14 then wo.raw_state=storage.probe_first_state or 'progress';wo.output_qty=storage.probe_first_output or 0 end
    if wo.id==15 then wo.raw_state=storage.probe_second_state or 'blocked' end
    if wo.id==16 then wo.raw_state=storage.probe_last_state or 'blocked' end
    operations[#operations+1]=wo
  end end
  s.work_orders=operations;s.material_demands={}
  return model.build(s,{connected=true,verified=true,health={source_ok=true,source_age_seconds=0}})
end
function M.init(surface)
  storage.probe_owned={surface=surface}
  assert(#physical.reconcile(view(),storage.probe_owned,2000)==0)
  local holds=model.build(helpers.json_to_table(fixture),{connected=true,verified=true,health={source_ok=true,source_age_seconds=0}})
  for key in pairs(holds.orders) do if key~=5 and key~=6 and key~=7 then holds.orders[key]=nil end end
  holds.orders[6].operations[1].output_qty=3
  storage.probe_holds_view=holds;storage.probe_holds_owned={surface=surface}
  assert(#physical.reconcile(holds,storage.probe_holds_owned,4000)==0)
  -- Persist a partially released stage before the create/save checkpoint.
  local partial=storage.probe_holds_owned.production[6]
  partial.source.get_inventory(defines.inventory.chest).remove{name='fc-raw-material',count=3}
  partial.machines[1].entity.get_inventory(defines.inventory.assembling_machine_output).insert{name='fc-workpiece',count=3}
  partial.machines[1].released=3
  storage.probe_partial_identity=partial.machines[1].entity.unit_number
end
function M.tick(tick)
  if storage.probe_finished then return end
  local owned=storage.probe_owned;cached_view=cached_view or view();local v=cached_view
  if tick==1 or tick%6==0 then
    physical.update(v,owned,tick)
    physical.update(storage.probe_holds_view,storage.probe_holds_owned,tick)
  end
  local lane=owned.production[6];local first,second,last=lane.machines[1],lane.machines[2],lane.machines[3]
  local function count(entity,name,inventory) return entity.get_inventory(inventory).get_item_count(name) end
  if tick==600 then storage.probe_source_count=lane.source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material') end
  if tick==800 then
    assert(storage.probe_source_count>0,'full TODO belt should leave work in the raw box')
    assert(lane.source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material')==storage.probe_source_count,'full belt did not stop its feed inserter')
    assert(count(first.entity,'fc-raw-material',defines.inventory.assembling_machine_input)>0)
    assert(count(first.entity,'fc-workpiece',defines.inventory.assembling_machine_output)==0,'running time invented output')
    assert(first.released==0 and second.released==0)
    storage.probe_first_output=3
    cached_view=nil
    local holds=storage.probe_holds_owned.production
    assert(holds[5].machines[1].entity.get_inventory(defines.inventory.assembling_machine_input).is_empty(),'ready work entered its machine')
    local ready_items=0
    for _,belt in ipairs(holds[5].machines[1].todo_belts) do for line=1,2 do ready_items=ready_items+belt.get_transport_line(line).get_item_count() end end
    assert(ready_items==10,'ready work must be visible on its TODO belt')
    assert(holds[7].source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material')==8,'material shortage did not hold raw feed')
    assert(not holds[7].feed.active)
    assert(holds[6].machines[1].entity.unit_number==storage.probe_partial_identity and holds[6].machines[1].released==3,'partial output ledger did not survive save/load')
    local partial_items=holds[6].machines[1].entity.get_inventory(defines.inventory.assembling_machine_output).get_item_count('fc-workpiece')
    for _,belt in ipairs(holds[6].belts) do for line=1,2 do partial_items=partial_items+belt.get_transport_line(line).get_item_count('fc-workpiece') end end
    assert(partial_items==3,'reload duplicated previously released output')
  end
  if tick==1200 then
    assert(first.released==3,'partial output must release exactly the Odoo quantity')
    assert(count(second.entity,'fc-workpiece',defines.inventory.assembling_machine_input)==0,'blocked stage consumed its TODO belt')
    storage.probe_first_state='done';storage.probe_second_state='progress'
    cached_view=nil
  end
  if tick==4200 then
    assert(count(second.entity,'fc-workpiece',defines.inventory.assembling_machine_input)>0,'next machine is not connected by native inserters and belt')
    assert(second.released==0)
    storage.probe_second_state='done';storage.probe_last_state='progress'
    cached_view=nil
  end
  if tick==8000 then storage.probe_last_state='done';cached_view=nil end
  if tick==12000 then
    assert(first.released==80 and second.released==80 and last.released==80)
    assert(lane.complete.get_inventory(defines.inventory.chest).get_item_count('fc-complete')==80,'completed work did not arrive at the final box')
    local identity=first.entity.unit_number
    assert(#physical.reconcile(v,owned,2000)==0)
    assert(owned.production[6].machines[1].entity.unit_number==identity,'repeat snapshot rebuilt a lane')
    assert(lane.source.get_inventory(defines.inventory.chest).is_empty(),'repeat snapshot reseeded raw materials')
    storage.probe_finished=true
    log('FC_PRODUCTION_SMOKE '..helpers.table_to_json{backpressure=true,partial_output=3,complete_markers=80,native_transport=true,ready_todo=true,shortage_hold=true,partial_save_load=true})
  end
end
return M
