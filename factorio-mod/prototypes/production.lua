-- Native logistics with no dependency on the player's electrical network.
data:extend({{type='recipe-category',name='fc-production'}})
for name,icon in pairs({['fc-raw-material']='iron-plate',['fc-workpiece']='iron-gear-wheel',['fc-complete']='engine-unit'}) do
  local item=table.deepcopy(data.raw.item[icon])
  item.name=name;item.stack_size=200;item.order='z[fc]-'..name
  item.localised_name={'item-name.'..name}
  item.place_result=nil;item.hidden=true
  data:extend({item})
end
for _,row in ipairs({{'raw','fc-raw-material','fc-workpiece'}, {'work','fc-workpiece','fc-workpiece'},
  {'final','fc-workpiece','fc-complete'}, {'raw-final','fc-raw-material','fc-complete'}}) do
  data:extend({{type='recipe',name='fc-process-'..row[1],category='fc-production',enabled=true,hidden=true,
    energy_required=1,ingredients={{type='item',name=row[2],amount=1}},results={{type='item',name=row[3],amount=1}},
    allow_productivity=false,allow_decomposition=false}})
end
for _,kind in ipairs({'machining','assembly','inspection','packing','generic'}) do
  local machine=table.deepcopy(data.raw['assembling-machine'][kind=='inspection' and 'assembling-machine-2' or 'assembling-machine-1'])
  machine.name='fc-production-'..kind;machine.localised_name={'entity-name.'..machine.name}
  machine.minable=nil;machine.next_upgrade=nil;machine.placeable_by=nil
  machine.flags={'placeable-neutral','player-creation','not-blueprintable','not-deconstructable'}
  machine.crafting_categories={'fc-production'};machine.energy_source={type='void'}
  machine.module_slots=0;machine.allowed_effects={};machine.fast_replaceable_group=nil
  data:extend({machine})
end
local inserter=table.deepcopy(data.raw.inserter['fast-inserter'])
inserter.name='fc-production-inserter';inserter.localised_name={'entity-name.fc-production-inserter'}
inserter.minable=nil;inserter.next_upgrade=nil;inserter.placeable_by=nil
inserter.flags={'placeable-neutral','player-creation','not-blueprintable','not-deconstructable'}
inserter.energy_source={type='void'};inserter.fast_replaceable_group=nil
inserter.uses_inserter_stack_size_bonus=false
-- Carry one marker at a time, so no source/output quantity changes depend on research.
inserter.stack_size_bonus=0
data:extend({inserter})
