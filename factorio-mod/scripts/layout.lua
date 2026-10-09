local M={}
local rank={MACH=1,ASSY=2,INSP=3,PACK=4}
function M.reconcile(work_centers,slots)
  slots=slots or {};local ordered,changes={},{}
  local next_index=0
  for _,slot in pairs(slots) do next_index=math.max(next_index,slot.index+1) end
  for _,center in ipairs(work_centers) do ordered[#ordered+1]=center end
  table.sort(ordered,function(a,b)
    local ar,br=rank[a.code] or 5,rank[b.code] or 5
    return ar==br and a.id<b.id or ar<br
  end)
  for _,center in ipairs(ordered) do
    if not slots[center.id] then
      slots[center.id]={index=next_index,position={x=(next_index%8)*24,y=math.floor(next_index/8)*28}}
      next_index=next_index+1;changes[#changes+1]=center.id
    end
  end
  return slots,changes
end
return M
