-- Static appearances on our own fixed-footprint machines: never import recipes,
-- power requirements, fluid connections, inventories or behavior from a skin.
local types={'assembling-machine','furnace','mining-drill','lab','beacon','boiler','generator',
  'reactor','rocket-silo','pump','offshore-pump','radar','solar-panel','accumulator',
  'container','logistic-container','electric-energy-interface','electric-pole',
  'agricultural-tower','fusion-generator','fusion-reactor','thruster'}
local sprite_keys={'filename','width','height','x','y','shift','scale','draw_as_shadow',
  'draw_as_light','draw_as_glow','priority','tint','blend_mode','flags','apply_runtime_tint',
  'premul_alpha','load_in_minimal_mode','allow_forced_downscale','dice','dice_x','dice_y'}
local function first_frame(value,factor)
  if type(value)~='table' then return nil end
  for _,key in ipairs({'north','structure','sheet'}) do
    if value[key] then return first_frame(value[key],factor) end
  end
  if value.layers or value.sheets then
    local layers={}
    for _,layer in ipairs(value.layers or value.sheets) do
      local sprite=first_frame(layer,factor)
      if not sprite then return nil end
      layers[#layers+1]=sprite
    end
    return #layers>0 and {layers=layers} or nil
  end
  if value[1] then return first_frame(value[1],factor) end
  local filename=value.filename or (value.filenames and value.filenames[1])
    or (value.stripes and value.stripes[1] and value.stripes[1].filename)
  local width,height=value.width,value.height
  if type(value.size)=='number' then width=width or value.size;height=height or value.size
  elseif type(value.size)=='table' then
    width=width or value.size[1] or value.size.x;height=height or value.size[2] or value.size.y
  end
  if not filename or not width or not height then return nil end
  local sprite={}
  for _,key in ipairs(sprite_keys) do sprite[key]=table.deepcopy(value[key]) end
  sprite.filename=filename;sprite.width=width;sprite.height=height;sprite.scale=(value.scale or 1)*factor
  if value.stripes then
    sprite.x=value.stripes[1].x or sprite.x;sprite.y=value.stripes[1].y or sprite.y
  end
  if sprite.shift then
    sprite.shift={(sprite.shift.x or sprite.shift[1] or 0)*factor,(sprite.shift.y or sprite.shift[2] or 0)*factor}
  end
  return sprite
end
local function appearance(source,limit)
  local box=source.selection_box or source.collision_box
  local factor=1
  if box then
    local a,b=box[1],box[2]
    local width=(b.x or b[1])-(a.x or a[1]);local height=(b.y or b[2])-(a.y or a[2])
    factor=math.min(1,limit/math.max(width,height,1))
  end
  local graphics=source.graphics_set or {}
  local north=graphics.north_graphics_set or {}
  local candidates={graphics.animation,graphics.idle_animation,graphics.picture,source.picture,source.pictures,
    source.animation,source.animations,source.off_animation,source.on_animation,source.idle_animation,
    source.base_picture,source.base_day_sprite,source.vertical_animation,source.horizontal_animation,
    graphics.base_animation,source.structure,graphics.structure,north.animation}
  -- Candidates may contain holes; pairs/ipairs would lose or reorder them.
  for i=1,18 do
    local sprite=first_frame(candidates[i],factor)
    if sprite then return sprite end
  end
  if graphics.animation_list then
    local layers={}
    for _,row in ipairs(graphics.animation_list) do
      local sprite=first_frame(row.animation,factor)
      if sprite then layers[#layers+1]=sprite end
    end
    if #layers>0 then return {layers=layers} end
  end
end
local generated={}
local templates={production=data.raw['assembling-machine']['fc-production-generic']}
for name,station in pairs(data.raw['simple-entity-with-owner']) do
  if name:sub(1,11)=='fc-station-' then templates['station-'..name:sub(12)]=station end
end
for _,kind in ipairs(types) do
  for name,source in pairs(data.raw[kind] or {}) do
    if name:sub(1,3)~='fc-' and not source.hidden then
      for role,template in pairs(templates) do
        local box=template.selection_box
        local limit=box and math.min((box[2].x or box[2][1])-(box[1].x or box[1][1]),
          (box[2].y or box[2][2])-(box[1].y or box[1][2])) or 3
        local sprite=appearance(source,limit)
        if sprite then
          local entity=table.deepcopy(template)
          entity.name='fc-skin-'..role..'-'..name
          entity.localised_name=source.localised_name or {'entity-name.'..name}
          entity.icon=source.icon;entity.icons=table.deepcopy(source.icons);entity.icon_size=source.icon_size
          entity.hidden=true;entity.hidden_in_factoriopedia=true
          if role=='production' then
            entity.graphics_set={animation=table.deepcopy(sprite)};entity.graphics_set_flipped=nil
          else entity.picture=table.deepcopy(sprite) end
          generated[#generated+1]=entity
        end
      end
    end
  end
end
data:extend(generated)
