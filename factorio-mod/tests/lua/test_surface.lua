local f=require('view_fixtures')
return {
  workflow_obstruction_stays_visible_until_resolved=function()
    local surface,entities=f.engine();local obstacle=surface.create_entity{name='steel-chest',position={x=12,y=10}}
    surface.can_place_entity=function(spec)
      for _,e in ipairs(entities) do if e.valid and e.position.x==spec.position.x and e.position.y==spec.position.y then return false end end
      return true
    end
    local s=f.snapshot();local v=f.module('view_model').build(s,f.healthy());local slots=f.module('layout').reconcile(s.work_centers,{})
    local owned={};local m=f.module('surface');assert(#m.reconcile(v,slots,owned)>0)
    assert(#m.reconcile(v,slots,owned)>0 and obstacle.valid)
    obstacle.destroy();assert(#m.reconcile(v,slots,owned)==0)
  end,
  seeded_workflow_belts_do_not_obstruct_each_other=function()
    local surface,entities=f.engine();surface.can_place_entity=function(spec)
      for _,e in ipairs(entities) do if e.valid and e.position.x==spec.position.x and e.position.y==spec.position.y then return false end end
      return true
    end
    local s=f.snapshot();local owned={};local warnings=f.module('surface').reconcile(f.module('view_model').build(s,f.healthy()),f.module('layout').reconcile(s.work_centers,{}),owned)
    assert(#warnings==0,'seeded workflow should be unobstructed')
  end,
  unowned_name_collision_and_obstruction_preserve_unrelated_entities=function()
    local surface=f.engine();game.surfaces['odoo-factory']=surface
    local m=f.module('surface');local s=f.snapshot();local slots=f.module('layout').reconcile(s.work_centers,{})
    local v=f.module('view_model').build(s,f.healthy());local owned={}
    local warnings=m.reconcile(v,slots,owned)
    assert(#warnings>0 and not owned.surface and v.centers[2].running_count==1)
    game.surfaces={};surface.can_place_entity=function(spec) return spec.position.x~=24 end
    warnings=m.reconcile(v,slots,owned)
    assert(#warnings>0 and not owned.stations[2] and owned.stations[1].entity.valid)
  end,
  rename_archive_and_repeat_snapshot_are_idempotent=function()
    local _,entities,renders=f.engine();local m=f.module('surface');local s=f.snapshot()
    local v=f.module('view_model').build(s,f.healthy());local slots=f.module('layout').reconcile(s.work_centers,{})
    local owned={};m.reconcile(v,slots,owned);local station=owned.stations[2].entity
    m.reconcile(v,slots,owned);assert(owned.stations[2].entity==station)
    s.work_centers[2].name='Assembly renamed';s.work_centers[2].active=false
    m.reconcile(f.module('view_model').build(s,f.healthy()),slots,owned)
    assert(owned.stations[2].entity==station and station.valid and not station.minable and not station.destructible)
    local labels={};for _,r in ipairs(renders) do if r.valid and r.text then labels[#labels+1]=r.text end end
    assert(table.concat(labels,'\n'):find('Assembly renamed (Archived)',1,true))
  end,
  power_and_unrelated_entities_do_not_change_source_truth=function()
    local surface,entities=f.engine();local m=f.module('surface');local s=f.snapshot()
    local unrelated=surface.create_entity{name='steel-chest',position={x=150,y=0}}
    local v=f.module('view_model').build(s,f.healthy());local slots=f.module('layout').reconcile(s.work_centers,{})
    local owned={};m.reconcile(v,slots,owned);owned.stations[2].entity.energy=0
    m.reconcile(v,slots,owned);assert(v.centers[2].running_count==1 and unrelated.valid)
    m.clear(owned);assert(unrelated.valid)
    for _,e in ipairs(entities) do if e~=unrelated then assert(not e.valid) end end
  end
}
