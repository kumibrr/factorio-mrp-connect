local surface=require('__factorio-connect__/scripts/surface')
local physical=require('__factorio-connect__/scripts/production_surface')
local skins=require('__factorio-connect__/scripts/skins')
local M={}
local ref={center_id=2,mo_id=6,op_id=14}
local function count(entity,kind,name) return entity.get_inventory(kind).get_item_count(name) end
function M.init(view)
  local choices={};for _,name in ipairs(skins.choices('production')) do choices[name]=true end
  for _,name in ipairs({'stone-furnace','electric-furnace','assembling-machine-3','electric-mining-drill',
    'boiler','steam-engine','oil-refinery','chemical-plant','centrifuge','rocket-silo','lab','beacon','smoke-custom-underground-belt-machine'}) do
    assert(choices[name],name..' appearance missing')
  end
  local owned=storage.probe_holds_owned;local machine=owned.production[6].machines[1]
  local original=machine.entity;local lane=owned.production[6]
  original.get_inventory(defines.inventory.assembling_machine_input).insert{name='fc-raw-material',count=2}
  original.get_inventory(defines.inventory.assembling_machine_input).insert{name='fc-component-kit',count=2}
  assert(machine.released==3 and count(original,defines.inventory.assembling_machine_output,'fc-workpiece')==3)
  assert(surface.set_skin(view,owned,ref,'smoke-custom-underground-belt-machine'))
  assert(not original.valid and machine.entity.name=='fc-skin-production-smoke-custom-underground-belt-machine')
  assert(count(machine.entity,defines.inventory.assembling_machine_input,'fc-raw-material')==2)
  assert(count(machine.entity,defines.inventory.assembling_machine_input,'fc-component-kit')==2)
  assert(count(machine.entity,defines.inventory.assembling_machine_output,'fc-workpiece')==3)
  assert(machine.entity.get_recipe().name=='fc-process-raw-kit' and machine.released==3)
  assert(machine.materials[1].complete==machine.entity)
  for _,allocation in ipairs(machine.materials[1].allocations) do assert(allocation.complete==machine.entity) end
  physical.reconcile(view,owned,4000);assert(owned.production[6]==lane)
  assert(surface.set_skin(view,owned,ref,nil))
  assert(machine.entity.name=='fc-production-assembly' and machine.released==3)
  assert(surface.set_skin(view,owned,ref,'smoke-custom-underground-belt-machine'))
  storage.probe_partial_identity=machine.entity.unit_number
  local station_owned=storage.smoke_owned;local station_ref={center_id=2}
  assert(surface.set_skin(view,station_owned,station_ref,'stone-furnace'))
  assert(station_owned.stations[2].renders[1].valid)
  assert(surface.machine_for_entity(station_owned,station_owned.stations[2].entity).center_id==2)
  storage.smoke_identity[2]=station_owned.stations[2].entity.unit_number
  local packing=station_owned.stations[4];local box=packing.entity.prototype.collision_box
  assert(surface.set_skin(view,station_owned,{center_id=4},'stone-furnace'))
  local changed=packing.entity.prototype.collision_box
  assert(changed.left_top.x==box.left_top.x and changed.right_bottom.x==box.right_bottom.x,
    'a skin must not enlarge a small station collision footprint')
  storage.smoke_identity[4]=packing.entity.unit_number
end
function M.check(view)
  local machine=storage.probe_holds_owned.production[6].machines[1]
  assert(machine.entity.name=='fc-skin-production-smoke-custom-underground-belt-machine')
  assert(machine.entity.unit_number==storage.probe_partial_identity and machine.released==3)
  assert(storage.probe_holds_owned.machine_skins.production[14]=='smoke-custom-underground-belt-machine')
  assert(storage.smoke_owned.stations[2].entity.name=='fc-skin-station-assembly-stone-furnace')
  assert(storage.smoke_owned.stations[4].entity.name=='fc-skin-station-packing-stone-furnace')
  return {base_and_modded_skins=true,inventory_and_ledger_preserved=true,saved_skin=true,gui_executed=false}
end
return M
