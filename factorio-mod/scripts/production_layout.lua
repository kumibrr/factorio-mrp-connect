-- Compact order cells: serial work stays straight, parallel work gets a row.
local M={}
function M.plan(lane)
  local positions,depths,rows={}, {}, {}
  local max_row,max_depth=0,0
  local outgoing,degree={},0
  for _,op in ipairs(lane.operations) do
    degree=math.max(degree,#op.dependency_ids)
    for _,parent in ipairs(op.dependency_ids) do outgoing[parent]=(outgoing[parent] or 0)+1 end
  end
  for _,count in pairs(outgoing) do degree=math.max(degree,count) end
  local stride=math.max(24,(degree+3)*4)
  local spacing=degree>1 and 24 or 16
  for _,op in ipairs(lane.operations) do
    local depth,preferred=0,nil
    for _,parent in ipairs(op.dependency_ids) do
      depth=math.max(depth,depths[parent]+1)
      preferred=math.min(preferred or math.huge,positions[parent].y/stride)
    end
    rows[depth]=rows[depth] or {}
    local row=preferred or 0
    if rows[depth][row] then row=0;while rows[depth][row] do row=row+1 end end
    rows[depth][row]=true;depths[op.id]=depth
    positions[op.id]={x=depth*spacing,y=row*stride}
    max_row=math.max(max_row,row);max_depth=math.max(max_depth,depth)
  end
  return {positions=positions,height=max_row*stride+math.max(32,degree*4+12),width=max_depth*spacing+16}
end
return M
