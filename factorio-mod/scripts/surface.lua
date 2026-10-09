local vm=require('scripts.view_model')
local M={}
local kinds={MACH='machining',ASSY='assembly',INSP='inspection',PACK='packing'}
local function destroy(objects)
  for _,object in ipairs(objects or {}) do if object.valid then object.destroy() end end
end
local function remove(row)
  if row.entity and row.entity.valid then row.entity.destroy() end
  destroy(row.entities);destroy(row.renders)
end
function M.clear(owned)
  for _,row in pairs(owned.stations or {}) do remove(row) end
  for _,targets in pairs(owned.links or {}) do for _,row in pairs(targets) do remove(row) end end
  owned.stations={};owned.links={}
  -- Keep the owned surface itself and all untracked contents intact.
end
local function ensure(owned,warnings)
  if owned.surface and owned.surface.valid then return owned.surface end
  if game.surfaces['odoo-factory'] then
    warnings[#warnings+1]='Display unavailable: unowned surface named odoo-factory already exists. Manually resolve the name collision before creating the generated view.'
    return nil
  end
  owned.surface=game.create_surface('odoo-factory',{peaceful_mode=true,default_enable_all_autoplace_controls=false,
    autoplace_settings={entity={treat_missing_as_default=false},decorative={treat_missing_as_default=false},
      tile={treat_missing_as_default=false,settings={['grass-1']={frequency=1,size=1,richness=1}}}}})
  return owned.surface
end
local function protect(entity)
  entity.minable=false;entity.destructible=false;entity.rotatable=false
end
local function text(surface,target,value,color)
  return rendering.draw_text{surface=surface,target=target,text=value,color=color,alignment='center',scale=0.8,use_rich_text=false}
end
local function station_labels(center)
  return {{center.display_name,vm.palette.idle},{'Running '..center.running_count,vm.palette.running},
    {'Ready '..center.ready_count,vm.palette.ready},{'Dependency waiting '..center.waiting_count,vm.palette.attention},
    {'MO material warnings '..center.material_warning_count,vm.palette.attention},
    {'Center '..center.raw_state_label..' | raw '..vm.plain(center.raw_state),vm.palette.idle}}
end
function M.reconcile(view,slots,owned)
  local warnings={};local surface=ensure(owned,warnings)
  if not surface then return warnings end
  owned.stations=owned.stations or {};owned.links=owned.links or {}
  for center_id,row in pairs(owned.stations) do if not view.centers[center_id] then remove(row);owned.stations[center_id]=nil end end
  for _,center_id in ipairs(view.center_ids) do
    local center,slot=view.centers[center_id],slots[center_id]
    if slot then
      if surface.request_to_generate_chunks then surface.request_to_generate_chunks(slot.position,1) end
    end
  end
  if surface.force_generate_chunk_requests then surface.force_generate_chunk_requests() end
  for _,center_id in ipairs(view.center_ids) do
    local center,slot=view.centers[center_id],slots[center_id]
    local row=owned.stations[center_id]
    if row and not row.entity.valid then remove(row);owned.stations[center_id]=nil;row=nil end
    if not row and slot then
      local spec={name='fc-station-'..(kinds[center.code] or 'generic'),position=slot.position,force='player'}
      if surface.can_place_entity(spec) then
        local entity=surface.create_entity(spec)
        if entity then protect(entity);row={entity=entity,renders={}};owned.stations[center_id]=row end
      end
      if not row then warnings[#warnings+1]='Display obstructed for '..center.display_name..'; source data remains available.' end
    end
    if row then
      for i,label in ipairs(station_labels(center)) do
        local r=row.renders[i]
        if r and r.valid then r.text=label[1];r.color=label[2]
        else row.renders[i]=text(surface,{entity=row.entity,offset={x=0,y=-4+(i-1)*0.7}},label[1],label[2]) end
      end
    end
  end
  local wanted={}
  for _,link in ipairs(view.links) do wanted[link.from]=wanted[link.from] or {};wanted[link.from][link.to]=link end
  for from,targets in pairs(owned.links) do
    for to,row in pairs(targets) do if not wanted[from] or not wanted[from][to] then remove(row);targets[to]=nil end end
  end
  for n,link in ipairs(view.links) do
    local a,b=slots[link.from],slots[link.to]
    if a and b and owned.stations[link.from] and owned.stations[link.to] then
      owned.links[link.from]=owned.links[link.from] or {}
      local row=owned.links[link.from][link.to]
      local intact=row~=nil and not row.incomplete
      if row then for _,entity in ipairs(row.entities) do if not entity.valid then intact=false end end end
      if not intact then
        if row then remove(row) end
        row={entities={},renders={}};owned.links[link.from][link.to]=row
        local y=math.max(a.position.y,b.position.y)+8+n*2
        local points={}
        local function segment(x1,y1,x2,y2)
          local dx=x2==x1 and 0 or (x2>x1 and 1 or -1)
          local dy=y2==y1 and 0 or (y2>y1 and 1 or -1)
          local direction=dx>0 and defines.direction.east or dx<0 and defines.direction.west or dy>0 and defines.direction.south or defines.direction.north
          local x,y0=x1,y1
          while x~=x2 or y0~=y2 do points[#points+1]={position={x=x,y=y0},direction=direction};x=x+dx;y0=y0+dy end
        end
        local start_x,end_x=a.position.x+4,b.position.x-4
        segment(start_x,a.position.y+3,start_x,y)
        segment(start_x,y,end_x,y)
        segment(end_x,y,end_x,b.position.y+3)
        for _,point in ipairs(points) do
          local spec={name='transport-belt',position=point.position,direction=point.direction,force='player'}
          if surface.can_place_entity(spec) then
            local e=surface.create_entity(spec)
            if e then protect(e);e.operable=false;e.active=false;row.entities[#row.entities+1]=e end
          else row.incomplete=true;warnings[#warnings+1]='Workflow visual obstructed; '..link.label end
        end
        row.target={x=(a.position.x+b.position.x)/2,y=y+1}
      end
      local r=row.renders[1]
      if r and r.valid then r.text=link.label else row.renders[1]=text(surface,row.target,link.label,vm.palette.ready) end
    end
  end
  return warnings
end
function M.center_for_entity(owned,entity)
  if not entity or not entity.valid then return nil end
  for center_id,row in pairs(owned.stations or {}) do if row.entity==entity then return center_id end end
end
return M
