local f=require('view_fixtures')
local cases={}
function cases.seeded_counts_and_six_motor_reason()
  local v=f.module('view_model').build(f.snapshot(),f.healthy())
  local c=v.centers[2]
  assert(c.running_count==1 and c.ready_count==3 and c.material_warning_count==1)
  assert(v.centers[3].waiting_count==4 and v.centers[4].waiting_count==4)
  local motor=v.orders[7].materials[2]
  for _,m in ipairs(v.orders[7].materials) do if m.product_id==3 then motor=m end end
  assert(motor.demand_qty==8 and motor.reserved_qty==2 and motor.unreserved_qty==6 and motor.warning)
  assert(motor.label:find('Electric motor',1,true) and motor.label:find('Unreserved 6 Units',1,true))
  assert(v.stock[10][1].on_hand_qty==14)
  assert(v.orders[3].requested_qty==4 and v.orders[4].requested_qty==6)
  assert(#v.orders[3].siblings==2)
end
function cases.center_done_means_running()
  local v=f.module('view_model').build(f.snapshot(),f.healthy())
  assert(v.centers[2].raw_state=='done' and v.centers[2].raw_state_label=='In Progress')
end
function cases.unknown_null_and_zero_are_truthful()
  local s=f.snapshot();s.work_centers[1].raw_working_state='future';s.work_orders[14].elapsed_minutes=0;s.work_orders[14].expected_minutes=0
  s.products[10].name='Pümpe [color=red]🔧[/color] [规格]\1'
  local v=f.module('view_model').build(s,f.healthy())
  assert(v.centers[1].raw_state_label=='Unknown (future)')
  assert(v.orders[8].operations[1].quantity_label:find('Output Unknown',1,true))
  assert(v.orders[6].operations[1].time_label:find('Elapsed 0 min',1,true))
  assert(v.orders[6].operations[1].time_ratio==nil)
  assert(v.orders[6].product=='Pümpe 🔧 ［规格］')
end
function cases.quantities_not_summed_across_operations_or_products()
  local v=f.module('view_model').build(f.snapshot(),f.healthy())
  assert(v.centers[2].quantity_ratio==nil and v.total_output==nil)
  assert(v.orders[2].posted_qty==10 and #v.orders[2].operations==3)
  assert(v.orders[4].operations[1].quantity_ratio==0.4)
  assert(v.orders[4].operations[1].quantity_label:find('Carried 4',1,true))
end
function cases.cycle_warns_without_losing_valid_view()
  local s=f.snapshot();s.work_orders[14].dependency_ids={15}
  local v=f.module('view_model').build(s,f.healthy())
  assert(#v.warnings>0 and v.centers[2].running_count==1 and v.orders[6])
  local seen={};for _,link in ipairs(v.links) do local key=link.from..'/'..link.to;assert(not seen[key]);seen[key]=true end
  assert(seen['1/2'] and seen['2/3'] and seen['3/4'])
end
function cases.unreserved_is_not_physical_shortage_and_health_is_fenced()
  local s=f.snapshot();for _,m in ipairs(s.material_demands) do m.availability_state=nil end;s.manufacturing_orders[7].availability_state=nil
  local h=f.healthy();h.verified=false
  local v=f.module('view_model').build(s,h)
  assert(v.centers[2].material_warning_count==0 and v.sync.label:find('Unverified',1,true))
  h=f.healthy();h.health.source_age_seconds=91
  assert(f.module('view_model').build(s,h).sync.label:find('Stale',1,true))
end
function cases.safe_ids_remain_distinct()
  local s=f.snapshot();s.work_centers[1].id=9007199254740990;s.work_centers[2].id=9007199254740991
  s.work_orders[1].center_id=9007199254740990
  for _,wo in ipairs(s.work_orders) do if wo.center_id==2 then wo.center_id=9007199254740991 end end
  local v=f.module('view_model').build(s,f.healthy())
  assert(v.centers[9007199254740990]~=v.centers[9007199254740991])
  assert(v.orders[6].record_url:find('/6',1,true))
end
return cases
