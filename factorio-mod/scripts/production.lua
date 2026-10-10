-- Physical workpiece planning; never changes source business quantities.
local vm=require('scripts.view_model')
local M={}
local function graph(order)
  local byid,successors,indegree,roots,edges={},{},{},{},{}
  for _,op in ipairs(order.operations) do
    byid[op.id]=op;successors[op.id]={};indegree[op.id]=0
  end
  for _,op in ipairs(order.operations) do
    local seen={}
    for _,dep in ipairs(op.dependency_ids or {}) do
      if not byid[dep] or seen[dep] then return nil end
      seen[dep]=true;indegree[op.id]=indegree[op.id]+1
      successors[dep][#successors[dep]+1]=op.id;edges[#edges+1]={from=dep,to=op.id}
    end
    if indegree[op.id]==0 then roots[#roots+1]=op.id end
  end
  table.sort(roots)
  local ready={};for _,key in ipairs(roots) do ready[#ready+1]=key end
  local ordered,sinks={},{}
  while #ready>0 do
    table.sort(ready);local key=table.remove(ready,1);ordered[#ordered+1]=byid[key]
    if #successors[key]==0 then sinks[#sinks+1]=key end
    for _,next_id in ipairs(successors[key]) do
      indegree[next_id]=indegree[next_id]-1
      if indegree[next_id]==0 then ready[#ready+1]=next_id end
    end
  end
  if #ordered~=#order.operations then return nil end
  table.sort(edges,function(a,b) return a.from==b.from and a.to<b.to or a.from<b.from end)
  return ordered,edges,roots,sinks
end
local function materials(order,ops,roots,view,warnings)
  local out={};local operations={};local unresolved=false
  for _,op in ipairs(ops) do operations[op.operation_id]=operations[op.operation_id] or {};operations[op.operation_id][#operations[op.operation_id]+1]=op.id end
  for _,demand in ipairs(order.materials) do
    if demand.demand_qty>0 and demand.availability_state~='cancel' then
      local targets={}
      for _,bom in ipairs(view.boms or {}) do
        if bom.product_id==order.product_id then
          local matches=false
          for _,op in ipairs(bom.operations) do if operations[op.id] then matches=true end end
          if matches then for _,component in ipairs(bom.components) do
            if component.product_id==demand.product_id then
              if component.operation_id then
                for _,id in ipairs(operations[component.operation_id] or {}) do targets[id]=true end
              elseif #roots==1 then targets[roots[1]]=true end
            end
          end end
        end
      end
      local target,n=nil,0
      for id in pairs(targets) do target=id;n=n+1 end
      if n==1 then
        out[#out+1]={id=demand.id,product_id=demand.product_id,location_id=demand.source_location_id,to=target,demand=demand,
          unit_label=view.units[demand.unit_id] and vm.plain(view.units[demand.unit_id].name) or 'Unknown unit',
          label=view.products[demand.product_id] and vm.plain(view.products[demand.product_id].name) or 'Unknown product'}
      else
        unresolved=true
        warnings[#warnings+1]='Material routing unavailable for '..order.reference..': '..demand.label..'; consuming operation is ambiguous.'
      end
    end
  end
  table.sort(out,function(a,b) return a.id<b.id end)
  return out,unresolved
end
function M.plan(view)
  local lanes,warnings,ids={},{},{}
  for key in pairs(view.orders) do ids[#ids+1]=key end;table.sort(ids)
  for _,key in ipairs(ids) do
    local order=view.orders[key]
    if order.raw_state~='cancel' and #order.operations>0 then
      local ops,edges,roots,sinks=graph(order)
      local quantity=ops and ops[1].required_qty and ops[1].carried_qty
        and math.max(0,ops[1].required_qty-ops[1].carried_qty) or nil
      if ops and quantity then
        for _,op in ipairs(ops) do
          if op.required_qty==nil or op.carried_qty==nil or math.abs(op.required_qty-op.carried_qty-quantity)>0.000001 then ops=nil;break end
        end
      end
      if not ops or not quantity then
        warnings[#warnings+1]='Physical flow unavailable for '..order.reference..': requires an acyclic dependency graph with known equal batch quantities; source details remain available.'
      elseif quantity>0 then
        local count=math.min(200,math.ceil(quantity))
        local material_routes,unresolved=materials(order,ops,roots,view,warnings)
        if not unresolved then lanes[#lanes+1]={mo_id=key,order=order,operations=ops,edges=edges,roots=roots,sinks=sinks,
          materials=material_routes,quantity=quantity,count=count,quantum=quantity/count} end
      end
    end
  end
  return lanes,warnings
end
function M.material_budget(material,count)
  local d=material.demand
  local allocated=(d.reserved_qty or 0)+(d.picked_qty or 0)+(d.posted_consumed_qty or 0)
  return math.min(count,math.max(0,math.floor(allocated/d.demand_qty*count+0.00000001)))
end
function M.budget(op,quantum,count)
  if op.raw_state=='cancel' then return 0 end
  if op.raw_state=='done' then return count end
  return math.min(count,math.max(0,math.floor((op.output_qty or 0)/quantum+0.00000001)))
end
function M.timing(op)
  local estimate='Remaining estimate Unknown'
  if op.expected_minutes and op.expected_minutes>0 and op.elapsed_minutes~=nil then
    local remaining=op.expected_minutes-op.elapsed_minutes
    estimate=remaining>=0 and ('Remaining estimate '..vm.number(remaining)..' min')
      or ('Over expected by '..vm.number(-remaining)..' min')
  end
  return 'Elapsed '..vm.number(op.elapsed_minutes)..' min | Expected '..vm.number(op.expected_minutes)..' min | '..estimate
end
function M.observe(op,clock,tick,healthy)
  local running=op.raw_state=='progress'
  if running and not clock.running then clock.ticks=0 end
  if running and clock.running and healthy and clock.healthy and clock.last_tick then
    clock.ticks=(clock.ticks or 0)+math.max(0,tick-clock.last_tick)
  end
  clock.running=running;clock.healthy=healthy;clock.last_tick=tick
  local seconds=math.floor((clock.ticks or 0)/60)
  op.running_label=M.timing(op)..(running and string.format(' | Observed running %02d:%02d (game time)',math.floor(seconds/60),seconds%60) or '')
  return op.running_label
end
return M
