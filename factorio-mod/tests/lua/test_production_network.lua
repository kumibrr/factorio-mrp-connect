local f=require('view_fixtures')
local function setup(diamond)
  f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
  for key in pairs(v.orders) do if key~=6 then v.orders[key]=nil end end
  v.orders[6].materials={}
  if diamond then
    local ops=v.orders[6].operations;local branch={}
    for k,x in pairs(ops[2]) do branch[k]=x end
    branch.id=99;branch.dependency_ids={14};ops[3].dependency_ids={15,99};ops[#ops+1]=branch
  end
  local owned={surface=game.create_surface()};local p=f.module('production_surface')
  local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
  return v,owned,p
end
return {
  changing_a_machine_skin_keeps_component_kits_connected=function()
    f.engine();prototypes.entity['fc-skin-production-stone-furnace']={}
    local v=f.module('view_model').build(f.snapshot(),f.healthy())
    v.orders={[6]=v.orders[6]};v.orders[6].operations[1].output_qty=3
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    assert(#p.reconcile(v,owned,40)==0)
    local row=owned.production[6];local first=row.machines[1];local original=first.entity
    local input=original.get_inventory(defines.inventory.assembling_machine_input)
    input.insert{name='fc-raw-material',count=3};input.insert{name='fc-component-kit',count=2}
    assert(p.set_skin(owned,{center_id=2,mo_id=6,op_id=14},'fc-skin-production-stone-furnace'))
    assert(row.nodes[14].entity==first.entity and not original.valid)
    assert(first.materials[1].complete==first.entity,'the kit feed must target the replacement machine')
    for _,allocation in ipairs(first.materials[1].allocations) do assert(allocation.complete==first.entity) end
    p.update(v,owned,0)
    input=first.entity.get_inventory(defines.inventory.assembling_machine_input)
    assert(first.released==2 and input.get_item_count('fc-raw-material')==1)
    assert(input.get_item_count('fc-component-kit')==0)
    assert(first.entity.get_inventory(defines.inventory.assembling_machine_output).get_item_count('fc-workpiece')==2)
  end,
  serial_connections_use_direct_belts_with_only_two_order_boxes=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    v.orders={[6]=v.orders[6]};v.orders[6].materials={}
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local row=owned.production[6];local boxes=0
    for _,entity in ipairs(row.entities) do if entity.name=='steel-chest' then boxes=boxes+1 end end
    assert(boxes==2,'a three-machine serial order needs only its input and final output boxes')
    for _,edge in ipairs(row.edges) do
      assert(edge.direct and not edge.source and not edge.complete,'serial work must go directly between machines')
      for _,belt in ipairs(edge.belts) do
        assert(belt.name=='transport-belt' and belt.position.y==row.machines[1].position.y,'serial belts must be straight and visible')
      end
    end
    assert(#row.belts<=26,'serial transport must not take detours through dispatch boxes')
  end,
  component_receipts_stay_at_the_producer_without_a_return_belt=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    v.orders={[1]=v.orders[1],[6]=v.orders[6]}
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local producer=owned.production[1].machines[1];local supply=producer.outgoing[1]
    assert(supply.complete==producer.receipt,'supplier completion belongs in its existing output box')
    assert(#supply.belts==0,'a shared stock display must not add a long return route')
  end,
  component_inputs_combine_into_one_short_native_feed=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local row=owned.production[6];local first=row.machines[1]
    assert(#row.material_edges==8,'individual component allocations must remain inspectable')
    assert(#first.materials==1,'component inputs must share one kit feed into assembly')
    local feed=first.materials[1]
    assert(feed.complete==first.entity,'components and workpieces must enter the same machine')
    assert(#feed.material_ids==7 and #feed.belts<=8,'seven assembly inputs need one short route')
    local belts=0
    for _,order in pairs(owned.production) do belts=belts+#order.belts end
    assert(belts<500,'the seeded factory must not recreate the factory-wide belt web')
  end,
  a_component_kit_waits_for_every_allocation_and_both_machine_inputs=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    for k in pairs(v.orders) do if k~=6 then v.orders[k]=nil end end
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local row=owned.production[6];local first=row.machines[1]
    v.orders[6].materials[1].reserved_qty=2
    p.update(v,owned,0)
    local feed=first.materials[1]
    assert(feed.dispatched==2,'the least available component limits complete kits')
    local input=first.entity.get_inventory(defines.inventory.assembling_machine_input)
    input.insert{name='fc-raw-material',count=3}
    v.orders[6].operations[1].output_qty=3;p.update(v,owned,6)
    assert(first.released==0,'workpieces alone cannot bypass the component kit')
    input.insert{name='fc-component-kit',count=2};p.update(v,owned,12)
    assert(first.released==2 and input.get_item_count('fc-raw-material')==1)
    assert(input.get_item_count('fc-component-kit')==0,'one kit must be consumed once per workpiece')
    p.update(v,owned,18);assert(first.released==2 and feed.dispatched==2)
  end,
  downward_material_allocation_corrections_replace_only_the_consumer=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    for k in pairs(v.orders) do if k~=1 and k~=6 then v.orders[k]=nil end end
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    p.reconcile(v,owned,40);p.update(v,owned,0)
    local old=owned.production[6];local other=owned.production[1].source
    local edge=old.material_edges[1]
    for _,d in ipairs(v.orders[6].materials) do if d.id==edge.material_id then d.reserved_qty=3 end end
    p.reconcile(v,owned,40);p.update(v,owned,60)
    assert(not old.source.valid and owned.production[1].source==other and other.valid)
    assert(owned.production[6].material_edges[1].dispatched==3)
  end,
  reassigned_operations_preserve_neighboring_order_cells=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    for k in pairs(v.orders) do if k~=1 and k~=2 then v.orders[k]=nil end end
    for _,order in pairs(v.orders) do order.materials={} end
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    p.reconcile(v,owned,40);local existing=owned.production[1].machines[1].entity
    v.orders[2].operations[1].center_id=1
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local moved=owned.production[2].machines[1].entity
    assert(moved.position.x==existing.position.x and moved.position.y~=existing.position.y)
    assert(moved.name=='fc-production-machining' and p.center_for_entity(owned,moved)==1)
    assert(owned.production[1].machines[1].entity==existing and existing.valid)
  end,
  adding_and_removing_a_consumer_reroutes_its_component_producer=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    local orders=v.orders;v.orders={[1]=orders[1]}
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    p.reconcile(v,owned,40);local first=owned.production[1].machines[1]
    assert(#first.outgoing==0)
    v.orders[6]=orders[6];p.reconcile(v,owned,40)
    local changed=owned.production[1].machines[1]
    assert(changed~=first and #changed.outgoing==1,'new component consumers must gain a supply route')
    v.orders[6]=nil;p.reconcile(v,owned,40)
    assert(#owned.production[1].machines[1].outgoing==0,'removed consumers must lose their supply route')
  end,
  simple_order_flows_keep_short_local_connections=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    local warnings=p.reconcile(v,owned,40);assert(#warnings==0,table.concat(warnings,'\n'))
    local a,b=owned.production[5],owned.production[6]
    assert(a.machines[1].entity.position.x==b.machines[1].entity.position.x,'orders must use consistent left-to-right stages')
    assert(a.machines[1].entity.position.y==a.machines[2].entity.position.y,'an unbranched order should stay on one row')
    assert(a.machines[1].entity.position.y~=b.machines[1].entity.position.y,'order flows must retain their own cells')
    assert(owned.production_buffers and owned.production_buffers['9:1'],'manufactured components need a shared buffer')
    assert(#owned.production[6].material_edges==8)
    local component=owned.production[1].machines[1]
    assert(#component.outgoing==1 and component.outgoing[1].hub=='9:1','component completion must feed the shared product area')
  end,
  a_join_waits_for_every_predecessor_and_a_branch_preserves_both_receipts=function()
    local v,owned,p=setup(true);local row=owned.production[6]
    assert(row.nodes and row.nodes[99],'valid branches must create nodes')
    local first=row.nodes[14];first.receipt.get_inventory(defines.inventory.chest).insert{name='fc-workpiece',count=3}
    first.released=3;v.orders[6].operations[1].output_qty=3
    p.update(v,owned,0)
    for _,edge in ipairs(first.outgoing) do
      assert(edge.source.get_inventory(defines.inventory.chest).get_item_count('fc-workpiece')==3,'both branch paths need the completion receipt')
    end
    local join=row.nodes[16]
    join.incoming[1].complete.get_inventory(defines.inventory.chest).insert{name='fc-workpiece',count=2}
    p.update(v,owned,60)
    assert(join.source.get_inventory(defines.inventory.chest).is_empty(),'one predecessor cannot satisfy a join')
    join.incoming[2].complete.get_inventory(defines.inventory.chest).insert{name='fc-workpiece',count=1}
    p.update(v,owned,120)
    assert(join.source.get_inventory(defines.inventory.chest).get_item_count('fc-workpiece')==1)
    assert(join.incoming[1].complete.get_inventory(defines.inventory.chest).get_item_count('fc-workpiece')==1)
  end,
  material_dispatch_is_bounded_and_not_reseeded_by_snapshots=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    local owned={surface=game.create_surface()};local p=f.module('production_surface')
    p.reconcile(v,owned,40);p.update(v,owned,0)
    local row=owned.production[6];local edge=row.material_edges[1]
    assert(edge and edge.dispatched==10)
    edge.source.get_inventory(defines.inventory.chest).remove{name='fc-component-kit',count=4}
    p.reconcile(v,owned,40);p.update(v,owned,60)
    assert(edge.source.get_inventory(defines.inventory.chest).get_item_count('fc-component-kit')==6)
    assert(edge.dispatched==10)
    local first=row.machines[1]
    first.entity.get_inventory(defines.inventory.assembling_machine_input).insert{name='fc-raw-material',count=2}
    v.orders[6].operations[1].output_qty=2;p.update(v,owned,120)
    assert(first.released==0,'recorded output still waits for physical component receipts')
  end
}
