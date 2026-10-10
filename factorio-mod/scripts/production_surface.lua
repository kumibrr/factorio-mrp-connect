-- Owned physical lanes. Only accepted source output can cross a machine.
local production=require('scripts.production')
local vm=require('scripts.view_model')
local M={}
local kinds={MACH='machining',ASSY='assembly',INSP='inspection',PACK='packing'}
local function destroy(row)
  for _,entity in ipairs(row.entities or {}) do if entity.valid then entity.destroy() end end
  for _,object in ipairs(row.renders or {}) do if object.valid then object.destroy() end end
end
function M.clear(owned)
  for _,row in pairs(owned.production or {}) do destroy(row) end
  owned.production={};owned.production_slots={};owned.production_clocks={};owned.production_base_y=nil
end
local function draw(surface,position,value,color)
  return rendering.draw_text{surface=surface,target=position,text=value,color=color or vm.palette.idle,
    alignment='center',scale=0.75,use_rich_text=false}
end
local function fingerprint(lane,view,base_y)
  local parts={vm.number(lane.quantity),vm.number(base_y)}
  for _,op in ipairs(lane.operations) do
    parts[#parts+1]=string.format('%d/%d/',op.id,op.center_id)..(kinds[view.centers[op.center_id].code] or 'generic')
  end
  return table.concat(parts,':')
end
local function specs(lane,view,y)
  local out={}
  local function add(role,name,x,extra)
    local spec={name=name,position={x=x,y=y},force='player'}
    if extra then for k,v in pairs(extra) do spec[k]=v end end
    out[#out+1]={role=role,spec=spec}
  end
  local function belt(x1,x2)
    for x=x1,x2 do add('belt','transport-belt',x,{direction=defines.direction.east}) end
  end
  local function inserter(role,x,pick,drop)
    add(role,'fc-production-inserter',x,{direction=defines.direction.west})
    out[#out].pickup={x=pick,y=y};out[#out].drop={x=drop,y=y}
  end
  add('source','steel-chest',-8)
  inserter('feed',-7,-8,-6);belt(-6,-3)
  for i,op in ipairs(lane.operations) do
    local x=(i-1)*16
    inserter('input',x-2,x-3,x)
    add('machine','fc-production-'..(kinds[view.centers[op.center_id].code] or 'generic'),x)
    out[#out].operation=op;out[#out].index=i
    out[#out].recipe='fc-process-'..(i==1 and (i==#lane.operations and 'raw-final' or 'raw') or (i==#lane.operations and 'final' or 'work'))
    inserter('output',x+2,x,x+3)
    belt(x+3,i<#lane.operations and x+13 or x+6)
  end
  local last_x=(#lane.operations-1)*16
  inserter('finish',last_x+7,last_x+6,last_x+8)
  add('complete','steel-chest',last_x+8)
  return out
end
local function intact(row)
  if not row or row.incomplete then return false end
  for _,entity in ipairs(row.entities) do if not entity.valid then return false end end
  return true
end
function M.reconcile(view,owned,base_y)
  if not owned.surface or not owned.surface.valid then return {} end
  local surface=owned.surface
  owned.production=owned.production or {};owned.production_slots=owned.production_slots or {}
  local lanes,warnings=production.plan(view);local wanted={};local next_index=0
  if #lanes>0 then owned.production_base_y=owned.production_base_y or base_y or 40 end
  base_y=owned.production_base_y or base_y or 40
  for _,index in pairs(owned.production_slots) do next_index=math.max(next_index,index+1) end
  for _,lane in ipairs(lanes) do wanted[lane.mo_id]=true end
  for key,row in pairs(owned.production) do if not wanted[key] then destroy(row);owned.production[key]=nil end end
  for _,lane in ipairs(lanes) do
    local key=lane.mo_id
    if owned.production_slots[key]==nil then owned.production_slots[key]=next_index;next_index=next_index+1 end
    local y=(base_y or 40)+owned.production_slots[key]*14
    local signature=fingerprint(lane,view,base_y or 40)
    local row=owned.production[key]
    local corrected=false
    if intact(row) then
      for i,op in ipairs(lane.operations) do
        if row.machines[i] and row.machines[i].released>production.budget(op,lane.quantum,lane.count) then corrected=true;break end
      end
    end
    if not intact(row) or row.signature~=signature or corrected then
      if row then destroy(row) end
      row={entities={},renders={},machines={},inputs={},outputs={},belts={},signature=signature,incomplete=true}
      owned.production[key]=row
      local planned=specs(lane,view,y)
      if surface.request_to_generate_chunks then
        for _,entry in ipairs(planned) do surface.request_to_generate_chunks(entry.spec.position,1) end
        surface.force_generate_chunk_requests()
      end
      local obstructed=false
      for _,entry in ipairs(planned) do if not surface.can_place_entity(entry.spec) then obstructed=true;break end end
      if not obstructed then
        for _,entry in ipairs(planned) do
          local entity=surface.create_entity(entry.spec)
          if not entity then obstructed=true;break end
          entity.minable=false;entity.destructible=false;entity.rotatable=false;entity.operable=false
          row.entities[#row.entities+1]=entity
          if entry.pickup then
            entity.pickup_position=entry.pickup;entity.drop_position=entry.drop;entity.inserter_stack_size_override=1
          end
          if entry.role=='machine' then
            entity.set_recipe(entry.recipe);entity.active=false
            row.machines[#row.machines+1]={entity=entity,released=0,op_id=entry.operation.id,center_id=entry.operation.center_id,
              input_name=entry.index==1 and 'fc-raw-material' or 'fc-workpiece',
              output_name=entry.index==#lane.operations and 'fc-complete' or 'fc-workpiece'}
          elseif entry.role=='input' then row.inputs[#row.inputs+1]=entity;entity.active=false
          elseif entry.role=='output' then row.outputs[#row.outputs+1]=entity
          elseif entry.role=='belt' then row.belts[#row.belts+1]=entity
          else row[entry.role]=entity end
        end
      end
      if obstructed then
        destroy(row);row.entities={};row.machines={};row.inputs={};row.outputs={}
      else
        row.incomplete=false
        row.source.get_inventory(defines.inventory.chest).insert{name='fc-raw-material',count=lane.count}
        row.renders[1]=draw(surface,{x=16,y=y-6},lane.order.reference..' — '..lane.order.product)
        row.renders[2]=draw(surface,{x=-8,y=y+2},'Raw materials',vm.palette.ready)
        row.renders[3]=draw(surface,{x=-4,y=y-2},'Production TODO',vm.palette.ready)
        row.renders[4]=draw(surface,{x=(#lane.operations-1)*16+8,y=y+2},'Production complete\nOperation output\nPosted stock is separate',vm.palette.running)
        row.renders[5]=draw(surface,{x=16,y=y-5},vm.number(lane.quantity)..' '..lane.operations[1].unit_label..' | '..lane.count..' markers | '..vm.number(lane.quantum)..' '..lane.operations[1].unit_label..' per marker',vm.palette.ready)
        for i,op in ipairs(lane.operations) do
          row.machines[i].label=draw(surface,{x=(i-1)*16,y=y-3},view.centers[op.center_id].display_name)
          row.renders[#row.renders+1]=row.machines[i].label
          row.machines[i].timer=draw(surface,{x=(i-1)*16,y=y+3},(production.timing(op):gsub(' | ','\n')))
          row.renders[#row.renders+1]=row.machines[i].timer
        end
      end
    end
    if row.incomplete then warnings[#warnings+1]='Physical production lane obstructed for '..lane.order.reference..'; source details remain available.' end
  end
  return warnings
end
function M.update(view,owned,tick)
  view.production_positions={}
  local position_priority={};local priorities={progress=3,ready=2,blocked=1,done=0}
  owned.production_clocks=owned.production_clocks or {}
  local healthy=view.sync.connected and view.sync.verified and not view.sync.stale and not view.sync.source_failed
    and view.sync.source_age_label~='Unknown'
  local seen={}
  for _,order in pairs(view.orders) do for _,op in ipairs(order.operations) do
    seen[op.id]=true
    local clock=owned.production_clocks[op.id] or {};owned.production_clocks[op.id]=clock
    production.observe(op,clock,tick,healthy)
  end end
  for key in pairs(owned.production_clocks) do if not seen[key] then owned.production_clocks[key]=nil end end
  local lanes=production.plan(view)
  for _,lane in ipairs(lanes) do
    local row=owned.production and owned.production[lane.mo_id]
    if intact(row) then
      row.feed.active=not lane.order.material_warning
      row.renders[1].text=lane.order.reference..' — '..lane.order.product..' | '..lane.order.state_label
      local staged=row.source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material')
      local completed=row.complete.get_inventory(defines.inventory.chest).get_item_count('fc-complete')
      row.renders[2].text='Raw materials\n'..vm.number(staged)..' markers staged'..(lane.order.material_warning and '\nWaiting for availability' or '')
      row.renders[4].text='Production complete\n'..vm.number(completed)..' markers\nPosted stock is separate'
      for i,op in ipairs(lane.operations) do
        local machine=row.machines[i]
        local priority=priorities[op.raw_state] or -1
        if position_priority[op.center_id]==nil or priority>position_priority[op.center_id] then
          position_priority[op.center_id]=priority
          view.production_positions[op.center_id]={x=machine.entity.position.x-5,y=machine.entity.position.y}
        end
        local budget=production.budget(op,lane.quantum,lane.count)
        -- Ready work waits on the belt; done work may replay accepted output.
        row.inputs[i].active=op.raw_state=='progress' or budget>machine.released
        machine.entity.active=false
        local input=machine.entity.get_inventory(defines.inventory.assembling_machine_input)
        local output=machine.entity.get_inventory(defines.inventory.assembling_machine_output)
        local count=math.min(math.max(0,budget-machine.released),input.get_item_count(machine.input_name))
        if count>0 then
          local inserted=output.insert{name=machine.output_name,count=count}
          input.remove{name=machine.input_name,count=inserted};machine.released=machine.released+inserted
        end
        if machine.label.valid then
          machine.label.text=view.centers[op.center_id].display_name..' | WO '..string.format('%d',op.id)..' | '..op.state_label
          machine.label.color=op.raw_state=='progress' and vm.palette.running or op.raw_state=='blocked' and vm.palette.attention or vm.palette.ready
        end
        if machine.timer.valid then machine.timer.text=op.running_label:gsub(' | ','\n') end
      end
    end
  end
end
function M.center_for_entity(owned,entity)
  for _,row in pairs(owned.production or {}) do
    local machines=row.machines or {}
    if row.source==entity and machines[1] then return machines[1].center_id end
    if row.complete==entity and machines[#machines] then return machines[#machines].center_id end
    for _,machine in ipairs(machines) do if machine.entity==entity then return machine.center_id end end
  end
end
return M
