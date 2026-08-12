const $ = (s) => document.querySelector(s);
const fmt = (v) => v == null ? "N/A" : Number(v).toFixed(3);
const escapeHTML = (value) => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const metricLabels = {context_recall:"Context recall",context_precision:"Context precision",faithfulness:"Faithfulness",relevance:"Relevance",completeness:"Completeness",overall:"Overall"};
let benchmarkById = {};
let deepEvalById = {};
let benchmarkResults = [];
let tableSort = {key:'overall', direction:'asc'};

const sortLabels = {id:'ID',difficulty:'Difficulty',context_recall:'Recall',context_precision:'Precision',faithfulness:'Faithfulness',relevance:'Relevance',completeness:'Completeness',overall:'Overall',passed:'Status'};
const difficultyOrder = {easy:0,medium:1,hard:2,adversarial:3};

function metricCards(metrics){
  return Object.entries(metricLabels).map(([key,label])=>{
    const value=metrics[key]; const pct=value==null?0:Math.max(0,Math.min(100,value*100));
    return `<div class="meter"><small>${label}</small><strong>${fmt(value)}</strong><div class="bar"><i style="width:${pct}%"></i></div></div>`;
  }).join("");
}

function renderDifficultySummary(results){
  const types=[
    ['easy','Easy','Direct lookup'],
    ['medium','Medium','Conditions & workflows'],
    ['hard','Hard','Multi-policy reasoning'],
    ['adversarial','Adversarial','Safety & robustness']
  ];
  $('#difficulty-summary').innerHTML=types.map(([key,label,description])=>{
    const cases=results.filter(row=>row.difficulty===key);
    const passed=cases.filter(row=>row.passed).length;
    const total=cases.length;
    const rate=total?passed/total:0;
    const pct=Math.round(rate*100);
    const tone=pct>=80?'strong':pct>=60?'steady':'risk';
    return `<article class="difficulty-card ${key} ${tone}">
      <div class="difficulty-top"><span class="difficulty-name">${label}</span><span class="difficulty-count">${passed}/${total} passed</span></div>
      <strong>${pct}%</strong>
      <p>${description}</p>
      <div class="difficulty-track" aria-label="${label} pass rate ${pct} percent"><i style="width:${pct}%"></i></div>
    </article>`;
  }).join('');
}

function compareRows(a,b,key){
  if(key==='difficulty') return difficultyOrder[a.difficulty]-difficultyOrder[b.difficulty] || a.id.localeCompare(b.id,undefined,{numeric:true});
  if(key==='id') return a.id.localeCompare(b.id,undefined,{numeric:true});
  if(key==='passed') return Number(a.passed)-Number(b.passed) || a.overall-b.overall;
  return (Number(a[key])||0)-(Number(b[key])||0);
}

function renderResultsTable(){
  const {key,direction}=tableSort;
  const rows=[...benchmarkResults].sort((a,b)=>compareRows(a,b,key)*(direction==='asc'?1:-1));
  $('#results').innerHTML=rows.map(r=>{
    const d=deepEvalById[r.id];
    const difficultyLabel=r.difficulty[0].toUpperCase()+r.difficulty.slice(1);
    return `<tr data-case="${r.id}"><td><b>${r.id}</b></td><td><span class="difficulty-badge ${r.difficulty}"><i></i>${difficultyLabel}</span></td><td>${fmt(r.context_recall)}</td><td>${fmt(r.context_precision)}</td><td>${fmt(r.faithfulness)}</td><td>${fmt(r.relevance)}</td><td>${fmt(r.completeness)}</td><td><b>${fmt(r.overall)}</b></td><td><span class="pill ${r.passed?'pass':'fail'}">${r.passed?'PASS':'FAIL'}</span></td><td>${d?'<button class="compare-button">Compare</button>':'—'}</td></tr>`;
  }).join('');
  document.querySelectorAll('.sort-button').forEach(button=>{
    const active=button.dataset.sort===key;
    button.classList.toggle('active',active);
    button.classList.toggle('asc',active&&direction==='asc');
    button.classList.toggle('desc',active&&direction==='desc');
  });
  $('#sort-status').textContent=`${sortLabels[key]} · ${direction==='asc'?'lowest first':'highest first'}`;
  document.querySelectorAll('[data-case] .compare-button').forEach(button=>button.addEventListener('click',()=>renderDeepEvalCase(button.closest('tr').dataset.case)));
}

async function loadDashboard(){
  const [benchmark, questions, deepEval] = await Promise.all([fetch('/api/benchmark').then(r=>r.json()),fetch('/api/golden-questions').then(r=>r.json()),fetch('/api/deepeval').then(r=>r.json())]);
  benchmarkResults=benchmark.results;
  benchmarkById=Object.fromEntries(benchmark.results.map(row=>[row.id,row]));
  deepEvalById=Object.fromEntries((deepEval.results||[]).map(row=>[row.id,row]));
  const s=benchmark.summary;
  $('#summary').innerHTML=[['Pass rate',`${(s.pass_rate*100).toFixed(0)}%`],['Ctx recall',fmt(s.avg_context_recall)],['Ctx precision',fmt(s.avg_context_precision)],['Faithfulness',fmt(s.avg_faithfulness)],['Relevance',fmt(s.avg_relevance)],['Completeness',fmt(s.avg_completeness)]].map(([l,v])=>`<div class="stat"><small>${l}</small><strong>${v}</strong></div>`).join('');
  renderDifficultySummary(benchmark.results);
  renderResultsTable();
  $('#examples').innerHTML+=[...questions].map(q=>`<option value="${q.question.replaceAll('"','&quot;')}">${q.id} · ${q.question}</option>`).join('');
  renderDeepEvalStatus(deepEval);
}

document.querySelectorAll('.sort-button').forEach(button=>button.addEventListener('click',()=>{
  const key=button.dataset.sort;
  tableSort=tableSort.key===key?{key,direction:tableSort.direction==='asc'?'desc':'asc'}:{key,direction:'asc'};
  renderResultsTable();
}));

function renderDeepEvalStatus(data){
  $('#deepeval-model').textContent=data.judge_model?`Judge: ${data.judge_model}`:'';
  if(!data.available){$('#deepeval-content').className='empty-note';$('#deepeval-content').innerHTML=`<strong>DeepEval LLM results not available.</strong><p>${data.message||'Run compare_deepeval.py first.'}</p><code>python -u compare_deepeval.py</code>`;return}
  const keys=['faithfulness','answer_relevancy','contextual_recall','contextual_precision','contextual_relevancy'];
  const averages=Object.fromEntries(keys.map(k=>[k,data.results.reduce((sum,r)=>sum+Number(r[k]),0)/data.results.length]));
  $('#deepeval-content').className='';
  $('#deepeval-content').innerHTML=`<p><b>${data.results.length}</b> complete DeepEval cases. Select <b>Compare</b> in the table to see deltas and judge reasons.</p><div class="deep-summary">${keys.map(k=>`<div class="meter"><small>${k.replaceAll('_',' ')}</small><strong>${fmt(averages[k])}</strong></div>`).join('')}</div>`;
}

function renderDeepEvalCase(id){
  const core=benchmarkById[id], deep=deepEvalById[id]; if(!core||!deep)return;
  const rows=[['Faithfulness',core.faithfulness,deep.faithfulness],['Relevance',core.relevance,deep.answer_relevancy],['Context recall',core.context_recall,deep.contextual_recall],['Context precision',core.context_precision,deep.contextual_precision],['Context relevancy',null,deep.contextual_relevancy]];
  $('#deepeval-content').innerHTML=`<h3>${id} · recorded evaluation</h3><p class="comparison-note">DeepEval scores refer to the recorded answer in <code>actual_answers.json</code>, not a newly generated live answer.</p><div class="comparison-grid"><b>Metric</b><b>Core</b><b>DeepEval</b><b>Delta</b>${rows.map(([n,c,d])=>`<span>${n}</span><span>${fmt(c)}</span><span>${fmt(d)}</span><span>${c==null?'N/A':`${d-c>=0?'+':''}${(d-c).toFixed(3)}`}</span>`).join('')}</div><details open><summary>DeepEval reasons</summary>${['faithfulness','answer_relevancy','contextual_recall','contextual_precision','contextual_relevancy'].map(k=>`<p><b>${k.replaceAll('_',' ')}:</b> ${deep[`${k}_reason`]||'No reason returned.'}</p>`).join('')}</details>`;
  document.querySelector('.deepeval-panel').scrollIntoView({behavior:'smooth',block:'start'});
}

$('#examples').addEventListener('change',e=>{if(e.target.value)$('#question').value=e.target.value});
$('#ask-button').addEventListener('click',async()=>{
  const question=$('#question').value.trim(); if(!question)return;
  const button=$('#ask-button'); button.disabled=true; button.textContent='Running retrieval + generation…'; $('#error').textContent='';
  try{
    const res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})}); const data=await res.json(); if(!res.ok)throw new Error(data.error||'Request failed');
    $('#live-metrics').classList.remove('empty'); $('#live-metrics').innerHTML=metricCards(data.metrics);
    $('#trace').classList.remove('hidden'); $('#answer').textContent=data.answer; $('#gold-badge').textContent=data.matched_golden?`Golden match · ${data.matched_golden}`:'Custom question · 2 answer metrics';
    $('#expected-wrap').style.display=data.expected_answer?'block':'none'; $('#expected').textContent=data.expected_answer||'';
    const topScore=Math.max(...data.chunks.map(c=>Number(c.score)||0),1);
    $('#chunks').innerHTML=data.chunks.map((c,i)=>{
      const score=Number(c.score)||0;
      const strength=Math.max(4,Math.min(100,(score/topScore)*100));
      return `<article class="chunk ${i===0?'chunk-best':''}">
        <div class="rank"><small>RANK</small><b>${String(i+1).padStart(2,'0')}</b><span>${i===0?'Best match':'Candidate'}</span></div>
        <div class="chunk-body">
          <div class="chunk-title"><h3>${escapeHTML(c.source_doc)}</h3><span class="chunk-id">${escapeHTML(c.chunk_id)}</span></div>
          <p>${escapeHTML(c.text)}</p>
          <div class="chunk-footer">
            <div class="score-label"><span>BM25 relevance</span><strong>${score.toFixed(4)}</strong></div>
            <div class="score-track" aria-label="Relative BM25 strength"><i style="width:${strength}%"></i></div>
          </div>
        </div>
      </article>`;
    }).join('');
    $('#trace').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(err){$('#error').textContent=err.message}finally{button.disabled=false;button.innerHTML='Run pipeline <span>→</span>'}
});

loadDashboard().catch(err=>{$('#error').textContent=`Dashboard data error: ${err.message}`});
