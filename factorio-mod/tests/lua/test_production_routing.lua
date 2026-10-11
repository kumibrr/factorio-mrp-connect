local f=require('view_fixtures')
return {
  farther_tunnel_landings_escape_a_blocked_nearest_exit=function()
    local occupied={}
    for y=-100,100 do
      occupied['5:'..y]={kind='entity'};occupied['9:'..y]={kind='entity'}
    end
    local path=f.module('production_routing').route({x=0,y=0},{x=12,y=0},occupied)
    assert(path and #path<=13,'routing must try a farther underground exit before a long detour')
    for _,p in ipairs(path) do assert(not occupied[p.position.x..':'..p.position.y]) end
  end,
  receivers_are_approached_from_the_feed_direction=function()
    local path=f.module('production_routing').route({x=6,y=0},{x=0,y=0},{})
    assert(path)
    local previous=path[#path-1]
    assert(previous.position.x<0 and previous.position.y==0,'a receiver approached head-on cannot transport items')
  end,
  parallel_underground_pairs_cannot_steal_each_others_connections=function()
    local occupied={['2:0']={kind='belt',direction=4,type='input'},['8:0']={kind='belt',direction=4,type='output'}}
    local path=f.module('production_routing').route({x=0,y=0},{x=12,y=0},occupied)
    assert(path)
    for _,p in ipairs(path) do
      if p.type and p.position.y==0 and p.direction==4 then
        assert(math.abs(p.position.x-2)>9 and math.abs(p.position.x-8)>9,'same-axis underground endpoints would steal a connection')
      end
    end
  end,
  routes_turn_around_entity_footprints=function()
    local router=f.module('production_routing');local occupied={}
    for y=-2,2 do occupied['3:'..y]={kind='entity'} end
    local path=router.route({x=0,y=0},{x=6,y=0},occupied)
    assert(path and #path>0)
    for _,p in ipairs(path) do assert(not occupied[p.position.x..':'..p.position.y]) end
    assert(path[1].position.x==0 and path[#path].position.x==6)
    assert(path[#path].direction==4,'receiver belt must feed its finish inserter')
    local previous=path[#path-1]
    assert(previous.position.x<6 and previous.position.y==0,'head-on endpoint would stop native transport')
  end,
  crossed_routes_use_underground_pairs_without_sharing_tiles=function()
    local router=f.module('production_routing');local occupied={}
    for y=-20,20 do occupied['5:'..y]={kind='belt',direction=8} end
    local path=router.route({x=0,y=0},{x=10,y=0},occupied)
    assert(path and #path<20)
    local inputs,outputs=0,0
    for _,p in ipairs(path) do
      assert(not occupied[p.position.x..':'..p.position.y])
      if p.type=='input' then inputs=inputs+1 end
      if p.type=='output' then outputs=outputs+1 end
    end
    assert(inputs==1 and outputs==1,'crossing must be underground')
  end,
  impossible_endpoints_do_not_return_partial_routes=function()
    local router=f.module('production_routing');local occupied={['0:0']={kind='entity'}}
    assert(not router.route({x=0,y=0},{x=3,y=0},occupied))
  end
}
