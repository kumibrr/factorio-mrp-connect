local validation=require('scripts.validation')
local M={}
function M.init()
  storage.factorio_connect=storage.factorio_connect or {revision=0,entity_slots={}}
  return storage.factorio_connect
end
function M.get() return storage.factorio_connect end
local function copy(v)
  if type(v)~='table' then return v end
  local out={}; for k,x in pairs(v) do out[k]=copy(x) end; return out
end
local function normalize(snapshot)
  local v=copy(snapshot)
  local byid=function(a,b) return a.id<b.id end
  for _,name in ipairs({'units','products','work_centers','manufacturing_orders','work_orders','boms','material_demands'}) do table.sort(v[name],byid) end
  for _,bom in ipairs(v.boms) do
    table.sort(bom.operations,byid)
    table.sort(bom.components,function(a,b) if a.product_id~=b.product_id then return a.product_id<b.product_id end; return (a.operation_id or 0)<(b.operation_id or 0) end)
  end
  table.sort(v.stock,function(a,b) if a.product_id~=b.product_id then return a.product_id<b.product_id end; return a.location_id<b.location_id end)
  return v
end
function M.accept(snapshot,revision,shape)
  if type(revision)~='number' or revision%1~=0 or revision<1 or revision>9007199254740991 then return false,'invalid revision' end
  local ok,err=validation.validate(snapshot,shape); if not ok then return false,err end
  local current=M.get()
  if current and current.source_id and (current.source_id~=snapshot.meta.source_id or current.scope_id~=snapshot.meta.scope_id) then return false,'source binding mismatch' end
  if current and revision<=current.revision then return false,'revision does not advance' end
  local next_state={snapshot=normalize(snapshot),revision=revision,source_id=snapshot.meta.source_id,scope_id=snapshot.meta.scope_id,entity_slots=current and current.entity_slots or {}}
  storage.factorio_connect=next_state
  return true
end
function M.reset_binding()
  local current=M.get()
  storage.factorio_connect={revision=0,entity_slots=current and current.entity_slots or {}}
end
return M
