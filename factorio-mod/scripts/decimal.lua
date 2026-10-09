-- Exact decimal operations only for the three shared quantity invariants.
-- Values are signed digits * 10^power; no source quantity is narrowed.
local M={}
local function trim(s) s=s:gsub('^0+',''); return s=='' and '0' or s end
local function magnitude(a,b) a,b=trim(a),trim(b); if #a~=#b then return #a<#b and -1 or 1 end; return a==b and 0 or (a<b and -1 or 1) end
local function digit(s,offset) if offset>=#s then return 0 end; return tonumber(s:sub(#s-offset,#s-offset)) end
local function add(a,b)
  local out,carry={},0
  for i=0,math.max(#a,#b)-1 do
    local n=digit(a,i)+digit(b,i)+carry
    out[#out+1]=tostring(n%10); carry=math.floor(n/10)
  end
  if carry>0 then out[#out+1]=tostring(carry) end
  return table.concat(out):reverse()
end
local function subtract(a,b)
  assert(magnitude(a,b)>=0,'decimal magnitude subtraction')
  local out,borrow={},0
  for i=0,#a-1 do
    local n=digit(a,i)-digit(b,i)-borrow
    borrow=n<0 and 1 or 0; if n<0 then n=n+10 end
    out[#out+1]=tostring(n)
  end
  return trim(table.concat(out):reverse())
end
local function normalize(sign,digits,power)
  digits=trim(digits); if digits=='0' then return {sign=0,digits='0',power=0} end
  local tail=digits:match('0+$') or ''; digits=digits:sub(1,#digits-#tail)
  return {sign=sign,digits=digits,power=power+#tail}
end
function M.parse(raw)
  local mantissa,exponent=raw:match('^(.-)[eE]([%+%-]?%d+)$')
  mantissa=mantissa or raw; exponent=tonumber(exponent) or 0
  local sign=1; if mantissa:sub(1,1)=='-' then sign=-1; mantissa=mantissa:sub(2) end
  local before,after=mantissa:match('^(%d+)%.(%d+)$')
  if not before then before,after=mantissa,'' end
  assert(before:match('^%d+$'),'decimal lexeme required')
  return normalize(sign,before..after,exponent-#after)
end
function M.number(v)
  assert(type(v)=='number' and v==v and v~=math.huge and v~=-math.huge,'finite decimal required')
  -- Find the shortest significant-decimal precision that roundtrips the value.
  for precision=1,17 do
    local raw=string.format('%.'..precision..'g',v)
    if tonumber(raw)==v then return M.parse(raw) end
  end
  error('decimal roundtrip unavailable')
end
local function align(a,b)
  local power=math.min(a.power,b.power)
  return a.digits..string.rep('0',a.power-power),b.digits..string.rep('0',b.power-power),power
end
local function difference(a,b)
  local x,y,power=align(a,b)
  if a.sign==0 then return normalize(-b.sign,y,power) end
  if b.sign==0 then return normalize(a.sign,x,power) end
  if a.sign~=b.sign then return normalize(a.sign,add(x,y),power) end
  if magnitude(x,y)>=0 then return normalize(a.sign,subtract(x,y),power) end
  return normalize(-a.sign,subtract(y,x),power)
end
local function remainder(a,b)
  local rem='0'
  for i=1,#a do
    rem=trim(rem..a:sub(i,i))
    while magnitude(rem,b)>=0 do rem=subtract(rem,b) end
  end
  return rem
end
function M.rounded(value,quantum)
  assert(quantum.sign>0,'positive quantum required')
  local numerator,denominator=align(value,quantum)
  local rem=remainder(numerator,denominator)
  local other=subtract(denominator,rem)
  if magnitude(other,rem)<0 then rem=other end
  return magnitude(rem..'00000000',denominator)<=0
end
function M.consistent(actual,first,second,quantum,clamp)
  local expected=difference(first,second)
  if clamp and expected.sign<0 then expected=M.parse('0') end
  local distance=difference(actual,expected)
  local tolerance={sign=1,digits=quantum.digits,power=quantum.power-8}
  local x,y=align(distance,tolerance)
  return magnitude(x,y)<=0
end
return M
