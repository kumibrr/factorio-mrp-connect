local vm=require('scripts.view_model')
local production=require('scripts.production')
local M={}
local function label(parent,value,color,name)
  local e=parent.add{type='label',caption=value,name=name}
  e.style.single_line=false;e.style.maximal_width=850
  if color then e.style.font_color=color end
  return e
end
local function synchronization(view)
  return {'Synchronization: '..view.sync.label..' | Source read '..view.sync.source_read_at,
    'Reported source age '..view.sync.source_age_label..' seconds | Last successful source read '..view.sync.last_success_at,
    'Source error '..view.sync.error..' | Refreshing '..tostring(view.sync.refreshing)..' | Connection verified '..tostring(view.sync.verified),
    'Transport: '..view.sync.transport_label..' | Stage '..view.sync.stage..' | Restart reason '..view.sync.restart_reason,
    'Source freshness: '..view.sync.freshness_label..' | '..(view.sync.source_failed and 'Source read failed' or 'No current source failure reported')}
end
local function progress(parent,value,caption,color)
  label(parent,caption,color)
  if value~=nil then
    local e=parent.add{type='progressbar',value=math.max(0,math.min(1,value))}
    e.style.width=250;e.style.color=color
  end
end
function M.ensure_button(player)
  if not player.gui.top.fc_open then player.gui.top.add{type='button',name='fc_open',caption='Odoo factory'} end
end
local function order_detail(parent,row,history)
  local order,op=row.order,row.operation
  local frame=parent.add{type='frame',direction='vertical'}
  label(frame,order.reference..' — '..order.product..' | MO '..order.state_label..' (raw '..vm.plain(order.raw_state)..')',history and vm.palette.idle or vm.palette.ready)
  label(frame,order.quantity_label);label(frame,order.dates_label);label(frame,order.readiness_label)
  label(frame,'WO '..string.format('%d',op.id)..' | Operation '..string.format('%d',op.operation_id)..' | '..op.state_label..' (raw '..vm.plain(op.raw_state)..')')
  progress(frame,op.quantity_ratio,'Operation quantity: '..op.quantity_label,history and vm.palette.idle or vm.palette.running)
  local timer=frame.add{type='label',name='fc_timer_'..string.format('%d',op.id),
    caption='Operation time: '..(op.running_label or production.timing(op)),tags={fc_timer_id=op.id}}
  timer.style.font_color=vm.palette.ready;timer.style.single_line=false;timer.style.maximal_width=850
  if op.time_ratio~=nil then
    local bar=frame.add{type='progressbar',value=math.max(0,math.min(1,op.time_ratio))}
    bar.style.width=250;bar.style.color=vm.palette.ready
  end
  label(frame,'Predecessors: '..op.dependency_label,op.raw_state=='blocked' and vm.palette.attention or vm.palette.idle)
  label(frame,'MO material evidence (applies to this order; no per-operation assignment available)',vm.palette.attention)
  if #order.materials==0 then label(frame,'Material evidence unavailable') end
  for _,material in ipairs(order.materials) do label(frame,material.label,material.warning and vm.palette.attention or vm.palette.idle) end
  if #order.siblings>1 then
    label(frame,'Source group '..string.format('%d',order.group_id)..' siblings (separate MOs)',vm.palette.idle)
    for _,sibling in ipairs(order.siblings) do
      label(frame,sibling.reference..' | '..(sibling.terminal and sibling.state_label or 'Outstanding')..' | '..sibling.product..' | '..sibling.quantity_label..' | Backorder sequence '..vm.number(sibling.backorder_sequence))
    end
  end
  label(frame,'Odoo record URL — select and copy into your browser')
  local field=frame.add{type='text-box',name='fc_record_'..string.format('%d',op.id),text=order.record_url,tags={fc_record=true}}
  field.read_only=true;field.word_wrap=false;field.style.width=800;field.style.height=36
end
function M.show(player,view,center_id)
  local previous=player.gui.screen.fc_panel
  local location=previous and previous.valid and previous.location or nil
  if previous then previous.destroy() end
  local panel=player.gui.screen.add{type='frame',name='fc_panel',direction='vertical',caption='Odoo operational factory',tags={center_id=center_id,revision=view.revision}}
  if location then panel.location=location else panel.auto_center=true end
  local controls=panel.add{type='flow',name='fc_controls',direction='horizontal'}
  controls.add{type='button',name='fc_close',caption='Close'}
  controls.add{type='button',name='fc_jump',caption='Jump to production lane',enabled=view.surface_available==true}
  controls.add{type='button',name='fc_repair',caption='Local re-pair…'}
  for i,text in ipairs(synchronization(view)) do label(panel,text,nil,'fc_sync_'..i) end
  label(panel,'Freshness is reported by the bridge; paused game time does not establish wall-clock freshness.',vm.palette.idle)
  local warnings=panel.add{type='flow',name='fc_warnings',direction='vertical'}
  for _,warning in ipairs(view.warnings) do label(warnings,'Data/display warning: '..warning,vm.palette.attention) end
  local scroll=panel.add{type='scroll-pane'}
  scroll.style.maximal_height=600;scroll.style.minimal_width=900
  local centers=scroll.add{type='flow',direction='horizontal'}
  for _,key in ipairs(view.center_ids) do
    centers.add{type='button',name='fc_center_'..string.format('%d',key),caption=view.centers[key].display_name,tags={fc_center_id=key}}
  end
  local center=view.centers[center_id]
  if center then
    label(scroll,center.display_name..' | Center '..center.raw_state_label..' (raw '..vm.plain(center.raw_state)..')')
    label(scroll,'Running '..center.running_count,vm.palette.running);label(scroll,'Ready '..center.ready_count,vm.palette.ready)
    label(scroll,'Dependency waiting '..center.waiting_count..' | MO material warnings '..center.material_warning_count,vm.palette.attention)
    label(scroll,'Active orders')
    if #center.orders==0 then label(scroll,'No active orders',vm.palette.idle) end
    for _,row in ipairs(center.orders) do order_detail(scroll,row,false) end
    label(scroll,'History — completed and cancelled; excluded from active queues',vm.palette.idle)
    for _,row in ipairs(center.history) do order_detail(scroll,row,true) end
  else label(scroll,'Select a work center to inspect orders.') end
  label(scroll,'Stock evidence by product and location (separate from operation output)',vm.palette.idle)
  local products={};for product_id in pairs(view.stock) do products[#products+1]=product_id end;table.sort(products)
  for _,product_id in ipairs(products) do for _,stock in ipairs(view.stock[product_id]) do label(scroll,stock.label) end end
  label(scroll,'Legend')
  label(scroll,'● Green — running orders',vm.palette.running);label(scroll,'● Blue — operation ready',vm.palette.ready)
  label(scroll,'● Amber — dependency or MO material attention',vm.palette.attention);label(scroll,'● Gray — idle / terminal history',vm.palette.idle)
  label(scroll,'Production lanes move visual workpieces: raw-material box → TODO belt → machines → production-complete box. Full belts stop inserters; ready/blocked work waits on its belt. Machines release only Odoo-reported output.',vm.palette.idle)
  label(scroll,'Workpiece markers represent batch quantities (scaled above 200 markers), not stock or individual BOM components. Completion boxes show operation output; posted stock is separate. Overview belts show intended BOM links.',vm.palette.idle)
  label(scroll,'Elapsed and expected time come from Odoo. Remaining time is an estimate. Observed running uses unpaused game time while synchronization is healthy.',vm.palette.idle)
  return panel
end
function M.update(player,view)
  local panel=player.gui.screen.fc_panel
  if not panel or not panel.valid then return end
  if panel.tags.revision~=view.revision and not panel.tags.confirming_repair then M.show(player,view,panel.tags.center_id);return end
  for i,text in ipairs(synchronization(view)) do panel['fc_sync_'..i].caption=text end
  panel.fc_controls.fc_jump.enabled=view.surface_available==true
  panel.fc_warnings.clear()
  for _,warning in ipairs(view.warnings) do label(panel.fc_warnings,'Data/display warning: '..warning,vm.palette.attention) end
  local timers={}
  for _,order in pairs(view.orders) do for _,op in ipairs(order.operations) do timers[op.id]=op end end
  local function update_timers(parent)
    for _,child in pairs(parent.children) do
      local key=child.tags and child.tags.fc_timer_id
      if key and timers[key] then child.caption='Operation time: '..(timers[key].running_label or production.timing(timers[key])) end
      update_timers(child)
    end
  end
  update_timers(panel)
end
function M.handle(player,event,view)
  local e=event.element
  if not e or not e.valid then return end
  local panel=player.gui.screen.fc_panel
  if e.name=='fc_open' then M.show(player,view,view.center_ids[1])
  elseif e.name=='fc_close' then if panel then panel.destroy() end
  elseif e.tags and e.tags.fc_center_id then M.show(player,view,e.tags.fc_center_id)
  elseif e.tags and e.tags.fc_record then e.focus();e.select_all()
  elseif e.name=='fc_jump' and view.surface_available and game.surfaces['odoo-factory'] then
    local center_id=panel and panel.tags.center_id
    local target=view.production_positions and view.production_positions[center_id] or {x=-5,y=0}
    local surface=game.surfaces['odoo-factory']
    local character=player.character
    if character and character.valid then target=surface.find_non_colliding_position(character.name,target,20,0.5) end
    if target then player.teleport(target,surface) end
  elseif e.name=='fc_repair' and panel then
    if panel.tags.confirming_repair then return end
    local tags=panel.tags;tags.confirming_repair=true;panel.tags=tags
    label(panel,'Confirm local re-pair: clear this generated view and its saved source binding. Odoo business data is untouched.',vm.palette.attention)
    local controls=panel.add{type='flow',name='fc_repair_confirmation'}
    controls.add{type='button',name='fc_confirm_repair',caption='Confirm local re-pair'}
    controls.add{type='button',name='fc_cancel_repair',caption='Cancel'}
  elseif e.name=='fc_cancel_repair' and panel then M.show(player,view,panel.tags.center_id)
  elseif e.name=='fc_confirm_repair' and panel and panel.tags.confirming_repair and e.parent==panel.fc_repair_confirmation then return 'reset' end
end
return M
