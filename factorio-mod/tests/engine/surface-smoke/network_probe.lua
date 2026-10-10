-- Native diamond, component supply, and underground-pair isolation acceptance.
local model=require('__factorio-connect__/scripts/view_model')
local physical=require('__factorio-connect__/scripts/production_surface')
local router=require('__factorio-connect__/scripts/production_routing')
local fixture=require('fixture')
local M={}
local function count(entity,name) return entity.get_inventory(defines.inventory.chest).get_item_count(name) end
local function healthy(snapshot) return model.build(snapshot,{connected=true,verified=true,health={source_ok=true,source_age_seconds=0}}) end
function M.init(surface)
  local snapshot=helpers.json_to_table(fixture)
  local order=snapshot.manufacturing_orders[6];order.requested_qty=4
  snapshot.manufacturing_orders={order};snapshot.work_orders={};snapshot.material_demands={}
  for i=1,4 do snapshot.work_orders[i]={id=2000+i,mo_id=6,center_id=i,operation_id=i,sequence=i,
    dependency_ids=i==1 and {} or i==4 and {2002,2003} or {2001},raw_state=(i==3 or i==4) and 'blocked' or 'done',
    unit_id=1,output_qty=0,carried_qty=0,required_qty=4,remaining_qty=4,ready_qty=0,expected_minutes=1,elapsed_minutes=0}
  end
  storage.network_view=healthy(snapshot);storage.network_owned={surface=surface}
  local warnings=physical.reconcile(storage.network_view,storage.network_owned,6000)
  assert(#warnings==0,table.concat(warnings,'\n'))
  storage.network_identity=storage.network_owned.production[6].nodes[2001].entity.unit_number

  local supply=healthy(helpers.json_to_table(fixture))
  for k in pairs(supply.orders) do if k~=1 and k~=6 then supply.orders[k]=nil end end
  supply.orders[1].materials={}
  local materials={};for _,m in ipairs(supply.orders[6].materials) do if m.product_id==9 then materials[#materials+1]=m end end
  supply.orders[6].materials=materials
  storage.supply_view=supply;storage.supply_owned={surface=surface}
  warnings=physical.reconcile(supply,storage.supply_owned,10000)
  assert(#warnings==0,table.concat(warnings,'\n'))

  surface.request_to_generate_chunks({x=1000,y=0},1);surface.force_generate_chunk_requests()
  local a=surface.create_entity{name='express-underground-belt',position={1002,0},direction=defines.direction.east,type='input',force='player'}
  local b=surface.create_entity{name='express-underground-belt',position={1008,0},direction=defines.direction.east,type='output',force='player'}
  assert(a.neighbours==b)
  local occupied={['1002:0']={kind='belt',direction=4,type='input'},['1008:0']={kind='belt',direction=4,type='output'}}
  local path=router.route({x=1000,y=0},{x=1012,y=0},occupied);assert(path)
  for _,spec in ipairs(path) do spec.force='player';assert(surface.create_entity(spec)) end
  assert(a.neighbours==b,'new route stole an existing underground connection')
  storage.network_pair={a,b}
end
function M.tick(tick)
  if storage.network_finished then return end
  if tick==1 or tick%6==0 then
    physical.update(storage.network_view,storage.network_owned,tick)
    physical.update(storage.supply_view,storage.supply_owned,tick)
  end
  local row=storage.network_owned.production[6]
  if tick==7000 then
    assert(row.nodes[2001].released==4 and row.nodes[2002].released==4,'fan-out did not reach the first branch')
    assert(row.nodes[2003].released==0,'blocked branch produced output')
    assert(row.nodes[2004].joined==0,'join advanced without both native receipts')
    local waiting=0
    for _,e in ipairs(row.nodes[2004].incoming) do waiting=waiting+count(e.complete,'fc-workpiece') end
    assert(waiting==4,'completed branch did not arrive at the join')
    for _,op in ipairs(storage.network_view.orders[6].operations) do op.raw_state='done' end
  end
  if tick==12000 then
    assert(count(row.nodes[2004].receipt,'fc-complete')==4,'diamond completion did not reach the output box')
    local supply=storage.supply_owned
    local producer=supply.production[1].machines[1]
    assert(count(producer.outgoing[1].complete,'fc-complete')==60,'component output did not arrive in its shared product area')
    assert(count(supply.production_buffers['9:1'].stock,'fc-raw-material')==46,'operation receipts changed posted stock')
    assert(count(supply.production[6].material_edges[1].complete,'fc-raw-material')==10,'allocated components did not feed assembly')
    assert(supply.production[6].machines[1].released==0,'component arrival invented assembly output')
    assert(storage.network_pair[1].neighbours==storage.network_pair[2],'underground pairing changed during transport')
    local identity=row.nodes[2001].entity.unit_number
    assert(identity==storage.network_identity)
    assert(#physical.reconcile(storage.network_view,storage.network_owned,6000)==0)
    assert(storage.network_owned.production[6].nodes[2001].entity.unit_number==identity)
    storage.network_finished=true
    log('FC_NETWORK_SMOKE '..helpers.table_to_json{native_diamond=true,join_waits_for_all=true,complete_markers=4,
      shared_component_receipts=60,allocated_material_receipts=10,posted_stock_unchanged=46,underground_pairing=true,save_load=true})
  end
end
return M
