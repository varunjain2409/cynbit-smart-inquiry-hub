/* Cynbit Smart Inquiry Hub — visitor form logic */
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => [...el.querySelectorAll(s)];

const form=$('#inquiry'), result=$('#resultCard');
let service='';

/* service chips */
$('#serviceChips').addEventListener('click', e=>{
  const b=e.target.closest('button'); if(!b) return;
  $$('#serviceChips button').forEach(x=>x.classList.toggle('on', x===b));
  service=b.dataset.value;
  showErr('service', service?'' : 'Please choose a service track.');
});

/* form submit */
form.addEventListener('submit', async e=>{
  e.preventDefault();

  /* honeypot: bots fill hidden fields */
  if ($('#website_hp').value){ return; }

  const payload={
    name:$('#name').value, email:$('#email').value,
    company:$('#company').value, industry:$('#industry').value,
    service, budget:$('#budget').value, timeline:$('#timeline').value,
    message:$('#message').value
  };
  ['service'].forEach(clear); clear('name'); clear('email'); clear('message');

  const btn=$('#submitBtn'); btn.disabled=true;
  try{
    const res=await fetch('/api/inquire',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)});
    const data=await res.json();

    if(data.ok){ showResult(data); }
    else{ Object.entries(data.errors||{}).forEach(([k,v])=>showErr(k,v)); }
  }catch(err){
    showErr('message','Network hiccup — try again.');
  }finally{
    btn.disabled=false;
  }
});

/* client-side niceties */
$('#name')&&['name','email'].forEach(()=>{});
['name','email'].forEach(id=>{
  $('#'+id).addEventListener('input', ()=>clear(id));
});
$('#message').addEventListener('input', ()=>clear('message'));

function clear(k){ const el=$('[data-err-for="'+k+'"]'); if(el) el.textContent=''; }
function showErr(k,v){ const el=$('[data-err-for="'+k+'"]'); if(el) el.textContent=v||''; }

function showResult(d){
  result.hidden=false;
  $('#scoreVal').textContent=d.score;
  $('#tierBadge').textContent=d.tier;
  $('#tierBadge').className='tier '+d.tier.toLowerCase().replace(' ','');
  $('#intelText').textContent=d.intelligence;
  $('#srcBadge').textContent=d.summary_type;
  $('#nextStepText').textContent=d.next_step;
  $('#leadId').textContent='#'+d.id;
  $('#signalsList').innerHTML=(d.signals||[]).map(s=>'<li>'+s+'</li>').join('');

  /* animate ring: r=52 → circumference ≈ 326.7 */
  const c=326.7;
  const ring=$('#ringFg');
  ring.style.stroke = d.tier==='Hot'?'var(--hot)':(d.tier==='Warm'?'var(--warm)':'var(--expl)');
  ring.style.strokeDashoffset=c*(1-d.score/100);
  result.scrollIntoView({behavior:'smooth', block:'nearest'});
}
