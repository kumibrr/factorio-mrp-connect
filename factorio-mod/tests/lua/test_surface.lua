local f=require('view_fixtures')
return {
  removed_operations_cannot_accumulate_observed_running_time=function()
    f.engine();local v=f.module('view_model').build(f.snapshot(),f.healthy())
    local m=f.module('surface');local owned={}
    m.update(v,owned,0);m.update(v,owned,60);assert(owned.production_clocks[14].ticks==60)
    local order=v.orders[6];v.orders[6]=nil;m.update(v,owned,600)
    v.orders[6]=order;m.update(v,owned,1200)
    assert(owned.production_clocks[14].ticks==0)
  end,
  new_summary_rows_do_not_reseed_existing_production=function()
    f.engine();local s=f.snapshot();local m=f.module('surface');local owned={}
    local slots=f.module('layout').reconcile(s.work_centers,{})
    m.reconcile(f.module('view_model').build(s,f.healthy()),slots,owned)
    local lane=owned.production[6];lane.machines[1].released=3;s.work_orders[14].output_qty=3
    for key=5,9 do s.work_centers[#s.work_centers+1]={id=key,name='New center',code='NEW',active=true} end
    slots=f.module('layout').reconcile(s.work_centers,slots)
    m.reconcile(f.module('view_model').build(s,f.healthy()),slots,owned)
    assert(owned.production[6]==lane and lane.source.valid and lane.machines[1].released==3)
  end,
  production_lanes_preserve_identity_and_cleanup_only_cancelled_work=function()
    local _,_,_=f.engine();local s=f.snapshot();local m=f.module('surface');local owned={}
    local slots=f.module('layout').reconcile(s.work_centers,{})
    local v=f.module('view_model').build(s,f.healthy());assert(#m.reconcile(v,slots,owned)==0)
    local lane=owned.production[6];local machine=lane.machines[1].entity
    assert(m.center_for_entity(owned,machine)==2)
    assert(lane.source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material')==10)
    assert(owned.production[4].source.get_inventory(defines.inventory.chest).get_item_count('fc-raw-material')==6)
    assert(not owned.production[8])
    m.reconcile(v,slots,owned);assert(owned.production[6].machines[1].entity==machine)
    s.manufacturing_orders[6].raw_state='cancel';v=f.module('view_model').build(s,f.healthy())
    m.reconcile(v,slots,owned);assert(not machine.valid and not owned.production[6])
    assert(owned.production[4].source.valid and owned.stations[2].entity.valid)
  end,
  production_obstruction_never_starts_a_partial_lane=function()
    local surface,entities=f.engine();local obstacle=surface.create_entity{name='steel-chest',position={x=-4,y=40}}
    surface.can_place_entity=function(spec)
      for _,e in ipairs(entities) do if e.valid and e.position.x==spec.position.x and e.position.y==spec.position.y then return false end end
      return true
    end
    local s=f.snapshot();local v=f.module('view_model').build(s,f.healthy());local slots=f.module('layout').reconcile(s.work_centers,{})
    local owned={};local m=f.module('surface');local warnings=m.reconcile(v,slots,owned)
    -- Shared routing can also hold another order while this area is obstructed.
    assert(#warnings>=1,table.concat(warnings,'\n'))
    assert(owned.production[1].incomplete and #owned.production[1].entities==0 and obstacle.valid)
    obstacle.destroy();warnings=m.reconcile(v,slots,owned)
    assert(#warnings==0 and owned.production[1].source.valid,table.concat(warnings,'\n'))
  end,
  source_output_correction_replaces_only_the_affected_lane=function()
    f.engine();local s=f.snapshot();local v=f.module('view_model').build(s,f.healthy())
    local slots=f.module('layout').reconcile(s.work_centers,{});local owned={};local m=f.module('surface')
    m.reconcile(v,slots,owned);local lane=owned.production[6];local other=owned.production[5].source
    lane.machines[1].released=3;s.work_orders[14].output_qty=1
    m.reconcile(f.module('view_model').build(s,f.healthy()),slots,owned)
    assert(not lane.source.valid and owned.production[6].machines[1].released==0)
    assert(owned.production[5].source==other and other.valid)
  end,
  decorative_workflow_routes_are_removed_without_touching_unrelated_entities=function()
    local surface=f.engine();local obstacle=surface.create_entity{name='steel-chest',position={x=12,y=10}}
    local old_belt=surface.create_entity{name='transport-belt',position={x=13,y=10}}
    local label=rendering.draw_text{text='old route'}
    local s=f.snapshot();local v=f.module('view_model').build(s,f.healthy());local slots=f.module('layout').reconcile(s.work_centers,{})
    local owned={surface=surface,links={[1]={[2]={entities={old_belt},renders={label}}}}};local m=f.module('surface')
    assert(#m.reconcile(v,slots,owned)==0)
    assert(not old_belt.valid and not label.valid and obstacle.valid,'remove only the owned decorative network')
    assert(next(owned.links)==nil,'work-center summaries must not duplicate production with another belt web')
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
