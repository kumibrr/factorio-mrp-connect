local f=require('fixtures')
local M={}
function M.snapshot() return f.native(f.read('contracts/fixtures/pumpworks-v1.json')) end
function M.module(name)
  local ok,m=pcall(require,'scripts.'..name)
  assert(ok and type(m)=='table',name..' must implement the operator view')
  return m
end
function M.healthy()
  return {verified=true,connected=true,health={source_ok=true,source_read_at='2026-10-09T12:00:00Z',source_age_seconds=0,refreshing=false}}
end
function M.engine()
  local entities,renders={},{}
  local surface={name='odoo-factory',valid=true}
  surface.create_entity=function(spec)
    local e={name=spec.name,position=spec.position,direction=spec.direction,belt_to_ground_type=spec.type,valid=true,surface=surface,unit_number=#entities+1}
    local inventories={}
    e.set_recipe=function(recipe) e.recipe=recipe end
    e.get_recipe=function() return e.recipe and {name=e.recipe},{name='normal'} end
    e.get_inventory=function(kind)
      if not inventories[kind] then
        local items={};local inventory={}
        inventory.get_item_count=function(name) return items[name] or 0 end
        inventory.insert=function(stack) items[stack.name]=(items[stack.name] or 0)+stack.count;return stack.count end
        inventory.remove=function(stack)
          local n=math.min(items[stack.name] or 0,stack.count);items[stack.name]=(items[stack.name] or 0)-n;return n
        end
        inventory.is_empty=function() for _,n in pairs(items) do if n>0 then return false end end;return true end
        inventory.get_contents=function()
          local out={};for name,count in pairs(items) do if count>0 then out[#out+1]={name=name,count=count,quality='normal'} end end
          return out
        end
        inventories[kind]=inventory
      end
      return inventories[kind]
    end
    e.destroy=function() e.valid=false end
    entities[#entities+1]=e; return e
  end
  surface.can_place_entity=function(spec)
    for _,entity in ipairs(entities) do
      if entity.valid and entity.position.x==spec.position.x and entity.position.y==spec.position.y then return false end
    end
    return true
  end
  _G.game={surfaces={},create_surface=function() game.surfaces['odoo-factory']=surface;return surface end}
  _G.prototypes={entity={}}
  _G.rendering={}
  for _,method in ipairs({'draw_text','draw_line'}) do
    rendering[method]=function(spec)
      assert(spec.color==nil or type(spec.color)=='table','rendering color must be a table')
      local r={valid=true,text=spec.text,color=spec.color,target=spec.target}
      r.destroy=function() r.valid=false end
      renders[#renders+1]=r; return r
    end
  end
  _G.defines={direction={east=4,south=8,west=12,north=0},inventory={chest=1,assembling_machine_input=2,assembling_machine_output=3}}
  return surface,entities,renders
end
local function element(spec,parent)
  local e=setmetatable({valid=true,children={},style={},parent=parent},{__newindex=function(t,key,value)
    if key=='read_only' and t.type~='text-box' then error('Only callable on text-box.') end
    rawset(t,key,value)
  end})
  for k,v in pairs(spec or {}) do e[k]=v end
  e.add=function(s)
    local child=element(s,e); e.children[#e.children+1]=child
    if s.name then e[s.name]=child end
    return child
  end
  e.destroy=function()
    for _,child in ipairs(e.children) do child.destroy() end
    e.valid=false;if parent and e.name then parent[e.name]=nil end
  end
  e.clear=function() for _,child in ipairs(e.children) do child.destroy() end;e.children={} end
  e.auto_center=false
  e.select_all=function() e.selected=true end
  e.focus=function() e.focused=true end
  return e
end
function M.player()
  local p={index=1,gui={screen=element(),top=element()},surface={name='nauvis'}}
  p.teleport=function(position,surface) p.position=position; p.surface=surface; return true end
  return p
end
function M.texts(root)
  local out={}
  local function visit(e)
    if not e.valid then return end
    if type(e.caption)=='string' then out[#out+1]=e.caption end
    if type(e.text)=='string' then out[#out+1]=e.text end
    for _,child in ipairs(e.children) do visit(child) end
  end
  visit(root); return table.concat(out,'\n')
end
function M.find(root,name)
  if not root.valid then return nil end
  if root.name==name then return root end
  for _,child in ipairs(root.children) do local e=M.find(child,name); if e then return e end end
end
return M
