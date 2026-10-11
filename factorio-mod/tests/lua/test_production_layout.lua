local f=require('view_fixtures')
return {
  a_wide_split_keeps_its_ports_inside_its_order_cell=function()
    local ops={{id=1,dependency_ids={}}}
    for i=2,14 do ops[#ops+1]={id=i,dependency_ids=i==2 and {1} or {1,i-1}} end
    local layout=f.module('production_layout').plan{operations=ops}
    assert(layout.height>=64,'thirteen outgoing ports must not spill into the next order cell')
  end,
  a_serial_order_stays_on_one_short_row=function()
    local lane={operations={{id=1,dependency_ids={}},{id=2,dependency_ids={1}},{id=3,dependency_ids={2}}}}
    local layout=f.module('production_layout').plan(lane)
    assert(layout.positions[1].x==0 and layout.positions[2].x==16 and layout.positions[3].x==32)
    assert(layout.positions[1].y==layout.positions[2].y and layout.positions[2].y==layout.positions[3].y)
    assert(layout.height<=40,'serial production must not consume multiple branch rows')
  end,
  parallel_steps_split_and_return_to_one_merge_machine=function()
    local lane={operations={{id=1,dependency_ids={}},{id=2,dependency_ids={1}},
      {id=3,dependency_ids={1}},{id=4,dependency_ids={2,3}}}}
    local layout=f.module('production_layout').plan(lane)
    assert(layout.positions[2].x==24 and layout.positions[3].x==24)
    assert(math.abs(layout.positions[2].y-layout.positions[3].y)==24)
    assert(layout.positions[4].x==48 and layout.positions[4].y==0)
    assert(layout.height<=64,'a diamond needs only two neighboring rows')
  end
}
