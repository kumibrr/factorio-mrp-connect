local cjson=require('cjson')
return {
  native_float_formatting_cannot_corrupt_source_scope_or_record_links=function()
    local original=string.format
    string.format=function(format,value,...)
      if format=='%.0f' and value==9007199254740991 then return '9007199254740992' end
      return original(format,value,...)
    end
    local ok,err=pcall(function()
      local f=require('view_fixtures')
      local snapshot=f.snapshot()
      snapshot.meta.company_id=9007199254740991
      snapshot.meta.scope_id='company:9007199254740991/warehouse:1'
      assert(require('scripts.validation').validate(snapshot),'safe source scope must validate')
      local mo=snapshot.manufacturing_orders[1]
      local prior=mo.id;mo.id=9007199254740991
      for _,wo in ipairs(snapshot.work_orders) do if wo.mo_id==prior then wo.mo_id=mo.id end end
      snapshot.work_centers[2].id=9007199254740991
      for _,wo in ipairs(snapshot.work_orders) do if wo.center_id==2 then wo.center_id=9007199254740991 end end
      local view=require('scripts.view_model').build(snapshot,f.healthy())
      assert(view.orders[9007199254740991].record_url:find('/9007199254740991',1,true))
      f.engine();local player=f.player()
      require('scripts.gui').show(player,view,9007199254740991)
      assert(f.find(player.gui.screen,'fc_center_9007199254740991'))
    end)
    string.format=original
    assert(ok,err)
  end,
  outgoing_safe_integer_boundary_survives_native_rounding=function()
    local ok,codec=pcall(require,'scripts.wire_encode')
    assert(ok and codec.encode,'wire codec must preserve exact safe integer fields')
    local token='quoted"sequence":9007199254740991, braces{} slash\\ café'
    local row={version=1,type='heartbeat_ack',token=token,sequence=9007199254740991}
    local encoded=codec.encode(row,function(fields)
      -- Model the observed native serializer bug if a numeric field escapes.
      if fields.sequence then return '{"sequence":9007199254740992}' end
      return cjson.encode(fields)
    end)
    assert(encoded:find('"sequence":9007199254740991',1,true))
    local decoded=cjson.decode(encoded)
    assert(decoded.sequence==9007199254740991 and decoded.version==1)
    assert(decoded.token==token)
    assert(row.sequence==9007199254740991)
  end,
  invalid_outgoing_integer_cannot_reach_socket=function()
    local codec=require('scripts.wire_encode')
    for _,value in ipairs({-1,1.5,9007199254740992,math.huge}) do
      local ok=pcall(codec.encode,{version=1,sequence=value},cjson.encode)
      assert(not ok)
    end
    local text=codec.encode({version=1,index=0,revision=9007199254740991,type='chunk_ack'},cjson.encode)
    assert(text:find('"index":0',1,true) and text:find('"revision":9007199254740991',1,true))
  end
}
