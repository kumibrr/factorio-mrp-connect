local vm=require('scripts.view_model')
local production=require('scripts.production_surface')
local skins=require('scripts.skins')
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
  production.clear(owned)
  for _,row in pairs(owned.stations or {}) do remove(row) end
  for _,targets in pairs(owned.links or {}) do for _,row in pairs(targets) do remove(row) end end
  owned.stations={};owned.links={};owned.machine_skins=nil
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
      local spec={name=skins.name(owned,'station',center_id,'fc-station-'..(kinds[center.code] or 'generic')),position=slot.position,force='player'}
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
  -- Production already shows actual dependencies. Retire the duplicate,
  -- inactive work-center belt web from older saves.
  for _,targets in pairs(owned.links) do for _,row in pairs(targets) do remove(row) end end
  owned.links={}
  local base_y=40
  for _,slot in pairs(slots) do base_y=math.max(base_y,slot.position.y+40) end
  for _,warning in ipairs(production.reconcile(view,owned,base_y)) do warnings[#warnings+1]=warning end
  return warnings
end
function M.update(view,owned,tick) production.update(view,owned,tick) end
function M.center_for_entity(owned,entity)
  if not entity or not entity.valid then return nil end
  for center_id,row in pairs(owned.stations or {}) do if row.entity==entity then return center_id end end
  return production.center_for_entity(owned,entity)
end
function M.machine_for_entity(owned,entity)
  if not entity or not entity.valid then return nil end
  for center_id,row in pairs(owned.stations or {}) do if row.entity==entity then return {center_id=center_id} end end
  return production.machine_for_entity(owned,entity)
end
function M.machine(owned,ref)
  if ref.op_id then return production.machine(owned,ref) end
  return owned.stations and owned.stations[ref.center_id]
end
function M.set_skin(view,owned,ref,skin)
  local center=view.centers[ref.center_id]
  if not center then return false,'This work center is no longer available.' end
  local role=ref.op_id and 'production' or 'station'
  local default='fc-'..role..'-'..(kinds[center.code] or 'generic')
  local name=skin and skins.prototype(role,skin,default) or default
  if skin and not prototypes.entity[name] then return false,'This appearance is not available from the installed mods.' end
  local ok,err
  if ref.op_id then ok,err=production.set_skin(owned,ref,name)
  else
    local row=M.machine(owned,ref)
    if not row then return false,'This machine is no longer available.' end
    ok,err=skins.replace(row,name,false,function(entity)
      -- Entity-targeted renders are destroyed with their target. Reattach them
      -- before removing the old station, preserving their handles across saves.
      for i,render in ipairs(row.renders) do
        if render.valid then render.target={entity=entity,offset={x=0,y=-4+(i-1)*0.7}} end
      end
    end)
  end
  if ok then skins.saved(owned,role)[ref.op_id or ref.center_id]=skin end
  return ok,err
end
return M
