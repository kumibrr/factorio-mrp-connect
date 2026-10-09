-- Native 2.0.77 JSON rounds the maximum safe integer. Keep native escaping for
-- strings while formatting only known envelope integer fields exactly.
local M={}
local integers={version=true,revision=true,index=true,sequence=true}
function M.encode(row,encode)
  local strings,numbers={},{}
  for key,value in pairs(row) do
    if integers[key] then
      assert(type(value)=='number' and value>=0 and value<=9007199254740991
        and value==math.floor(value),'invalid outgoing wire integer')
      numbers[#numbers+1]='"'..key..'":'..string.format('%d',value)
    else strings[key]=value end
  end
  table.sort(numbers)
  local text=encode(strings)
  assert(type(text)=='string','native encoder must return JSON text')
  -- Remove only surrounding whitespace and the object's final closing brace.
  -- Arbitrary braces, quotes, Unicode and numeric text in tokens remain intact.
  text=text:match('^%s*(.-)%s*$')
  assert(text:sub(1,1)=='{' and text:sub(-1)=='}','native encoder must return a JSON object')
  if #numbers==0 then return text end
  local body=text:sub(1,-2)
  local separator=body:match('^%s*{%s*$') and '' or ','
  return body..separator..table.concat(numbers,',')..'}'
end
return M
