local f=require('fixtures')
return {
  catalog_imports_modded_graphics_without_importing_machine_behavior=function()
    local previous_data,deepcopy=data,table.deepcopy
    table.deepcopy=f.copy
    local sprite={filename='modded-machine.png',width=200,height=100,scale=0.5,shift={1,2},frame_count=12}
    data={raw={
      ['assembling-machine']={
        ['fc-production-generic']={type='assembling-machine',name='fc-production-generic',crafting_categories={'fc-production'},
          energy_source={type='void'},collision_box={{-1.2,-1.2},{1.2,1.2}},graphics_set={animation=sprite}},
        ['modded-smelter']={type='assembling-machine',name='modded-smelter',icon='modded-icon.png',icon_size=64,
          selection_box={{-3,-3},{3,3}},graphics_set={animation={north={layers={sprite}}}},crafting_categories={'modded-recipe'}}},
      ['simple-entity-with-owner']={['fc-station-assembly']={type='simple-entity-with-owner',name='fc-station-assembly',
        collision_box={{-1.2,-1.2},{1.2,1.2}},selection_box={{-1.5,-1.5},{1.5,1.5}}},
        ['fc-station-packing']={type='simple-entity-with-owner',name='fc-station-packing',
          collision_box={{-0.35,-0.35},{0.35,0.35}},selection_box={{-0.5,-0.5},{0.5,0.5}}}},
      boiler={['custom-boiler']={type='boiler',name='custom-boiler',icon='boiler.png',pictures={north={structure={layers={sprite}}}}}},
      ['mining-drill']={['custom-drill']={type='mining-drill',name='custom-drill',icon='drill.png',graphics_set={animation={layers={sprite}}}}},
      beacon={['custom-beacon']={type='beacon',name='custom-beacon',icon='beacon.png',graphics_set={animation_list={{animation=sprite}}}}},
      ['fusion-reactor']={['custom-reactor']={type='fusion-reactor',name='custom-reactor',graphics_set={structure=sprite}}},
      ['fusion-generator']={['custom-generator']={type='fusion-generator',name='custom-generator',graphics_set={north_graphics_set={animation=sprite}}}},
      furnace={['size-furnace']={type='furnace',name='size-furnace',graphics_set={animation={filename='square.png',size=128}}},
        ['rectangle-furnace']={type='furnace',name='rectangle-furnace',graphics_set={animation={filename='rectangle.png',size={128,64}}}}}
    }}
    function data:extend(rows) for _,row in ipairs(rows) do self.raw[row.type][row.name]=row end end
    package.loaded['prototypes.skins']=nil
    local ok,err=pcall(require,'prototypes.skins')
    local generated=data.raw;data=previous_data;table.deepcopy=deepcopy
    assert(ok,err)
    local skin=generated['assembling-machine']['fc-skin-production-modded-smelter']
    assert(skin and skin.graphics_set.animation.layers[1].filename=='modded-machine.png')
    assert(skin.crafting_categories[1]=='fc-production' and skin.energy_source.type=='void')
    assert(skin.collision_box[1][1]==-1.2,'a large skin must keep the production footprint')
    assert(skin.graphics_set.animation.layers[1].scale==0.25 and skin.graphics_set.animation.layers[1].shift[1]==0.5)
    assert(skin.graphics_set.animation.layers[1].frame_count==nil,'skin should use a static first frame')
    for _,name in ipairs({'custom-boiler','custom-drill','custom-beacon','custom-reactor','custom-generator','size-furnace'}) do
      assert(generated['assembling-machine']['fc-skin-production-'..name],name..' missing')
      assert(generated['simple-entity-with-owner']['fc-skin-station-assembly-'..name],name..' station missing')
    end
    local square=generated['assembling-machine']['fc-skin-production-size-furnace'].graphics_set.animation
    assert(square.width==128 and square.height==128)
    local rectangle=generated['assembling-machine']['fc-skin-production-rectangle-furnace'].graphics_set.animation
    assert(rectangle.width==128 and rectangle.height==64)
    local packing=generated['simple-entity-with-owner']['fc-skin-station-packing-modded-smelter']
    assert(packing.collision_box[1][1]==-0.35 and packing.picture.layers[1].scale==1/12)
    assert(not generated['assembling-machine']['fc-skin-production-fc-production-generic'])
  end
}
