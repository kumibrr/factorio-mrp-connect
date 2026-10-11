local f=require('view_fixtures')
return {
  machine_panel_contains_only_its_operation_and_stays_open_for_skin_selection=function()
    local p=f.player();local gui=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy());v.revision=7
    gui.show_machine(p,v,{center_id=2,mo_id=6,op_id=14})
    local panel=p.gui.screen.fc_machine_panel;local text=f.texts(panel)
    assert(not p.gui.screen.fc_panel,'opening a machine must not open the global panel')
    assert(text:find('WO 14',1,true) and text:find(v.orders[6].reference,1,true))
    assert(not text:find(v.orders[7].reference,1,true),'another machine order leaked into the panel')
    assert(not f.find(panel,'fc_center_3') and not text:find('Stock evidence',1,true))
    local chooser=f.find(panel,'fc_machine_skin');assert(chooser and chooser.elem_type=='entity')
    v.orders[6].operations[1].running_label='Observed running 00:02 (game time)'
    gui.update(p,v)
    assert(panel.valid and chooser.valid and f.texts(panel):find('00:02',1,true))
    chooser.elem_value='modded-smelter'
    local action=gui.handle(p,{element=chooser},v)
    assert(action.action=='skin' and action.skin=='modded-smelter' and action.machine.op_id==14)
    gui.handle(p,{element=f.find(panel,'fc_machine_close')},v)
    assert(not p.gui.screen.fc_machine_panel)
  end,
  machine_revision_refresh_keeps_scope_and_closes_when_operation_disappears=function()
    local p=f.player();local gui=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy());v.revision=7
    gui.show_machine(p,v,{center_id=2,mo_id=6,op_id=14},'stone-furnace')
    local chooser=f.find(p.gui.screen.fc_machine_panel,'fc_machine_skin')
    v.revision=8;v.orders[6].operations[1].output_qty=3
    gui.update(p,v)
    assert(chooser.valid and chooser==f.find(p.gui.screen.fc_machine_panel,'fc_machine_skin'),'source refresh must not destroy the open skin picker')
    assert(p.gui.screen.fc_machine_panel.tags.machine.op_id==14)
    assert(f.find(p.gui.screen.fc_machine_panel,'fc_machine_skin').elem_value=='stone-furnace')
    v.orders[6]=nil;v.revision=9;gui.update(p,v)
    assert(not p.gui.screen.fc_machine_panel,'removed machine should not leave a stale panel')
  end,
  running_timer_refresh_preserves_record_selection=function()
    local p=f.player();local gui=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy());v.revision=7
    v.orders[6].operations[1].running_label='Elapsed 12 min | Expected 50 min | Remaining estimate 38 min | Observed running 00:01 (game time)'
    gui.show(p,v,2)
    local field=f.find(p.gui.screen,'fc_record_14');gui.handle(p,{element=field},v)
    assert(f.texts(p.gui.screen):find('Remaining estimate 38 min',1,true))
    v.orders[6].operations[1].running_label='Elapsed 12 min | Expected 50 min | Remaining estimate 38 min | Observed running 00:02 (game time)'
    gui.update(p,v)
    assert(f.texts(p.gui.screen):find('Observed running 00:02',1,true))
    assert(field.valid and field.selected)
  end,
  opening_factory_panel_uses_native_auto_center_property=function()
    local p=f.player();local gui=f.module('gui')
    local view=f.module('view_model').build(f.snapshot(),f.healthy())
    gui.ensure_button(p)
    gui.handle(p,{element=p.gui.top.fc_open},view)
    local panel=p.gui.screen.fc_panel
    assert(panel and panel.valid and panel.auto_center==true)
    assert(f.texts(panel):find('Machining',1,true))
  end,
  health_refresh_preserves_copyable_field_and_selected_text=function()
    local p=f.player();local m=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy());v.revision=7
    m.show(p,v,2);local field=f.find(p.gui.screen,'fc_record_17');m.handle(p,{element=field},v)
    local h=f.healthy();h.health.source_age_seconds=5;local next=f.module('view_model').build(f.snapshot(),h);next.revision=7
    m.update(p,next);assert(field.valid and field.selected and f.find(p.gui.screen,'fc_record_17')==field)
    assert(f.texts(p.gui.screen):find('Reported source age 5 seconds',1,true))
  end,
  operator_detail_exposes_evidence_history_legend_url_and_sync=function()
    local p=f.player();local m=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy())
    m.show(p,v,2);local text=f.texts(p.gui.screen)
    for _,value in ipairs({'Running 1','Ready 3','PUMP/MO/00007','Electric motor','Demand 8 Units','Reserved 2 Units','Unreserved 6 Units','Forecast Unknown','History','Posted 4 Units','Outstanding','Legend','2026-10-09T12:00:00Z','http://localhost:8069/odoo/mrp.production/7'}) do assert(text:find(value,1,true),value..' missing') end
    local field=f.find(p.gui.screen,'fc_record_17');assert(field.type=='text-box' and field.read_only)
    m.handle(p,{element=field},v);assert(field.selected)
  end,
  local_repair_requires_confirmation_and_surface_jump_is_local=function()
    local surface=f.engine();game.surfaces['odoo-factory']=surface;local p=f.player();local m=f.module('gui');local v=f.module('view_model').build(f.snapshot(),f.healthy());v.surface_available=true
    m.show(p,v,2)
    assert(m.handle(p,{element=f.find(p.gui.screen,'fc_repair')},v)~= 'reset')
    assert(f.texts(p.gui.screen):find('Confirm local re-pair',1,true))
    assert(m.handle(p,{element=f.find(p.gui.screen,'fc_confirm_repair')},v)=='reset')
    m.show(p,v,2);m.handle(p,{element=f.find(p.gui.screen,'fc_jump')},v)
    assert(p.surface.name=='odoo-factory')
  end,
  update_preserves_selected_center_and_shows_source_error=function()
    local p=f.player();local m=f.module('gui');m.show(p,f.module('view_model').build(f.snapshot(),f.healthy()),3)
    local h=f.healthy();h.health.source_ok=false;h.health.last_error='read_failed';h.health.last_success_at='2026-10-09T11:59:00Z'
    m.update(p,f.module('view_model').build(f.snapshot(),h))
    local text=f.texts(p.gui.screen);assert(text:find('Inspection',1,true) and text:find('read_failed',1,true) and text:find('2026-10-09T11:59:00Z',1,true))
  end,
  transport_and_stale_source_error_remain_visible_together=function()
    local p=f.player();local gui=f.module('gui');local h=f.healthy()
    h.verified=false;h.health.source_ok=false;h.health.source_age_seconds=91;h.health.last_error='read_failed'
    gui.show(p,f.module('view_model').build(f.snapshot(),h),2)
    local text=f.texts(p.gui.screen)
    for _,value in ipairs({'Resynchronizing','Stale source data','Source read failed','read_failed'}) do
      assert(text:find(value,1,true),value..' missing')
    end
  end
}
