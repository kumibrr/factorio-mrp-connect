local f=require('view_fixtures')
local function model() return f.module('view_model').build(f.snapshot(),f.healthy()) end
return {
  material_markers_use_the_components_own_unit=function()
    local snapshot=f.snapshot();snapshot.units[#snapshot.units+1]={id=2,name='kg',rounding=0.01}
    for _,d in ipairs(snapshot.material_demands) do if d.mo_id==6 and d.product_id==9 then d.unit_id=2 end end
    local flows=f.module('production').plan(f.module('view_model').build(snapshot,f.healthy()))
    for _,m in ipairs(flows[6].materials) do if m.product_id==9 then assert(m.unit_label=='kg');return end end
    error('missing impeller route')
  end,
  unresolved_material_routes_cannot_bypass_component_receipts=function()
    local v=model();v.orders[6].product_id=999
    local flows,warnings=f.module('production').plan(v)
    assert(#warnings>0)
    for _,lane in ipairs(flows) do assert(lane.mo_id~=6,'unassigned material must prevent physical release') end
  end,
  branches_and_joins_follow_the_actual_dependency_graph=function()
    local v=model();local ops=v.orders[6].operations
    local branch={};for k,x in pairs(ops[2]) do branch[k]=x end
    branch.id=99;branch.dependency_ids={ops[1].id}
    ops[3].dependency_ids={ops[2].id,99};ops[#ops+1]=branch
    local flows,warnings=f.module('production').plan(v)
    assert(#warnings==0 and #flows==7,'a valid diamond must have a physical flow')
    local lane=flows[6]
    assert(#lane.edges==4 and #lane.roots==1 and #lane.sinks==1)
    assert(lane.operations[4].id==16,'join must follow both predecessors')
  end,
  multiple_roots_are_supported_but_cycles_and_missing_predecessors_are_not=function()
    local v=model();v.orders[6].operations[2].dependency_ids={}
    local p=f.module('production');local flows,warnings=p.plan(v)
    assert(#flows==7 and #warnings==0 and #flows[6].roots==2)
    v.orders[6].operations[1].dependency_ids={16}
    flows,warnings=p.plan(v);assert(#flows==7 and #warnings==0)
    v.orders[6].operations[2].dependency_ids={14}
    flows,warnings=p.plan(v);assert(#flows==6 and #warnings==1)
    v.orders[6].operations[2].dependency_ids={999}
    flows,warnings=p.plan(v);assert(#flows==6 and #warnings==1)
  end,
  material_routes_are_assigned_to_their_bom_operation_and_allocation=function()
    local p=f.module('production');local flows=p.plan(model());local lane=flows[6]
    assert(#lane.materials==8,'every actual component demand must feed the network')
    local impeller,carton
    for _,m in ipairs(lane.materials) do
      if m.product_id==9 then impeller=m end
      if m.product_id==8 then carton=m end
    end
    assert(impeller and impeller.to==14 and impeller.product_id==9)
    assert(carton and carton.to==16)
    assert(p.material_budget(impeller,10)==10)
    impeller.demand.reserved_qty=3;assert(p.material_budget(impeller,10)==3)
    impeller.demand.picked_qty=2;assert(p.material_budget(impeller,10)==5)
    impeller.demand.posted_consumed_qty=5;assert(p.material_budget(impeller,10)==10)
  end,
  lanes_follow_dependencies_and_exclude_cancelled_orders=function()
    local flows,warnings=f.module('production').plan(model())
    assert(#warnings==0 and #flows==7)
    local lane=flows[6]
    assert(lane.mo_id==6 and lane.operations[1].id==14 and lane.operations[2].id==15 and lane.operations[3].id==16)
    assert(lane.count==10 and lane.quantum==1)
  end,
  backorders_do_not_recreate_carried_output=function()
    local flows=f.module('production').plan(model())
    assert(flows[4].count==6 and flows[4].quantity==6)
  end,
  fractional_and_large_batches_are_bounded_without_changing_source_quantities=function()
    local v=model();v.orders[1].operations[1].required_qty=1000.5
    local flows=f.module('production').plan(v)
    assert(flows[1].count==200 and flows[1].quantum==5.0025 and flows[1].quantity==1000.5)
    assert(v.orders[1].operations[1].required_qty==1000.5)
    v.orders[1].operations[1].required_qty=0.25
    flows=f.module('production').plan(v);assert(flows[1].count==1 and flows[1].quantum==0.25)
  end,
  missing_dependencies_never_invent_a_serial_route=function()
    local v=model();v.orders[6].operations[2].dependency_ids={999}
    local flows,warnings=f.module('production').plan(v)
    assert(#flows==6 and #warnings==1)
    for _,lane in ipairs(flows) do assert(lane.mo_id~=6) end
  end,
  release_budget_requires_recorded_output_or_done=function()
    local p=f.module('production');local op=model().orders[6].operations[1]
    assert(p.budget(op,1,10)==0)
    op.output_qty=3;assert(p.budget(op,1,10)==3)
    op.output_qty=nil;assert(p.budget(op,1,10)==0)
    op.raw_state='done';assert(p.budget(op,1,10)==10)
    op.raw_state='cancel';assert(p.budget(op,1,10)==0)
  end,
  estimated_remaining_is_not_invented_when_elapsed_is_unknown=function()
    local p=f.module('production');local op=model().orders[6].operations[1]
    assert(p.timing(op):find('Remaining estimate Unknown',1,true))
    op.elapsed_minutes=12;assert(p.timing(op):find('Remaining estimate 38 min',1,true))
    op.elapsed_minutes=70;assert(p.timing(op):find('Over expected by 20 min',1,true))
    op.expected_minutes=0;assert(p.timing(op):find('Remaining estimate Unknown',1,true))
  end,
  observed_clock_pauses_without_healthy_source_and_resets_between_runs=function()
    local p=f.module('production');local op=model().orders[6].operations[1];local clock={}
    p.observe(op,clock,0,true);p.observe(op,clock,120,true);assert(clock.ticks==120)
    p.observe(op,clock,240,false);p.observe(op,clock,360,true);assert(clock.ticks==120)
    p.observe(op,clock,420,true);assert(clock.ticks==180)
    op.raw_state='done';p.observe(op,clock,480,true);assert(clock.ticks==180)
    op.raw_state='progress';p.observe(op,clock,540,true);assert(clock.ticks==0)
  end
}
