-- Native transport between shared center areas and product allocation buffers.
local production=require('scripts.production')
local router=require('scripts.production_routing')
local vm=require('scripts.view_model')
local M={}
local kinds={MACH='machining',ASSY='assembly',INSP='inspection',PACK='packing'}
local function key(x,y) return x..':'..y end
local function id(value) return string.format('%d',value) end
local function inventory(entity) return entity.get_inventory(defines.inventory.chest) end
local function destroy(row)
  for _,entity in ipairs(row.entities or {}) do if entity.valid then entity.destroy() end end
  for _,object in ipairs(row.renders or {}) do if object.valid then object.destroy() end end
end
function M.clear(owned)
  for _,row in pairs(owned.production or {}) do destroy(row) end
  for _,row in pairs(owned.production_buffers or {}) do destroy(row) end
  owned.production={};owned.production_slots={};owned.production_clocks={};owned.production_base_y=nil
  owned.production_buffers={};owned.production_node_slots={};owned.production_center_slots={};owned.production_buffer_slots={}
end
local function draw(surface,position,value,color)
  return rendering.draw_text{surface=surface,target=position,text=value,color=color or vm.palette.idle,
    alignment='center',scale=0.75,use_rich_text=false}
end
local function intact(row)
  if not row or row.incomplete then return false end
  for _,entity in ipairs(row.entities) do if not entity.valid then return false end end
  return true
end
local function fingerprint(lane,view,buffers)
  local parts={'network-v1',vm.number(lane.quantity),string.format('%d',lane.order.product_id)}
  local destinations={}
  for k,m in pairs(buffers) do if m.product_id==lane.order.product_id then destinations[#destinations+1]=k end end
  table.sort(destinations);for _,k in ipairs(destinations) do parts[#parts+1]='supply/'..k end
  for _,op in ipairs(lane.operations) do
    parts[#parts+1]=id(op.id)..'/'..id(op.center_id)..'/'..(kinds[view.centers[op.center_id].code] or 'generic')
    for _,dep in ipairs(op.dependency_ids) do parts[#parts+1]='d'..id(dep) end
  end
  for _,m in ipairs(lane.materials) do parts[#parts+1]='m'..id(m.id)..'/'..id(m.product_id)..'/'..id(m.location_id)..'/'..id(m.to)..'/'..vm.number(m.demand.demand_qty) end
  return table.concat(parts,':')
end
local function reserve(occupied,spec)
  local radius=spec.name:find('fc%-production%-') and spec.name~='fc-production-inserter' and 1 or 0
  for x=spec.position.x-radius,spec.position.x+radius do for y=spec.position.y-radius,spec.position.y+radius do
    occupied[key(x,y)]={kind=spec.name:find('belt') and 'belt' or 'entity',direction=spec.direction,type=spec.type}
  end end
end
local function create(surface,row,spec)
  local e=surface.create_entity(spec)
  if not e then return nil end
  e.minable=false;e.destructible=false;e.rotatable=false;e.operable=false
  row.entities[#row.entities+1]=e
  return e
end
local function build(surface,row,planned,occupied)
  if surface.request_to_generate_chunks then
    for _,spec in ipairs(planned) do surface.request_to_generate_chunks(spec.position,1) end
    surface.force_generate_chunk_requests()
  end
  for _,spec in ipairs(planned) do if not surface.can_place_entity(spec) then return false,'cannot place '..spec.name..' at '..spec.position.x..','..spec.position.y end end
  for _,spec in ipairs(planned) do
    local entity=create(surface,row,spec)
    if not entity then return false,'creation failed for '..spec.name..' at '..spec.position.x..','..spec.position.y end
    reserve(occupied,spec)
    spec.entity=entity
  end
  return true
end
local function add(planned,name,x,y,extra)
  local spec={name=name,position={x=x,y=y},force='player'}
  if extra then for k,v in pairs(extra) do spec[k]=v end end
  planned[#planned+1]=spec;return spec
end
local function position(owned,op,base_y)
  local center=owned.production_center_slots[op.center_id]
  if center==nil then
    center=0;for _,index in pairs(owned.production_center_slots) do center=math.max(center,index+1) end
    owned.production_center_slots[op.center_id]=center
  end
  local slot=owned.production_node_slots[op.id]
  if not slot or slot.center_id~=op.center_id then
    local index=0
    for _,s in pairs(owned.production_node_slots) do if s.center_id==op.center_id then index=math.max(index,s.index+1) end end
    slot={center_id=op.center_id,index=index};owned.production_node_slots[op.id]=slot
  end
  return {x=center*64,y=base_y+slot.index*64+(center%2)*16}
end
local function hub_key(product,location) return id(product)..':'..id(location) end
local function buffer_position(owned,k,base_y)
  if owned.production_buffer_slots[k]==nil then
    local index=0;for _,i in pairs(owned.production_buffer_slots) do index=math.max(index,i+1) end
    owned.production_buffer_slots[k]=index
  end
  return {x=-56,y=base_y+owned.production_buffer_slots[k]*80}
end
local function plan_order(lane,view,owned,base_y,occupied)
  local planned,nodes,edges={},{},{}
  local sinks={};for _,id in ipairs(lane.sinks) do sinks[id]=true end
  for _,op in ipairs(lane.operations) do
    local p=position(owned,op,base_y);local node={op_id=op.id,center_id=op.center_id,position=p,incoming={},outgoing={},materials={},root=#op.dependency_ids==0,
      input_name=#op.dependency_ids==0 and 'fc-raw-material' or 'fc-workpiece',output_name=sinks[op.id] and 'fc-complete' or 'fc-workpiece',released=0,dispatched=0,joined=0}
    nodes[op.id]=node
    node.source_spec=add(planned,'steel-chest',p.x-8,p.y)
    node.feed_spec=add(planned,'fc-production-inserter',p.x-7,p.y,{direction=defines.direction.west})
    node.todo_specs={}
    for x=p.x-6,p.x-3 do node.todo_specs[#node.todo_specs+1]=add(planned,'transport-belt',x,p.y,{direction=defines.direction.east}) end
    node.input_spec=add(planned,'fc-production-inserter',p.x-2,p.y,{direction=defines.direction.west})
    node.machine_spec=add(planned,'fc-production-'..(kinds[view.centers[op.center_id].code] or 'generic'),p.x,p.y)
    node.output_spec=add(planned,'fc-production-inserter',p.x+2,p.y,{direction=defines.direction.west})
    node.receipt_spec=add(planned,'steel-chest',p.x+3,p.y)
  end
  local hub_ports={}
  local function edge(from,to,material,hub)
    local node=to and nodes[to];local source_pos
    if from then
      local parent=nodes[from]
      source_pos={x=parent.position.x+6,y=parent.position.y+8+#parent.outgoing*4}
    else
      local k=hub_key(material.product_id,material.location_id)
      hub_ports[k]=(hub_ports[k] or 0)+1
      -- Each order has its own allocation port at a shared product buffer.
      local hubpos=buffer_position(owned,k,base_y)
      local slot=owned.production_slots[lane.mo_id]
      source_pos={x=hubpos.x+8+slot*4,y=hubpos.y+8+(hub_ports[k]-1)*4}
    end
    local target_pos
    if hub and not material then
      local p=buffer_position(owned,hub,base_y)
      target_pos={x=p.x-8,y=p.y+8+owned.production_slots[lane.mo_id]*4}
    else target_pos={x=node.position.x-8,y=node.position.y+8+(#node.incoming+#node.materials)*4} end
    local e={from=from,to=to,material_id=material and material.id,hub=hub,dispatched=0,
      product_receipt=hub and not material or false,name=material and 'fc-raw-material' or (hub and 'fc-complete' or 'fc-workpiece')}
    e.source_spec=add(planned,'steel-chest',source_pos.x,source_pos.y)
    e.feed_spec=add(planned,'fc-production-inserter',source_pos.x+1,source_pos.y,{direction=defines.direction.west})
    e.complete_spec=add(planned,'steel-chest',target_pos.x,target_pos.y)
    e.finish_spec=add(planned,'fc-production-inserter',target_pos.x-1,target_pos.y,{direction=defines.direction.west})
    e.start={x=source_pos.x+2,y=source_pos.y};e.finish={x=target_pos.x-2,y=target_pos.y}
    edges[#edges+1]=e
    if from then
      nodes[from].outgoing[#nodes[from].outgoing+1]=e
      if node then node.incoming[#node.incoming+1]=e end
    else node.materials[#node.materials+1]=e end
  end
  for _,e in ipairs(lane.edges) do edge(e.from,e.to) end
  for _,m in ipairs(lane.materials) do edge(nil,m.to,m,hub_key(m.product_id,m.location_id)) end
  local destinations={}
  for k,buffer in pairs(owned.production_buffers) do
    if buffer.product_id==lane.order.product_id then destinations[#destinations+1]=k end
  end
  -- The snapshot has no stock-move destination for finished output. Only a
  -- single destination product area can be connected without inventing a split.
  if #destinations==1 then for _,id in ipairs(lane.sinks) do edge(id,nil,nil,destinations[1]) end end
  for _,spec in ipairs(planned) do reserve(occupied,spec) end
  for _,e in ipairs(edges) do
    for _,p in ipairs({e.start,e.finish}) do
      for x=p.x-1,p.x+1 do for y=p.y-1,p.y+1 do
        if not occupied[key(x,y)] then occupied[key(x,y)]={kind='port',owner=e} end
      end end
    end
  end
  return planned,nodes,edges
end
local function route_order(planned,edges,occupied)
  for _,e in ipairs(edges) do
    for _,p in ipairs({e.start,e.finish}) do
      for x=p.x-1,p.x+1 do for y=p.y-1,p.y+1 do
        local entry=occupied[key(x,y)]
        if entry and entry.owner==e then occupied[key(x,y)]=nil end
      end end
    end
    local path,reason=router.route(e.start,e.finish,occupied)
    if not path then return false,reason..' '..e.start.x..','..e.start.y..' -> '..e.finish.x..','..e.finish.y end
    for _,spec in ipairs(path) do
      spec.force='player';planned[#planned+1]=spec;reserve(occupied,spec)
    end
  end
  return true
end
local function configure_inserter(e,pick,drop)
  e.pickup_position=pick;e.drop_position=drop;e.inserter_stack_size_override=1
end
function M.reconcile(view,owned,base_y)
  if not owned.surface or not owned.surface.valid then return {} end
  local surface=owned.surface
  owned.production=owned.production or {};owned.production_slots=owned.production_slots or {}
  owned.production_node_slots=owned.production_node_slots or {};owned.production_center_slots=owned.production_center_slots or {}
  owned.production_buffers=owned.production_buffers or {};owned.production_buffer_slots=owned.production_buffer_slots or {}
  local lanes,warnings=production.plan(view);local wanted={};local next_index=0
  owned.production_base_y=owned.production_base_y or base_y or 40;base_y=owned.production_base_y
  for _,index in pairs(owned.production_slots) do next_index=math.max(next_index,index+1) end
  local buffers={}
  for _,lane in ipairs(lanes) do
    wanted[lane.mo_id]=true
    if owned.production_slots[lane.mo_id]==nil then owned.production_slots[lane.mo_id]=next_index;next_index=next_index+1 end
    for _,m in ipairs(lane.materials) do buffers[hub_key(m.product_id,m.location_id)]=m end
  end
  for id,row in pairs(owned.production) do
    local lane
    for _,l in ipairs(lanes) do if l.mo_id==id then lane=l;break end end
    local corrected=false
    if lane and intact(row) then
      for i,op in ipairs(lane.operations) do
        if row.machines[i] and row.machines[i].released>production.budget(op,lane.quantum,lane.count) then corrected=true end
      end
      local byid={};for _,m in ipairs(lane.materials) do byid[m.id]=m end
      for _,e in ipairs(row.material_edges or {}) do
        if byid[e.material_id] and e.dispatched>production.material_budget(byid[e.material_id],lane.count) then corrected=true end
      end
    end
    if not wanted[id] or not intact(row) or row.signature~=fingerprint(lane,view,buffers) or corrected then destroy(row);owned.production[id]=nil end
  end
  for k,row in pairs(owned.production_buffers) do if not buffers[k] or not intact(row) then destroy(row);owned.production_buffers[k]=nil end end
  local occupied={}
  for _,row in pairs(owned.production) do for _,e in ipairs(row.entities) do reserve(occupied,{name=e.name,position=e.position,direction=e.direction,type=e.name:find('underground') and e.belt_to_ground_type or nil}) end end
  for _,row in pairs(owned.production_buffers) do for _,e in ipairs(row.entities) do reserve(occupied,{name=e.name,position=e.position,direction=e.direction,type=e.name:find('underground') and e.belt_to_ground_type or nil}) end end
  local buffer_ids={};for k in pairs(buffers) do buffer_ids[#buffer_ids+1]=k end;table.sort(buffer_ids)
  for _,k in ipairs(buffer_ids) do
    local material=buffers[k];local row=owned.production_buffers[k]
    if not row then
      local p=buffer_position(owned,k,base_y);row={entities={},renders={},product_id=material.product_id,location_id=material.location_id,ports={}}
      owned.production_buffers[k]=row
      local planned={};local stock=add(planned,'steel-chest',p.x,p.y)
      if build(surface,row,planned,occupied) then
        row.stock=stock.entity;row.renders[1]=draw(surface,{x=p.x,y=p.y-3},material.label..' | Shared supply buffer',vm.palette.ready)
        row.renders[2]=draw(surface,{x=p.x,y=p.y+3},'Stock allocation; order provenance unavailable',vm.palette.idle)
      else row.incomplete=true;destroy(row);row.entities={} end
    end
  end
  -- Reserve every machine footprint before routing so later orders cannot
  -- place their machines on an earlier order's belt.
  local pending={}
  for _,lane in ipairs(lanes) do if not owned.production[lane.mo_id] then
    for _,op in ipairs(lane.operations) do
      local p=position(owned,op,base_y)
      for x=p.x-8,p.x+3 do for y=p.y-1,p.y+1 do occupied[key(x,y)]={kind='entity'} end end
    end
    pending[#pending+1]=lane
  end end
  local blueprints={}
  for _,lane in ipairs(pending) do
    local planned,nodes,edges=plan_order(lane,view,owned,base_y,occupied)
    blueprints[lane.mo_id]={planned=planned,nodes=nodes,edges=edges}
  end
  for _,lane in ipairs(pending) do
    local row={entities={},renders={},machines={},inputs={},outputs={},belts={},nodes={},edges={},material_edges={},signature=fingerprint(lane,view,buffers),incomplete=true}
    owned.production[lane.mo_id]=row
    local available=true;for _,m in ipairs(lane.materials) do if not intact(owned.production_buffers[hub_key(m.product_id,m.location_id)]) then available=false end end
    local blueprint=blueprints[lane.mo_id]
    local planned,nodes,edges=blueprint.planned,blueprint.nodes,blueprint.edges
    local trial={};for k,v in pairs(occupied) do trial[k]=v end
    local routed,reason
    if available then routed,reason=route_order(planned,edges,trial) end
    row.reason=reason
    local built,obstruction
    if routed then built,obstruction=build(surface,row,planned,trial) end
    row.reason=obstruction or row.reason
    if built then
      occupied=trial
      row.incomplete=false;row.nodes=nodes;row.edges=edges
      for _,spec in ipairs(planned) do if spec.name:find('belt') then row.belts[#row.belts+1]=spec.entity end end
      for _,op in ipairs(lane.operations) do
        local node=nodes[op.id];local p=node.position
        node.entity=node.machine_spec.entity;node.entity.active=false
        node.entity.set_recipe('fc-process-'..(node.root and (node.output_name=='fc-complete' and 'raw-final' or 'raw') or (node.output_name=='fc-complete' and 'final' or 'work')))
        node.source=node.source_spec.entity;node.receipt=node.receipt_spec.entity
        node.todo_belts={};for _,spec in ipairs(node.todo_specs) do node.todo_belts[#node.todo_belts+1]=spec.entity end;node.todo_specs=nil
        node.feed=node.feed_spec.entity;node.input=node.input_spec.entity;node.output=node.output_spec.entity
        configure_inserter(node.feed,{x=p.x-8,y=p.y},{x=p.x-6,y=p.y})
        configure_inserter(node.input,{x=p.x-3,y=p.y},{x=p.x,y=p.y})
        configure_inserter(node.output,{x=p.x,y=p.y},{x=p.x+3,y=p.y})
        node.input.active=false
        if node.root then inventory(node.source).insert{name='fc-raw-material',count=lane.count} end
        node.label=draw(surface,{x=p.x,y=p.y-4},view.centers[op.center_id].display_name)
        node.timer=draw(surface,{x=p.x,y=p.y+4},(production.timing(op):gsub(' | ','\n')))
        row.renders[#row.renders+1]=node.label;row.renders[#row.renders+1]=node.timer
        node.order_label=draw(surface,{x=p.x,y=p.y-6},lane.order.reference..' | '..vm.number(lane.quantum)..' '..op.unit_label..'/marker')
        row.renders[#row.renders+1]=node.order_label
        row.machines[#row.machines+1]=node;row.inputs[#row.inputs+1]=node.input;row.outputs[#row.outputs+1]=node.output
      end
      for _,e in ipairs(edges) do
        e.source=e.source_spec.entity;e.complete=e.complete_spec.entity;e.feed=e.feed_spec.entity
        configure_inserter(e.feed,e.source.position,e.start)
        configure_inserter(e.finish_spec.entity,e.finish,e.complete.position)
        if e.material_id then row.material_edges[#row.material_edges+1]=e end
        local label=e.product_receipt and (lane.order.product..' | Operation receipts; posted stock is separate') or 'Dependency receipt'
        if e.material_id then
          for _,m in ipairs(lane.materials) do if m.id==e.material_id then label=m.label..' | '..vm.number(m.demand.demand_qty/lane.count)..' '..m.unit_label..'/allocation marker' end end
        end
        e.label=draw(surface,{x=e.source.position.x,y=e.source.position.y-2},label..' | '..lane.order.reference,vm.palette.ready)
        row.renders[#row.renders+1]=e.label
      end
      row.source=nodes[lane.roots[1]].source;row.feed=nodes[lane.roots[1]].feed;row.complete=nodes[lane.sinks[1]].receipt
      row.renders[#row.renders+1]=draw(surface,{x=row.source.position.x,y=row.source.position.y-3},'Production TODO',vm.palette.ready)
      row.renders[#row.renders+1]=draw(surface,{x=row.complete.position.x,y=row.complete.position.y+2},'Operation complete\nPosted stock is separate',vm.palette.running)
      -- Drop transient construction descriptions; persist only engine references
      -- and the counters required for save/load and dispatch.
      for _,node in pairs(nodes) do node.source_spec=nil;node.feed_spec=nil;node.machine_spec=nil;node.input_spec=nil;node.output_spec=nil;node.receipt_spec=nil end
      for _,e in ipairs(edges) do e.source_spec=nil;e.feed_spec=nil;e.complete_spec=nil;e.finish_spec=nil end
    else
      destroy(row);row.entities={};row.machines={};row.inputs={};row.outputs={};row.belts={}
    end
  end
  for _,lane in ipairs(lanes) do if owned.production[lane.mo_id].incomplete then warnings[#warnings+1]='Physical production network obstructed for '..lane.order.reference..' ('..(owned.production[lane.mo_id].reason or 'entity obstruction')..'); source details remain available.' end end
  return warnings
end
local function update_clocks(view,owned,tick)
  owned.production_clocks=owned.production_clocks or {}
  local healthy=view.sync.connected and view.sync.verified and not view.sync.stale and not view.sync.source_failed and view.sync.source_age_label~='Unknown'
  local seen={}
  for _,order in pairs(view.orders) do for _,op in ipairs(order.operations) do
    seen[op.id]=true
    local clock=owned.production_clocks[op.id] or {};owned.production_clocks[op.id]=clock
    production.observe(op,clock,tick,healthy)
  end end
  for k in pairs(owned.production_clocks) do if not seen[k] then owned.production_clocks[k]=nil end end
end
function M.update(view,owned,tick)
  view.production_positions={};local position_priority={};local priorities={progress=3,ready=2,blocked=1,done=0}
  update_clocks(view,owned,tick)
  for _,buffer in pairs(owned.production_buffers or {}) do if intact(buffer) then
    local quantity=0
    for _,stock in ipairs(view.stock[buffer.product_id] or {}) do if stock.location_id==buffer.location_id then quantity=stock.on_hand_qty end end
    local inv=inventory(buffer.stock);local wanted=math.min(200,math.max(0,math.ceil(quantity)))
    local current=inv.get_item_count('fc-raw-material')
    if wanted>current then inv.insert{name='fc-raw-material',count=wanted-current}
    elseif current>wanted then inv.remove{name='fc-raw-material',count=current-wanted} end
    buffer.renders[2].text='Posted stock '..vm.number(quantity)..' | '..wanted..' stock markers\nAllocations follow Odoo; operation receipts are separate'
  end end
  local lanes=production.plan(view)
  for _,lane in ipairs(lanes) do
    local row=owned.production and owned.production[lane.mo_id]
    if intact(row) then
      local material_byid={};for _,m in ipairs(lane.materials) do material_byid[m.id]=m end
      for _,edge in ipairs(row.material_edges) do
        local m=material_byid[edge.material_id];local budget=production.material_budget(m,lane.count)
        if budget>edge.dispatched then
          edge.dispatched=edge.dispatched+inventory(edge.source).insert{name=edge.name,count=budget-edge.dispatched}
        end
      end
      for _,op in ipairs(lane.operations) do
        local node=row.nodes[op.id];local priority=priorities[op.raw_state] or -1
        if position_priority[op.center_id]==nil or priority>position_priority[op.center_id] then
          position_priority[op.center_id]=priority;view.production_positions[op.center_id]={x=node.entity.position.x-5,y=node.entity.position.y}
        end
        node.feed.active=not lane.order.material_warning
        local budget=production.budget(op,lane.quantum,lane.count)
        node.input.active=op.raw_state=='progress' or budget>node.released
        if #node.incoming>0 then
          local count=lane.count-node.joined
          for _,edge in ipairs(node.incoming) do count=math.min(count,inventory(edge.complete).get_item_count(edge.name)) end
          if count>0 then
            local inserted=inventory(node.source).insert{name='fc-workpiece',count=count}
            for _,edge in ipairs(node.incoming) do inventory(edge.complete).remove{name=edge.name,count=inserted} end
            node.joined=node.joined+inserted
          end
        end
        local input=node.entity.get_inventory(defines.inventory.assembling_machine_input)
        local output=node.entity.get_inventory(defines.inventory.assembling_machine_output)
        local count=math.min(math.max(0,budget-node.released),input.get_item_count(node.input_name))
        for _,edge in ipairs(node.materials) do count=math.min(count,inventory(edge.complete).get_item_count(edge.name)) end
        if count>0 then
          local inserted=output.insert{name=node.output_name,count=count}
          input.remove{name=node.input_name,count=inserted}
          for _,edge in ipairs(node.materials) do inventory(edge.complete).remove{name=edge.name,count=inserted} end
          node.released=node.released+inserted
        end
        if #node.outgoing>0 then
          local inv=inventory(node.receipt);local ready=math.min(inv.get_item_count(node.output_name),node.released-node.dispatched)
          if ready>0 then
            -- A branch is a completion receipt for each dependency, not extra
            -- production. All route boxes have room for the bounded batch.
            for _,edge in ipairs(node.outgoing) do inventory(edge.source).insert{name=edge.name,count=ready} end
            if node.output_name~='fc-complete' then inv.remove{name=node.output_name,count=ready} end
            node.dispatched=node.dispatched+ready
          end
        end
        node.label.text=view.centers[op.center_id].display_name..' | WO '..string.format('%d',op.id)..' | '..op.state_label
        node.label.color=op.raw_state=='progress' and vm.palette.running or op.raw_state=='blocked' and vm.palette.attention or vm.palette.ready
        node.timer.text=op.running_label:gsub(' | ','\n')
        node.order_label.text=lane.order.reference..' | '..lane.order.product..' | '..vm.number(lane.quantum)..' '..op.unit_label..'/marker'
      end
    end
  end
end
function M.center_for_entity(owned,entity)
  for _,row in pairs(owned.production or {}) do
    for _,node in ipairs(row.machines or {}) do if node.entity==entity or node.source==entity or node.receipt==entity then return node.center_id end end
  end
end
return M
