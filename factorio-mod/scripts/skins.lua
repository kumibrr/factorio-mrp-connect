local M={}
function M.choices()
  local names={};local prefix='fc-skin-production-'
  for name in pairs(prototypes.entity) do
    if name:sub(1,#prefix)==prefix then names[#names+1]=name:sub(#prefix+1) end
  end
  table.sort(names)
  return names
end
function M.prototype(role,skin,default)
  local variant=role=='station' and ('station-'..default:sub(12)) or role
  return 'fc-skin-'..variant..'-'..skin
end
function M.saved(owned,role)
  owned.machine_skins=owned.machine_skins or {station={},production={}}
  return owned.machine_skins[role]
end
function M.name(owned,role,id,default)
  local choices=M.saved(owned,role);local skin=choices[id]
  if skin then
    local name=M.prototype(role,skin,default)
    if prototypes.entity[name] then return name end
  end
  choices[id]=nil
  return default
end
function M.replace(row,name,inventory,retarget)
  local old=row.entity
  if not old or not old.valid then return false,'This machine is no longer available.' end
  if old.name==name then return true end
  local replacement=old.surface.create_entity{name=name,position=old.position,force=old.force,direction=old.direction,
    quality=old.quality,create_build_effect_smoke=false,preserve_ghosts_and_corpses=true}
  if not replacement then return false,'Unable to apply this appearance.' end
  replacement.minable=false;replacement.destructible=false;replacement.rotatable=false;replacement.operable=false
  if inventory then
    replacement.active=false
    local recipe,quality=old.get_recipe()
    if recipe then replacement.set_recipe(recipe.name,quality and quality.name) end
    for _,kind in ipairs({defines.inventory.assembling_machine_input,defines.inventory.assembling_machine_output}) do
      local source,target=old.get_inventory(kind),replacement.get_inventory(kind)
      for _,stack in ipairs(source.get_contents()) do
        if target.insert(stack)~=stack.count then
          replacement.destroy();return false,'Unable to preserve this machine’s contents; appearance unchanged.'
        end
      end
    end
    replacement.crafting_progress=old.crafting_progress
    replacement.bonus_progress=old.bonus_progress
  end
  if old.health then replacement.health=old.health end
  if retarget then retarget(replacement) end
  row.entity=replacement;old.destroy()
  return true
end
return M
