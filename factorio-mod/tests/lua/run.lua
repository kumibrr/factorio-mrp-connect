package.path = '/repo/factorio-mod/?.lua;/repo/factorio-mod/tests/lua/?.lua;' .. package.path
local suites = arg[1] and {arg[1]} or {'test_receiver', 'test_state', 'test_layout', 'test_view_model', 'test_surface', 'test_gui', 'test_control', 'test_wire_encode'}
local passed, failed = 0, 0
for _, name in ipairs(suites) do
  local cases = require(name)
  local names = {}
  for key in pairs(cases) do names[#names+1] = key end
  table.sort(names)
  for _, key in ipairs(names) do
    local ok, err = pcall(cases[key])
    if ok then passed = passed + 1; print('PASS '..key)
    else failed = failed + 1; print('FAIL '..key..': '..tostring(err)) end
  end
end
print(string.format('%d passed, %d failed', passed, failed))
os.exit(failed == 0 and 0 or 1)
