-- Record JSON shape only: native helpers remain responsible for decoding values.
local M = {}
function M.inspect(text, decode)
  if type(text) ~= 'string' then return nil, 'JSON text required' end
  local at, size = 1, #text
  local function whitespace() local _,e=text:find('^[ \n\r\t]*',at); at=(e or at-1)+1 end
  local function quoted()
    assert(text:sub(at,at)=='"', 'JSON string required')
    local start=at; at=at+1
    while at<=size do
      local c=text:sub(at,at)
      if c=='"' then at=at+1; return text:sub(start,at-1) end
      if c=='\\' then at=at+2 else assert(c:byte()>=32,'JSON control character'); at=at+1 end
    end
    error('unterminated JSON string')
  end
  local value
  value=function(depth)
    assert(depth<=32,'JSON nesting limit'); whitespace()
    local c=text:sub(at,at)
    if c=='{' then
      at=at+1; whitespace(); local node={kind='object',fields={}}
      if text:sub(at,at)=='}' then at=at+1; return node end
      while true do
        local raw=quoted()
        local key=decode('{"key":'..raw..'}').key
        assert(type(key)=='string','invalid JSON key')
        whitespace(); assert(text:sub(at,at)==':','JSON colon required'); at=at+1
        node.fields[key]=value(depth+1); whitespace(); c=text:sub(at,at); at=at+1
        if c=='}' then break end
        assert(c==',','JSON comma required'); whitespace()
      end
      return node
    elseif c=='[' then
      at=at+1; whitespace(); local node={kind='array',items={}}
      if text:sub(at,at)==']' then at=at+1; return node end
      while true do
        node.items[#node.items+1]=value(depth+1); whitespace(); c=text:sub(at,at); at=at+1
        if c==']' then break end
        assert(c==',','JSON comma required')
      end
      return node
    elseif c=='"' then quoted(); return {kind='string'}
    end
    for _,literal in ipairs({'null','true','false'}) do
      if text:sub(at,at+#literal-1)==literal then
        at=at+#literal; return {kind=literal=='null' and 'null' or 'boolean'}
      end
    end
    local tail=text:sub(at)
    local raw=tail:match('^%-?%d+%.?%d*[eE][%+%-]?%d+') or tail:match('^%-?%d+%.%d+') or tail:match('^%-?%d+')
    assert(raw,'JSON value required')
    assert(not raw:match('^%-?0%d'),'JSON leading zero')
    at=at+#raw
    return {kind='number',integer=not raw:find('[%.eE]'),raw=raw}
  end
  local ok,node=pcall(value,1)
  if not ok then return nil, tostring(node) end
  whitespace(); if at<=size then return nil,'JSON trailing data' end
  node.byte_length=size
  return node
end
return M
