-- Static first frames of base assets: displays have no inventory or recipes.
local function picture(source)
  local animation=source.picture or source.graphics_set.animation
  local layers={}
  for _,layer in ipairs(animation.layers or {animation}) do
    local sprite={}
    for _,key in ipairs({'filename','width','height','shift','scale','draw_as_shadow','priority','tint'}) do sprite[key]=table.deepcopy(layer[key]) end
    layers[#layers+1]=sprite
  end
  return {layers=layers}
end
local sources={machining=data.raw.furnace['stone-furnace'],assembly=data.raw['assembling-machine']['assembling-machine-1'],
  inspection=data.raw['assembling-machine']['assembling-machine-2'],packing=data.raw.container['steel-chest'],generic=data.raw.container['iron-chest']}
for kind,source in pairs(sources) do
  data:extend({{type='simple-entity-with-owner',name='fc-station-'..kind,icon=source.icon,
    localised_name={'entity-name.fc-station-'..kind},flags={'placeable-neutral','player-creation','not-blueprintable','not-deconstructable'},
    max_health=1000,collision_box=table.deepcopy(source.collision_box),selection_box=table.deepcopy(source.selection_box),
    picture=picture(source),render_layer='object'}})
end
