-- Pure tile routing. Dedicated belts never merge with another order's route.
local M={}
local directions={{x=1,y=0,d=4},{x=0,y=1,d=8},{x=-1,y=0,d=12},{x=0,y=-1,d=0}}
local function key(x,y) return x..':'..y end
local function state(x,y,d,forced) return key(x,y)..':'..d..':'..tostring(forced or false) end
local function isolated_tunnel(node,d,distance,occupied)
  for offset=-9,distance+9 do
    local other=occupied[key(node.x+d.x*offset,node.y+d.y*offset)]
    if other and other.type and other.direction==d.d then return false end
  end
  return true
end
local function visited(node,x,y)
  while node do
    if node.x==x and node.y==y then return true end
    node=node.previous
  end
  return false
end
local function push(heap,node)
  local i=#heap+1
  while i>1 do
    local parent=math.floor(i/2)
    if heap[parent].score<=node.score then break end
    heap[i]=heap[parent];i=parent
  end
  heap[i]=node
end
local function pop(heap)
  local first,last=heap[1],table.remove(heap)
  if #heap>0 then
    local i=1
    while i*2<=#heap do
      local child=i*2
      if child<#heap and heap[child+1].score<heap[child].score then child=child+1 end
      if last.score<=heap[child].score then break end
      heap[i]=heap[child];i=child
    end
    heap[i]=last
  end
  return first
end
function M.route(start,finish,occupied)
  if occupied[key(start.x,start.y)] or occupied[key(finish.x,finish.y)] then return nil,'occupied route endpoint' end
  -- Occupancy is fixed during a search; different directional states revisit
  -- the same tiles frequently.
  local clearance={}
  local function clear(x,y)
    local k=key(x,y)
    if clearance[k]~=nil then return clearance[k] end
    if occupied[k] then clearance[k]=false;return false end
    for _,d in ipairs(directions) do
      local other=occupied[key(x+d.x,y+d.y)]
      if other and other.kind=='belt' and other.type~='input' then
        local direction=other.direction
        if direction==(d.d+8)%16 then clearance[k]=false;return false end
      end
    end
    clearance[k]=true;return true
  end
  if not clear(start.x,start.y) or not clear(finish.x,finish.y) then return nil,'route endpoint receives another belt' end
  local heap,best={},{}
  local initial={x=start.x,y=start.y,d=4,cost=0}
  initial.score=math.abs(start.x-finish.x)+math.abs(start.y-finish.y)
  push(heap,initial);best[state(initial.x,initial.y,initial.d)]=0
  local limit=0
  while #heap>0 and limit<60000 do
    local node=pop(heap)
    if node.cost==best[state(node.x,node.y,node.d,node.forced)] then
      limit=limit+1
      if node.x==finish.x and node.y==finish.y then
        local reversed={};local current=node
        while current.previous do reversed[#reversed+1]=current;current=current.previous end
        local out={};local x,y=start.x,start.y;local previous_jump,previous_direction
        for i=#reversed,1,-1 do
          local step=reversed[i]
          local underground=previous_jump or step.jump
          out[#out+1]={name=underground and 'express-underground-belt' or 'transport-belt',position={x=x,y=y},
            direction=previous_jump and previous_direction or step.d,type=previous_jump and 'output' or (step.jump and 'input' or nil)}
          x,y=step.x,step.y;previous_jump=step.jump;previous_direction=step.d
        end
        out[#out+1]={name=previous_jump and 'express-underground-belt' or 'transport-belt',position={x=x,y=y},
          direction=previous_jump and previous_direction or 4,type=previous_jump and 'output' or nil}
        return out
      end
      local function candidate(x,y,d,jump)
        if not (x==finish.x and y==finish.y and d.d~=4) then
          local cost=node.cost+(jump and (math.abs(x-node.x)+math.abs(y-node.y)+2) or 1)+(node.d~=d.d and 0.25 or 0)
          local k=state(x,y,d.d,jump)
          -- Walk the path history only when this candidate can improve a state.
          -- Rejected costs cannot enter the heap, regardless of their history.
          if (not best[k] or cost<best[k]) and not visited(node,x,y) then
            best[k]=cost
            push(heap,{x=x,y=y,d=d.d,forced=jump,cost=cost,score=cost+1.5*(math.abs(x-finish.x)+math.abs(y-finish.y)),previous=node,jump=jump})
          end
        end
      end
      for _,d in ipairs(directions) do
        if not node.forced or node.d==d.d then
          local x,y=node.x+d.x,node.y+d.y
          if clear(x,y) then candidate(x,y,d,false)
          elseif node.previous and not node.forced and node.d==d.d then
            local crossed=false
            for distance=1,9 do
              local obstacle=occupied[key(node.x+d.x*distance,node.y+d.y*distance)]
              crossed=crossed or obstacle~=nil
              local landing_x,landing_y=node.x+d.x*distance,node.y+d.y*distance
              if distance>=4 and crossed and clear(landing_x,landing_y) and isolated_tunnel(node,d,distance,occupied) then
                candidate(landing_x,landing_y,d,true)
              end
            end
          end
        end
      end
    end
  end
  return nil,limit>=60000 and 'routing search limit' or 'no isolated route'
end
return M
