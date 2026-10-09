-- Shared v1 shape, quantities and reference graph. Nil represents source null.
local decimal=require("scripts.decimal")
local M={}
local MAX_INTEGER=9007199254740991
local function finite(v) return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function integer(v,minimum) return finite(v) and v%1==0 and v>=minimum and v<=MAX_INTEGER end
local function uuid(v) return type(v)=='string' and v:match('^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$')~=nil end
local function scope(v)
  if type(v)~='string' then return false end
  local company,warehouse=v:match('^company:([1-9]%d*)/warehouse:([1-9]%d*)$')
  return company~=nil and integer(tonumber(company),1) and integer(tonumber(warehouse),1)
end
local function utc(v)
  if type(v)~='string' then return false end
  local y,m,d,h,n,s,rest=v:match('^(%d%d%d%d)%-(%d%d)%-(%d%d)[Tt](%d%d):(%d%d):(%d%d)(.*)$')
  if not y then return false end
  y,m,d,h,n,s=tonumber(y),tonumber(m),tonumber(d),tonumber(h),tonumber(n),tonumber(s)
  if y<1 or m<1 or m>12 or h>23 or n>59 or s>59 then return false end
  local days={31,28,31,30,31,30,31,31,30,31,30,31}
  if y%4==0 and (y%100~=0 or y%400==0) then days[2]=29 end
  if d<1 or d>days[m] then return false end
  rest=rest:gsub('^%.%d+','')
  return rest=='Z' or rest=='z' or rest=='+00:00' or rest=='-00:00'
end
local predicates={id=function(v) return integer(v,1) end,seq=function(v) return integer(v,0) end,
  qty=function(v) return finite(v) and v>=0 end,pos=function(v) return finite(v) and v>0 end,
  finite=finite,text=function(v) return type(v)=='string' and #v>0 end,str=function(v) return type(v)=='string' end,
  bool=function(v) return type(v)=='boolean' end,uuid=uuid,scope=scope,utc=utc,
  one=function(v) return v==1 end,twenty=function(v) return v==20 end,
  url=function(v) return type(v)=='string' and v:match('^https?://[^/%s]+/?[^%s]*$')~=nil end}
local function object(fields) return {fields=fields} end
local function array(item) return {item=item} end
local specs={}
specs.meta=object{schema_version='one',source_id='uuid',scope_id='scope',company_id='id',warehouse_id='id',source_read_at='utc',odoo_major='twenty',odoo_base_url='url'}
specs.unit=object{id='id',name='text',rounding='pos'}
specs.product=object{id='id',name='text',code='str?',unit_id='id'}
specs.center=object{id='id',name='text',code='str?',active='bool',capacity='pos',calendar_id='id?',raw_working_state='str?'}
specs.mo=object{id='id',reference='text',origin='str?',product_id='id',unit_id='id',requested_qty='qty',reported_qty='qty?',posted_qty='qty',raw_state='text',planned_start_at='utc?',deadline_at='utc?',started_at='utc?',finished_at='utc?',readiness_state='str?',availability_state='str?',group_id='id?',backorder_sequence='seq?'}
specs.wo=object{id='id',mo_id='id',center_id='id',operation_id='id',unit_id='id',sequence='seq',dependency_ids=array('id'),raw_state='text',output_qty='qty?',carried_qty='qty?',required_qty='qty?',remaining_qty='qty?',ready_qty='qty?',expected_minutes='qty?',elapsed_minutes='qty?'}
specs.component=object{product_id='id',unit_id='id',quantity='qty',operation_id='id?'}
specs.operation=object{id='id',center_id='id',sequence='seq',dependency_ids=array('id')}
specs.bom=object{id='id',product_id='id',unit_id='id',output_qty='pos',components=array(specs.component),operations=array(specs.operation)}
specs.demand=object{id='id',mo_id='id',product_id='id',unit_id='id',demand_qty='qty',remaining_demand_qty='qty',reserved_qty='qty',picked_qty='qty',posted_consumed_qty='qty',unreserved_qty='qty',forecast_qty='finite?',availability_state='str?',source_location_id='id'}
specs.stock=object{product_id='id',location_id='id',unit_id='id',on_hand_qty='finite',reserved_qty='qty',free_qty='finite'}
local root=object{meta=specs.meta,units=array(specs.unit),products=array(specs.product),work_centers=array(specs.center),manufacturing_orders=array(specs.mo),work_orders=array(specs.wo),boms=array(specs.bom),material_demands=array(specs.demand),stock=array(specs.stock)}
local function check(v,s,shape,path)
  path=path or '$'
  if type(s)=='string' then
    local nullable=s:sub(-1)=='?'; local kind=nullable and s:sub(1,-2) or s
    if v==nil then assert(nullable and (not shape or shape.kind=='null'),path..' null/missing'); return end
    assert(predicates[kind](v),path..' invalid '..kind)
    if shape then
      local expected=({id='number',seq='number',qty='number',pos='number',finite='number',bool='boolean',one='number',twenty='number'})[kind] or 'string'
      assert(shape.kind==expected,path..' wrong JSON type')
      if kind=='id' or kind=='seq' or kind=='one' or kind=='twenty' then assert(shape.integer,path..' integer token required') end
    end
    return
  end
  assert(type(v)=='table',path..' table required')
  if s.item then
    assert(not shape or shape.kind=='array',path..' array required')
    local count=shape and #shape.items or #v
    for k in pairs(v) do assert(integer(k,1) and k<=count,path..' array index') end
    for i=1,count do check(v[i],s.item,shape and shape.items[i],path..'['..i..']') end
  else
    assert(not shape or shape.kind=='object',path..' object required')
    for k in pairs(v) do assert(s.fields[k],path..' unknown field '..tostring(k)) end
    if shape then for k in pairs(shape.fields) do assert(s.fields[k],path..' unknown field '..k) end end
    for k,sub in pairs(s.fields) do
      if shape then assert(shape.fields[k],path..' missing '..k) end
      check(v[k],sub,shape and shape.fields[k],path..'.'..k)
    end
  end
end
local function index(rows)
  local out={}; for _,r in ipairs(rows) do assert(not out[r.id],'duplicate ID'); out[r.id]=r end; return out
end
local function ref(rows,id) assert(rows[id],'unresolved reference'); return rows[id] end
local function acyclic(rows)
  local degrees,followers,count={}, {},0
  for id,row in pairs(rows) do
    count=count+1; degrees[id]=#row.dependency_ids; local seen={}
    for _,dep in ipairs(row.dependency_ids) do
      ref(rows,dep); assert(not seen[dep],'duplicate dependency'); seen[dep]=true
      followers[dep]=followers[dep] or {}; table.insert(followers[dep],id)
    end
  end
  local queue={}; for id,n in pairs(degrees) do if n==0 then queue[#queue+1]=id end end
  local at=1
  while at<=#queue do
    for _,id in ipairs(followers[queue[at]] or {}) do degrees[id]=degrees[id]-1; if degrees[id]==0 then queue[#queue+1]=id end end
    at=at+1
  end
  assert(#queue==count,'cyclic dependencies')
end
local function validate(v,shape)
  check(v,root,shape)
  local shapes={}
  local function collect(value,node)
    if type(value)~='table' or not node then return end
    shapes[value]=node.fields or node.items
    for key,child in pairs(node.fields or node.items or {}) do collect(value[key],child) end
  end
  collect(v,shape)
  local function number(row,name)
    local node=shapes[row] and shapes[row][name]
    return node and node.raw and decimal.parse(node.raw) or decimal.number(row[name])
  end
  assert(v.meta.scope_id=='company:'..string.format('%.0f',v.meta.company_id)..'/warehouse:'..string.format('%.0f',v.meta.warehouse_id),'scope mismatch')
  local units,products,centers,mos,wos=index(v.units),index(v.products),index(v.work_centers),index(v.manufacturing_orders),index(v.work_orders)
  index(v.boms); index(v.material_demands)
  local function quantities(row,names)
    local unit=ref(units,row.unit_id)
    for _,name in ipairs(names) do if row[name]~=nil then
      assert(decimal.rounded(number(row,name),number(unit,'rounding')),'quantity rounding')
    end end
  end
  local function product_unit(row) assert(ref(products,row.product_id).unit_id==row.unit_id,'product unit mismatch') end
  local function consistent(row,actual,first,second,clamp)
    assert(decimal.consistent(number(row,actual),number(row,first),number(row,second),number(ref(units,row.unit_id),'rounding'),clamp),'inconsistent quantity')
  end
  for _,p in ipairs(v.products) do ref(units,p.unit_id) end
  for _,mo in ipairs(v.manufacturing_orders) do product_unit(mo); quantities(mo,{'requested_qty','reported_qty','posted_qty'}) end
  local operations,product_ops={},{}
  for _,bom in ipairs(v.boms) do
    product_unit(bom); quantities(bom,{'output_qty'}); local local_ops=index(bom.operations); acyclic(local_ops)
    product_ops[bom.product_id]=product_ops[bom.product_id] or {}
    for _,op in ipairs(bom.operations) do ref(centers,op.center_id); assert(not operations[op.id],'duplicate operation'); operations[op.id]=op; product_ops[bom.product_id][op.id]=true end
    for _,c in ipairs(bom.components) do product_unit(c); quantities(c,{'quantity'}); if c.operation_id then ref(local_ops,c.operation_id) end end
  end
  acyclic(wos)
  for _,wo in ipairs(v.work_orders) do
    local mo=ref(mos,wo.mo_id); ref(centers,wo.center_id); ref(operations,wo.operation_id)
    assert(product_ops[mo.product_id] and product_ops[mo.product_id][wo.operation_id],'operation product mismatch')
    assert(wo.unit_id==mo.unit_id,'WO unit mismatch')
    for _,dep in ipairs(wo.dependency_ids) do assert(ref(wos,dep).mo_id==wo.mo_id,'WO predecessor MO mismatch') end
    quantities(wo,{'output_qty','carried_qty','required_qty','remaining_qty','ready_qty'})
  end
  for _,d in ipairs(v.material_demands) do
    ref(mos,d.mo_id); product_unit(d); quantities(d,{'demand_qty','remaining_demand_qty','reserved_qty','picked_qty','posted_consumed_qty','unreserved_qty','forecast_qty'})
    consistent(d,'unreserved_qty','remaining_demand_qty','reserved_qty',true)
  end
  local stock={}
  for _,s in ipairs(v.stock) do
    product_unit(s); quantities(s,{'on_hand_qty','reserved_qty','free_qty'}); consistent(s,'free_qty','on_hand_qty','reserved_qty',false)
    stock[s.product_id]=stock[s.product_id] or {}
    assert(not stock[s.product_id][s.location_id],'duplicate stock'); stock[s.product_id][s.location_id]=true
  end
end
function M.validate(v,shape)
  local ok,err=pcall(validate,v,shape)
  if ok then return true,nil end
  return false,tostring(err)
end
local base={version='one',token='text',hello_nonce='text',session_id='uuid',source_id='uuid',scope_id='scope',type='text'}
local wire_fields={hello={challenge_id='uuid?'},hello_challenge={challenge_id='uuid'},hello_ack={},snapshot_begin={revision='id',snapshot_id='text',chunk_count='id',byte_length='id'},snapshot_chunk={revision='id',snapshot_id='text',index='seq',data='str'},chunk_ack={snapshot_id='text',index='seq'},snapshot_applied={revision='id',snapshot_id='text'},heartbeat={sequence='seq',source_read_at='utc?',source_age_seconds='qty?',source_ok='bool',last_success_at='utc?',last_error='str?',refreshing='bool'},heartbeat_ack={sequence='seq'},resync_request={}}
function M.wire(v,shape)
  local ok,err=pcall(function()
    assert(type(v)=='table' and wire_fields[v.type],'unknown wire message')
    assert(not shape or shape.byte_length<=1024,'UDP envelope exceeds 1024 bytes')
    local fields={}; for k,s in pairs(base) do fields[k]=s end
    for k,s in pairs(wire_fields[v.type]) do fields[k]=s end
    if v.type=='hello' then fields.session_id='uuid?'; fields.source_id='uuid?'; fields.scope_id='scope?' end
    if v.type=='hello_challenge' then fields.session_id='uuid?' end
    -- Wire defaults may be omitted, unlike required nullable business fields.
    local adjusted=shape and {kind=shape.kind,fields={}} or nil
    if adjusted then
      for k,s in pairs(shape.fields or {}) do adjusted.fields[k]=s end
      local defaults=v.type=='hello' and {'session_id','source_id','scope_id','challenge_id'} or v.type=='hello_challenge' and {'session_id'} or v.type=='heartbeat' and {'last_success_at','last_error','refreshing'} or {}
      for _,k in ipairs(defaults) do if not adjusted.fields[k] then adjusted.fields[k]={kind=k=='refreshing' and 'boolean' or 'null'} end end
    end
    local values=v
    if v.type=='heartbeat' and v.refreshing==nil then
      assert(not shape or not shape.fields.refreshing,'refreshing cannot be null')
      values={}; for k,x in pairs(v) do values[k]=x end; values.refreshing=false
    end
    check(values,object(fields),adjusted)
    if v.type=='hello' then assert(v.session_id==nil and ((v.source_id==nil)==(v.scope_id==nil)),'hello binding') end
    if v.type=='hello_challenge' then assert(v.session_id==nil,'challenge session') end
    if v.chunk_count then assert(v.chunk_count<=512,'chunk count') end
    if v.byte_length then assert(v.byte_length<=262144,'snapshot byte length') end
    if v.index then assert(v.index<512,'chunk index') end
  end)
  if ok then return true,nil end
  return false,tostring(err)
end
return M
