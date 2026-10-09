-- Snapshot-only business truth. Health is transport evidence, never production.
local M={}
local decimal=require('scripts.decimal')
M.palette={running={r=0.25,g=0.85,b=0.35},ready={r=0.3,g=0.65,b=1},attention={r=1,g=0.7,b=0.2},idle={r=0.65,g=0.65,b=0.65}}
function M.plain(value)
  if value==nil then return 'Unknown' end
  local text=tostring(value):gsub('%b[]',function(tag)
    local body=tag:sub(2,-2)
    if body:match('^/?[%a][%w%-]*=') or body:match('^/[%a][%w%-]*$') then return '' end
    return tag
  end)
  -- Keep ordinary bracketed Unicode text while preventing rich-text parsing.
  text=text:gsub('%[','［'):gsub('%]','］'):gsub('[%z\1-\31\127]','')
  return text
end
function M.number(value)
  if value==nil then return 'Unknown' end
  if type(value)~='number' then return 'Unknown' end
  local d=decimal.number(value)
  local digits=d.digits
  if d.power>=0 then digits=digits..string.rep('0',d.power)
  elseif #digits+d.power>0 then local split=#digits+d.power;digits=digits:sub(1,split)..'.'..digits:sub(split+1)
  else digits='0.'..string.rep('0',-d.power-#digits)..digits end
  return (d.sign<0 and '-' or '')..digits
end
local function id(value) return string.format('%d',value) end
local function index(rows) local out={};for _,row in ipairs(rows or {}) do out[row.id]=row end;return out end
local function terminal(raw) return raw=='done' or raw=='cancel' end
local function label(raw,known) return raw==nil and 'Unknown' or known[raw] or ('Unknown ('..M.plain(raw)..')') end
local wo_labels={progress='Running',ready='Ready',blocked='Dependency waiting',done='Completed',cancel='Cancelled'}
local center_labels={normal='Idle',done='In Progress',blocked='Blocked'}
local mo_labels={draft='Draft',confirmed='Confirmed',progress='In Progress',to_close='To Close',done='Completed',cancel='Cancelled'}
local function ratio(output,carried,required)
  if output==nil or carried==nil or required==nil or required<=0 then return nil end
  return (output+carried)/required
end
local function cycles(rows,getdeps,warnings,kind)
  local colors={}
  local function visit(key)
    if colors[key]==1 then warnings[#warnings+1]=kind..' dependency cycle at '..id(key);return end
    if colors[key]==2 or not rows[key] then return end
    colors[key]=1
    for _,dep in ipairs(getdeps(rows[key]) or {}) do
      if rows[dep] then visit(dep) else warnings[#warnings+1]=kind..' missing predecessor '..id(dep) end
    end
    colors[key]=2
  end
  for key in pairs(rows) do visit(key) end
end
local function sync(snapshot,status)
  status=status or {};local h=status.health or {}
  local transport
  if status.connected and status.verified then transport='Connected'
  elseif status.connected or status.stage=='ack' or (status.stage=='challenge' and status.restart_reason~='timeout') then transport='Resynchronizing'
  else transport='Disconnected' end
  -- Only a current bridge report establishes source age. Running ticks never
  -- turn a retained source timestamp into a wall-clock freshness claim.
  local stale=h.source_age_seconds~=nil and h.source_age_seconds>90
  local freshness=h.source_age_seconds==nil and 'Source freshness Unknown' or (stale and 'Stale source data' or 'Source age within threshold')
  local failed=h.source_ok==false
  local text
  if not snapshot then text='Awaiting snapshot'
  elseif transport~='Connected' then text=transport
  elseif stale then text='Stale source data'
  elseif failed then text='Source read failed'
  elseif h.source_age_seconds==nil then text='Source freshness Unknown'
  elseif h.refreshing then text='Refreshing source'
  else text='Healthy' end
  return {label=text,source_read_at=snapshot and snapshot.meta.source_read_at or 'Unknown',
    source_age_label=M.number(h.source_age_seconds),last_success_at=M.plain(h.last_success_at),
    error=M.plain(h.last_error),verified=status.verified==true,connected=status.connected==true,refreshing=h.refreshing==true,
    transport_label=transport,stage=M.plain(status.stage),restart_reason=M.plain(status.restart_reason),
    freshness_label=freshness,stale=stale,source_failed=failed}
end
function M.build(snapshot,status)
  local v={centers={},center_ids={},orders={},stock={},links={},warnings={},sync=sync(snapshot,status),palette=M.palette}
  if not snapshot then return v end
  local products,units,mos,wos=index(snapshot.products),index(snapshot.units),index(snapshot.manufacturing_orders),index(snapshot.work_orders)
  local function unit(key) return units[key] and M.plain(units[key].name) or 'Unknown unit' end
  local function product(key) return products[key] and M.plain(products[key].name) or 'Unknown product' end
  local function q(value,key) return M.number(value)..(value==nil and '' or ' '..unit(key)) end
  local groups={}
  for _,mo in ipairs(snapshot.manufacturing_orders) do
    local row={id=mo.id,reference=M.plain(mo.reference),product=product(mo.product_id),product_id=mo.product_id,unit_id=mo.unit_id,
      requested_qty=mo.requested_qty,reported_qty=mo.reported_qty,posted_qty=mo.posted_qty,raw_state=mo.raw_state,
      state_label=label(mo.raw_state,mo_labels),terminal=terminal(mo.raw_state),materials={},operations={},siblings={},
      record_url=snapshot.meta.odoo_base_url:gsub('/+$','')..'/odoo/mrp.production/'..id(mo.id),
      quantity_label='Requested '..q(mo.requested_qty,mo.unit_id)..' | Reported '..q(mo.reported_qty,mo.unit_id)..' | Posted '..q(mo.posted_qty,mo.unit_id),
      dates_label='Planned '..M.plain(mo.planned_start_at)..' | Deadline '..M.plain(mo.deadline_at)..' | Started '..M.plain(mo.started_at)..' | Finished '..M.plain(mo.finished_at),
      readiness_label='MO readiness '..M.plain(mo.readiness_state)..' | Availability '..M.plain(mo.availability_state),
      group_id=mo.group_id,backorder_sequence=mo.backorder_sequence,origin=M.plain(mo.origin)}
    v.orders[mo.id]=row
    if mo.group_id then groups[mo.group_id]=groups[mo.group_id] or {};groups[mo.group_id][#groups[mo.group_id]+1]=row end
  end
  for _,row in pairs(v.orders) do row.siblings=groups[row.group_id] or {} end
  for _,d in ipairs(snapshot.material_demands) do
    local order=v.orders[d.mo_id]
    if order then
      local m={};for k,x in pairs(d) do m[k]=x end
      -- A missing reservation alone is not evidence of physical absence.
      m.warning=d.unreserved_qty>0 and (d.availability_state=='unavailable' or (d.forecast_qty~=nil and d.forecast_qty<0)
        or (mos[d.mo_id] and mos[d.mo_id].availability_state=='unavailable'))
      m.label=product(d.product_id)..' | Demand '..q(d.demand_qty,d.unit_id)..' | Remaining '..q(d.remaining_demand_qty,d.unit_id)
        ..' | Reserved '..q(d.reserved_qty,d.unit_id)..' | Unreserved '..q(d.unreserved_qty,d.unit_id)
        ..' | Picked '..q(d.picked_qty,d.unit_id)..' | Posted consumed '..q(d.posted_consumed_qty,d.unit_id)
        ..' | Forecast '..q(d.forecast_qty,d.unit_id)..' | Availability '..M.plain(d.availability_state)
      order.materials[#order.materials+1]=m
      order.material_warning=order.material_warning or m.warning
    else v.warnings[#v.warnings+1]='Missing material MO '..id(d.mo_id) end
  end
  for _,c in ipairs(snapshot.work_centers) do
    v.centers[c.id]={id=c.id,name=M.plain(c.name),code=M.plain(c.code),active=c.active,
      display_name=M.plain(c.name)..(c.active and '' or ' (Archived)'),raw_state=c.raw_working_state,
      raw_state_label=label(c.raw_working_state,center_labels),running_count=0,ready_count=0,waiting_count=0,material_warning_count=0,
      orders={},history={},order_states={},material_orders={}}
    v.center_ids[#v.center_ids+1]=c.id
  end
  table.sort(v.center_ids)
  for _,wo in ipairs(snapshot.work_orders) do
    local order,center=v.orders[wo.mo_id],v.centers[wo.center_id]
    if order and center then
      local op={id=wo.id,mo_id=wo.mo_id,center_id=wo.center_id,operation_id=wo.operation_id,raw_state=wo.raw_state,
        state_label=label(wo.raw_state,wo_labels),output_qty=wo.output_qty,carried_qty=wo.carried_qty,required_qty=wo.required_qty,
        remaining_qty=wo.remaining_qty,ready_qty=wo.ready_qty,expected_minutes=wo.expected_minutes,elapsed_minutes=wo.elapsed_minutes,
        quantity_ratio=ratio(wo.output_qty,wo.carried_qty,wo.required_qty),
        time_ratio=wo.expected_minutes and wo.expected_minutes>0 and wo.elapsed_minutes and wo.elapsed_minutes/wo.expected_minutes or nil,
        quantity_label='Output '..q(wo.output_qty,wo.unit_id)..' | Carried '..q(wo.carried_qty,wo.unit_id)..' | Required '..q(wo.required_qty,wo.unit_id)
          ..' | Remaining '..q(wo.remaining_qty,wo.unit_id)..' | Ready quantity '..q(wo.ready_qty,wo.unit_id),
        time_label='Elapsed '..M.number(wo.elapsed_minutes)..' min | Expected '..M.number(wo.expected_minutes)..' min',dependencies={}}
      for _,dep_id in ipairs(wo.dependency_ids) do
        local dep=wos[dep_id]
        op.dependencies[#op.dependencies+1]=dep and ('WO '..id(dep_id)..' ('..label(dep.raw_state,wo_labels)..', raw '..M.plain(dep.raw_state)..')') or ('Missing WO '..id(dep_id))
      end
      op.dependency_label=#op.dependencies>0 and table.concat(op.dependencies,', ') or 'No operation predecessor reported; material availability is separate'
      order.operations[#order.operations+1]=op
      local rows=(order.terminal or terminal(wo.raw_state)) and center.history or center.orders
      rows[#rows+1]={order=order,operation=op}
      if rows==center.orders then
        local priorities={progress=3,ready=2,blocked=1}
        local previous=center.order_states[wo.mo_id]
        if not previous or (priorities[wo.raw_state] or 0)>(priorities[previous] or 0) then center.order_states[wo.mo_id]=wo.raw_state end
        if order.material_warning then center.material_orders[wo.mo_id]=true end
      end
    else v.warnings[#v.warnings+1]='Missing WO center or MO for '..id(wo.id) end
  end
  for _,c in pairs(v.centers) do
    for _,raw in pairs(c.order_states) do
      if raw=='progress' then c.running_count=c.running_count+1 elseif raw=='ready' then c.ready_count=c.ready_count+1 elseif raw=='blocked' then c.waiting_count=c.waiting_count+1 end
    end
    for _ in pairs(c.material_orders) do c.material_warning_count=c.material_warning_count+1 end
  end
  for _,stock in ipairs(snapshot.stock) do
    local row={};for k,x in pairs(stock) do row[k]=x end
    row.label=product(stock.product_id)..' | Location '..id(stock.location_id)..' | On hand '..q(stock.on_hand_qty,stock.unit_id)..' | Reserved '..q(stock.reserved_qty,stock.unit_id)..' | Free '..q(stock.free_qty,stock.unit_id)
    v.stock[stock.product_id]=v.stock[stock.product_id] or {};v.stock[stock.product_id][#v.stock[stock.product_id]+1]=row
  end
  cycles(wos,function(row) return row.dependency_ids end,v.warnings,'WO')
  local links={}
  local function link(from,to,reason)
    if not from or not to or from==to then return end
    if not v.centers[from] or not v.centers[to] then v.warnings[#v.warnings+1]='Missing workflow center';return end
    links[from]=links[from] or {};local row=links[from][to]
    if not row then row={from=from,to=to,reasons={}};links[from][to]=row end
    row.reasons[reason]=true
  end
  for _,wo in ipairs(snapshot.work_orders) do
    for _,dep in ipairs(wo.dependency_ids) do if wos[dep] then link(wos[dep].center_id,wo.center_id,'Operation dependency') end end
  end
  local producers={}
  for _,bom in ipairs(snapshot.boms) do
    local ops=index(bom.operations);local successors={}
    cycles(ops,function(row) return row.dependency_ids end,v.warnings,'BOM '..id(bom.id))
    for _,op in ipairs(bom.operations) do for _,dep in ipairs(op.dependency_ids) do successors[dep]=true;if ops[dep] then link(ops[dep].center_id,op.center_id,'BOM operation dependency') end end end
    producers[bom.product_id]=producers[bom.product_id] or {}
    for _,op in ipairs(bom.operations) do if not successors[op.id] then producers[bom.product_id][#producers[bom.product_id]+1]=op.center_id end end
  end
  for _,bom in ipairs(snapshot.boms) do
    local ops=index(bom.operations)
    for _,component in ipairs(bom.components) do
      local target=ops[component.operation_id]
      if target then for _,from in ipairs(producers[component.product_id] or {}) do link(from,target.center_id,'BOM supply: '..product(component.product_id)) end end
    end
  end
  for from,targets in pairs(links) do
    for to,row in pairs(targets) do
      local reasons={};for reason in pairs(row.reasons) do reasons[#reasons+1]=reason end;table.sort(reasons)
      row.label=table.concat(reasons,'; ')..' — intended workflow, not stock transport';v.links[#v.links+1]=row
    end
  end
  table.sort(v.links,function(a,b) return a.from==b.from and a.to<b.to or a.from<b.from end)
  table.sort(v.warnings)
  return v
end
return M
