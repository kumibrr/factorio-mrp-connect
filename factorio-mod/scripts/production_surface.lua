-- Compact native order flows with local dependency junctions and component kits.
local production=require('scripts.production')
local router=require('scripts.production_routing')
local layout=require('scripts.production_layout')
local vm=require('scripts.view_model')
local skins=require('scripts.skins')
local M={}
local kinds={MACH='machining',ASSY='assembly',INSP='inspection',PACK='packing'}
local function key(x,y) return x..':'..y end
local function id(value) return string.format('%d',value) end
local function machine_name(name)
  return name:find('^fc%-skin%-production%-') or (name:find('^fc%-production%-') and name~='fc-production-inserter')
end
local function belt_name(name)
  return name=='transport-belt' or name=='express-underground-belt'
end
local function inventory(entity)
  local kind=machine_name(entity.name) and defines.inventory.assembling_machine_input or defines.inventory.chest
  return entity.get_inventory(kind)
end
local function destroy(row)
  for _,entity in ipairs(row.entities or {}) do if entity.valid then entity.destroy() end end
  for _,object in ipairs(row.renders or {}) do if object.valid then object.destroy() end end
end
function M.clear(owned)
  for _,row in pairs(owned.production or {}) do destroy(row) end
  for _,row in pairs(owned.production_buffers or {}) do destroy(row) end
  owned.production={};owned.production_slots={};owned.production_clocks={};owned.production_base_y=nil
  owned.production_buffers={};owned.production_node_slots={};owned.production_center_slots={};owned.production_buffer_slots={}
  owned.production_cells={}
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
  local parts={'direct-belts-v3',vm.number(lane.quantity),string.format('%d',lane.order.product_id)}
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
  local radius=machine_name(spec.name) and 1 or 0
  for x=spec.position.x-radius,spec.position.x+radius do for y=spec.position.y-radius,spec.position.y+radius do
    occupied[key(x,y)]={kind=belt_name(spec.name) and 'belt' or 'entity',direction=spec.direction,type=spec.type}
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
local function position(owned,lane,op,base_y)
  local cell=owned.production_cells[lane.mo_id]
  if not cell or cell.height<lane.layout.height then
    local offset=0
    for _,other in pairs(owned.production_cells) do offset=math.max(offset,other.offset+other.height+16) end
    cell={offset=offset,height=lane.layout.height};owned.production_cells[lane.mo_id]=cell
  end
  local p=lane.layout.positions[op.id]
  return {x=p.x,y=base_y+cell.offset+p.y}
end
local function hub_key(product,location) return id(product)..':'..id(location) end
local function buffer_position(owned,k,base_y)
  if owned.production_buffer_slots[k]==nil then
    local index=0;for _,i in pairs(owned.production_buffer_slots) do index=math.max(index,i+1) end
    owned.production_buffer_slots[k]=index
  end
  return {x=-32,y=base_y+owned.production_buffer_slots[k]*12}
end
local function plan_order(lane,view,owned,base_y,occupied)
  local planned,nodes,edges={},{},{}
  local sinks={};for _,id in ipairs(lane.sinks) do sinks[id]=true end
  local successors,predecessors={},{}
  for _,e in ipairs(lane.edges) do
    successors[e.from]=successors[e.from] or {};successors[e.from][#successors[e.from]+1]=e.to
    predecessors[e.to]=predecessors[e.to] or {};predecessors[e.to][#predecessors[e.to]+1]=e.from
  end
  local function direct(from,to) return #(successors[from] or {})==1 and #(predecessors[to] or {})==1 end
  for _,op in ipairs(lane.operations) do
    local p=position(owned,lane,op,base_y);local node={op_id=op.id,center_id=op.center_id,position=p,incoming={},outgoing={},materials={},root=#op.dependency_ids==0,
      input_name=#op.dependency_ids==0 and 'fc-raw-material' or 'fc-workpiece',output_name=sinks[op.id] and 'fc-complete' or 'fc-workpiece',released=0,dispatched=0,joined=0}
    nodes[op.id]=node
    local parents,children=predecessors[op.id] or {},successors[op.id] or {}
    node.direct_input=#parents==1 and direct(parents[1],op.id)
    node.direct_output=#children==1 and direct(op.id,children[1])
    node.todo_specs={}
    if not node.direct_input then
      node.source_spec=add(planned,'steel-chest',p.x-8,p.y)
      node.feed_spec=add(planned,'fc-production-inserter',p.x-7,p.y,{direction=defines.direction.west})
      for x=p.x-6,p.x-3 do node.todo_specs[#node.todo_specs+1]=add(planned,'transport-belt',x,p.y,{direction=defines.direction.east}) end
    end
    node.input_spec=add(planned,'fc-production-inserter',p.x-2,p.y,{direction=defines.direction.west})
    node.machine_spec=add(planned,skins.name(owned,'production',op.id,'fc-production-'..(kinds[view.centers[op.center_id].code] or 'generic')),p.x,p.y)
    node.output_spec=add(planned,'fc-production-inserter',p.x+2,p.y,{direction=defines.direction.west})
    if not node.direct_output then node.receipt_spec=add(planned,'steel-chest',p.x+3,p.y) end
  end
  local function edge(from,to,materials,hub)
    local node=to and nodes[to];local source_pos
    if from and to and direct(from,to) then
      local parent=nodes[from]
      local e={from=from,to=to,direct=true,name='fc-workpiece',
        start={x=parent.position.x+3,y=parent.position.y},finish={x=node.position.x-3,y=node.position.y}}
      edges[#edges+1]=e;parent.outgoing[#parent.outgoing+1]=e;node.incoming[#node.incoming+1]=e
      return
    end
    if hub then
      local parent=nodes[from]
      local e={from=from,hub=hub,product_receipt=true,local_supply=true,name='fc-complete',dispatched=0,belts={}}
      edges[#edges+1]=e;parent.outgoing[#parent.outgoing+1]=e
      return
    end
    if from then
      local parent=nodes[from]
      source_pos={x=parent.position.x+6,y=parent.position.y+8+#parent.outgoing*4}
    else
      source_pos={x=node.position.x-8,y=node.position.y-3}
    end
    local target_pos
    target_pos={x=node.position.x-8,y=node.position.y+8+(#node.incoming+#node.materials)*4}
    local e={from=from,to=to,hub=hub,dispatched=0,materials=materials,
      product_receipt=hub and not materials or false,name=materials and 'fc-component-kit' or (hub and 'fc-complete' or 'fc-workpiece')}
    e.source_spec=add(planned,'steel-chest',source_pos.x,source_pos.y)
    e.feed_spec=add(planned,'fc-production-inserter',source_pos.x+1,source_pos.y,{direction=defines.direction.west})
    if materials then
      e.material_ids={};for _,m in ipairs(materials) do e.material_ids[#e.material_ids+1]=m.id end
      e.complete_spec=node.machine_spec
      e.finish_spec=add(planned,'fc-production-inserter',node.position.x,node.position.y-2,{direction=defines.direction.north})
      e.finish={x=node.position.x,y=node.position.y-3}
    else
      e.complete_spec=add(planned,'steel-chest',target_pos.x,target_pos.y)
      e.finish_spec=add(planned,'fc-production-inserter',target_pos.x-1,target_pos.y,{direction=defines.direction.west})
      e.finish={x=target_pos.x-2,y=target_pos.y}
    end
    e.start={x=source_pos.x+2,y=source_pos.y}
    edges[#edges+1]=e
    if from then
      nodes[from].outgoing[#nodes[from].outgoing+1]=e
      if node then node.incoming[#node.incoming+1]=e end
    else node.materials[#node.materials+1]=e end
  end
  for _,e in ipairs(lane.edges) do edge(e.from,e.to) end
  local groups={}
  for _,m in ipairs(lane.materials) do groups[m.to]=groups[m.to] or {};groups[m.to][#groups[m.to]+1]=m end
  for _,op in ipairs(lane.operations) do if groups[op.id] then edge(nil,op.id,groups[op.id]) end end
  local destinations={}
  for k,buffer in pairs(owned.production_buffers) do
    if buffer.product_id==lane.order.product_id then destinations[#destinations+1]=k end
  end
  -- The snapshot has no stock-move destination for finished output. Only a
  -- single destination product area can be connected without inventing a split.
  if #destinations==1 then for _,id in ipairs(lane.sinks) do edge(id,nil,nil,destinations[1]) end end
  for _,spec in ipairs(planned) do reserve(occupied,spec) end
  for _,e in ipairs(edges) do
    for _,p in ipairs(e.local_supply and {} or {e.start,e.finish}) do
      for x=p.x-1,p.x+1 do for y=p.y-1,p.y+1 do
        if not occupied[key(x,y)] then occupied[key(x,y)]={kind='port',owner=e} end
      end end
    end
  end
  return planned,nodes,edges
end
local function route_order(planned,edges,occupied)
  for _,e in ipairs(edges) do
    if not e.local_supply then
    for _,p in ipairs({e.start,e.finish}) do
      for x=p.x-1,p.x+1 do for y=p.y-1,p.y+1 do
        local entry=occupied[key(x,y)]
        if entry and entry.owner==e then occupied[key(x,y)]=nil end
      end end
    end
    local path,reason=router.route(e.start,e.finish,occupied)
    if not path then return false,reason..' '..e.start.x..','..e.start.y..' -> '..e.finish.x..','..e.finish.y end
    e.belt_specs=path
    for _,spec in ipairs(path) do
      spec.force='player';planned[#planned+1]=spec;reserve(occupied,spec)
    end
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
  owned.production_cells=owned.production_cells or {}
  local lanes,warnings=production.plan(view);local wanted={};local next_index=0
  owned.production_base_y=owned.production_base_y or base_y or 40;base_y=owned.production_base_y
  for _,index in pairs(owned.production_slots) do next_index=math.max(next_index,index+1) end
  local buffers={}
  for _,lane in ipairs(lanes) do
    lane.layout=layout.plan(lane)
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
  for _,row in pairs(owned.production) do for _,e in ipairs(row.entities) do reserve(occupied,{name=e.name,position=e.position,direction=e.direction,type=e.name=='express-underground-belt' and e.belt_to_ground_type or nil}) end end
  for _,row in pairs(owned.production_buffers) do for _,e in ipairs(row.entities) do reserve(occupied,{name=e.name,position=e.position,direction=e.direction,type=e.name=='express-underground-belt' and e.belt_to_ground_type or nil}) end end
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
  -- Plan and reserve actual entities for every order before routing. Empty
  -- space formerly occupied by serial boxes remains available to direct belts.
  local pending={}
  for _,lane in ipairs(lanes) do if not owned.production[lane.mo_id] then
    pending[#pending+1]=lane
  end end
  local blueprints={}
  for _,lane in ipairs(pending) do
    local planned,nodes,edges=plan_order(lane,view,owned,base_y,occupied)
    blueprints[lane.mo_id]={planned=planned,nodes=nodes,edges=edges}
  end
  for _,lane in ipairs(pending) do
    local row={entities={},renders={},machines={},inputs={},outputs={},belts={},nodes={},edges={},material_edges={},material_feeds={},signature=fingerprint(lane,view,buffers),incomplete=true}
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
      for _,spec in ipairs(planned) do if belt_name(spec.name) then row.belts[#row.belts+1]=spec.entity end end
      for _,op in ipairs(lane.operations) do
        local node=nodes[op.id];local p=node.position
        node.entity=node.machine_spec.entity;node.entity.active=false
        node.entity.set_recipe('fc-process-'..(node.root and (node.output_name=='fc-complete' and 'raw-final' or 'raw') or (node.output_name=='fc-complete' and 'final' or 'work'))..(#node.materials>0 and '-kit' or ''))
        node.source=node.source_spec and node.source_spec.entity;node.receipt=node.receipt_spec and node.receipt_spec.entity
        node.todo_belts={};for _,spec in ipairs(node.todo_specs) do node.todo_belts[#node.todo_belts+1]=spec.entity end;node.todo_specs=nil
        node.feed=node.feed_spec and node.feed_spec.entity;node.input=node.input_spec.entity;node.output=node.output_spec.entity
        if node.feed then configure_inserter(node.feed,{x=p.x-8,y=p.y},{x=p.x-6,y=p.y}) end
        configure_inserter(node.input,{x=p.x-3,y=p.y},{x=p.x,y=p.y})
        configure_inserter(node.output,{x=p.x,y=p.y},{x=p.x+3,y=p.y})
        node.input.active=false
        if node.root then inventory(node.source).insert{name='fc-raw-material',count=lane.count} end
        node.label=draw(surface,{x=p.x,y=p.y-4},view.centers[op.center_id].display_name)
        node.timer=draw(surface,{x=p.x,y=p.y+4},'Output 0 / '..lane.count)
        row.renders[#row.renders+1]=node.label;row.renders[#row.renders+1]=node.timer
        node.order_label=draw(surface,{x=p.x,y=p.y-6},lane.order.reference..' | '..vm.number(lane.quantum)..' '..op.unit_label..'/marker')
        row.renders[#row.renders+1]=node.order_label
        row.machines[#row.machines+1]=node;row.inputs[#row.inputs+1]=node.input;row.outputs[#row.outputs+1]=node.output
      end
      for _,e in ipairs(edges) do
        if e.local_supply then
          e.complete=nodes[e.from].receipt
        elseif e.direct then
          e.belts={};for _,spec in ipairs(e.belt_specs) do e.belts[#e.belts+1]=spec.entity end
          nodes[e.to].todo_belts=e.belts;e.belt_specs=nil
        else
        e.source=e.source_spec.entity;e.complete=e.complete_spec.entity;e.feed=e.feed_spec.entity
        configure_inserter(e.feed,e.source.position,e.start)
        configure_inserter(e.finish_spec.entity,e.finish,e.complete.position)
        e.finish_inserter=e.finish_spec.entity;e.belts={}
        for _,spec in ipairs(e.belt_specs) do e.belts[#e.belts+1]=spec.entity end
        e.belt_specs=nil
        if e.material_ids then
          row.material_feeds[#row.material_feeds+1]=e;e.allocations={}
          for _,m in ipairs(e.materials) do
            local allocation={material_id=m.id,hub=hub_key(m.product_id,m.location_id),dispatched=0,
              source=e.source,complete=e.complete,name=e.name}
            e.allocations[#e.allocations+1]=allocation;row.material_edges[#row.material_edges+1]=allocation
          end
          e.materials=nil
          e.label=draw(surface,{x=e.source.position.x,y=e.source.position.y-2},'Components × '..#e.material_ids,vm.palette.ready)
          row.renders[#row.renders+1]=e.label
        end
        end
      end
      row.source=nodes[lane.roots[1]].source;row.feed=nodes[lane.roots[1]].feed;row.complete=nodes[lane.sinks[1]].receipt
      row.renders[#row.renders+1]=draw(surface,{x=row.source.position.x,y=row.source.position.y-3},'Input',vm.palette.ready)
      row.renders[#row.renders+1]=draw(surface,{x=row.complete.position.x,y=row.complete.position.y+2},'Complete',vm.palette.running)
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
      for _,feed in ipairs(row.material_feeds or {}) do
        local budget=lane.count
        for _,material_id in ipairs(feed.material_ids) do budget=math.min(budget,production.material_budget(material_byid[material_id],lane.count)) end
        if budget>feed.dispatched then
          feed.dispatched=feed.dispatched+inventory(feed.source).insert{name=feed.name,count=budget-feed.dispatched}
        end
        for _,allocation in ipairs(feed.allocations) do allocation.dispatched=feed.dispatched end
      end
      for _,op in ipairs(lane.operations) do
        local node=row.nodes[op.id];local priority=priorities[op.raw_state] or -1
        if position_priority[op.center_id]==nil or priority>position_priority[op.center_id] then
          position_priority[op.center_id]=priority;view.production_positions[op.center_id]={x=node.entity.position.x-5,y=node.entity.position.y}
        end
        if node.feed then node.feed.active=not lane.order.material_warning end
        local budget=production.budget(op,lane.quantum,lane.count)
        node.input.active=op.raw_state=='progress' or budget>node.released
        for _,feed in ipairs(node.materials) do feed.finish_inserter.active=node.input.active end
        if #node.incoming>0 and not node.direct_input then
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
        if #node.outgoing>0 and not node.direct_output and not node.outgoing[1].local_supply then
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
        node.timer.text='Output '..node.released..' / '..lane.count
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
function M.machine_for_entity(owned,entity)
  for mo_id,row in pairs(owned.production or {}) do
    for _,machine in ipairs(row.machines or {}) do
      if machine.entity==entity then return {center_id=machine.center_id,mo_id=mo_id,op_id=machine.op_id} end
    end
  end
end
function M.machine(owned,ref)
  local lane=owned.production and owned.production[ref.mo_id]
  for _,machine in ipairs(lane and lane.machines or {}) do
    if machine.op_id==ref.op_id and machine.center_id==ref.center_id then return machine,lane end
  end
end
function M.set_skin(owned,ref,name)
  local machine,lane=M.machine(owned,ref)
  if not machine then return false,'This machine is no longer available.' end
  local original=machine.entity
  local ok,err=skins.replace(machine,name,true)
  if ok then
    for i,entity in ipairs(lane.entities) do if entity==original then lane.entities[i]=machine.entity;break end end
    for _,feed in ipairs(machine.materials or {}) do
      feed.complete=machine.entity
      for _,allocation in ipairs(feed.allocations or {}) do allocation.complete=machine.entity end
    end
  end
  return ok,err
end
return M
