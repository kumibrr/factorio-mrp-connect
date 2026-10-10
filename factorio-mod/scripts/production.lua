-- Physical workpiece planning; never changes source business quantities.
local vm=require('scripts.view_model')
local M={}
local function chain(order)
  local byid,nexts,roots={},{},{}
  for _,op in ipairs(order.operations) do byid[op.id]=op end
  for _,op in ipairs(order.operations) do
    local deps=op.dependency_ids or {}
    if #deps==0 then roots[#roots+1]=op
    elseif #deps~=1 or not byid[deps[1]] or nexts[deps[1]] then return nil end
    if #deps==1 then nexts[deps[1]]=op end
  end
  if #roots~=1 then return nil end
  local ordered,seen={},{};local op=roots[1]
  while op do
    if seen[op.id] then return nil end
    seen[op.id]=true;ordered[#ordered+1]=op;op=nexts[op.id]
  end
  return #ordered==#order.operations and ordered or nil
end
function M.plan(view)
  local lanes,warnings,ids={},{},{}
  for key in pairs(view.orders) do ids[#ids+1]=key end;table.sort(ids)
  for _,key in ipairs(ids) do
    local order=view.orders[key]
    if order.raw_state~='cancel' and #order.operations>0 then
      local ops=chain(order)
      local quantity=ops and ops[1].required_qty and ops[1].carried_qty
        and math.max(0,ops[1].required_qty-ops[1].carried_qty) or nil
      if ops and quantity then
        for _,op in ipairs(ops) do
          if op.required_qty==nil or op.carried_qty==nil or math.abs(op.required_qty-op.carried_qty-quantity)>0.000001 then ops=nil;break end
        end
      end
      if not ops or not quantity then
        warnings[#warnings+1]='Physical flow unavailable for '..order.reference..': requires one dependency chain with known equal batch quantities; source details remain available.'
      elseif quantity>0 then
        local count=math.min(200,math.ceil(quantity))
        lanes[#lanes+1]={mo_id=key,order=order,operations=ops,quantity=quantity,count=count,quantum=quantity/count}
      end
    end
  end
  return lanes,warnings
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
