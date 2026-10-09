local f=require('view_fixtures')
return {
  new_center_does_not_move_existing_slots=function()
    local m=f.module('layout');local s=m.reconcile(f.snapshot().work_centers,{})
    assert(s[1].position.x==0 and s[2].position.x==24 and s[3].position.x==48 and s[4].position.x==72)
    local centers=f.snapshot().work_centers;centers[#centers+1]={id=5,name='New',code='NEW',active=true}
    local next=m.reconcile(centers,s);assert(next[2].position.x==24 and next[5].position.x==96)
    m.reconcile({},next);local again=m.reconcile(centers,next);assert(again[5].position.x==96)
  end
}
