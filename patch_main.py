import re

with open("main.py", "r") as f:
    code = f.read()

# 1. Imports
code = code.replace("import logging\nfrom datetime", "import logging\nimport json\nimport glob\nfrom datetime")

# 2. DATA_DIR
code = code.replace("START_TIME = time.time()\n", "START_TIME = time.time()\nimport os\nDATA_DIR = os.getenv(\"DATA_DIR\", os.path.join(os.path.dirname(os.path.abspath(__file__)), \"data\", \"dataset\"))\n")

# 3. CSS grid
code = code.replace(".grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}",
                    ".grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; margin-bottom: 32px; }}")

# 4. HTML Card
card_html = """<div class="container">
  <div class="grid">
    <div class="card" id="ctx-card">
      <h3>🧩 Context Initialization</h3>
      <div id="loader-status" style="margin-bottom: 16px; font-size: 0.85rem; color: #94a3b8;">
        <div>Loading coCategories...</div>
        <div>Loading Merchants...</div>
        <div>Loading Triggers...</div>
      </div>
      <div class="stat" style="flex-direction: column; align-items: flex-start; gap: 8px;">
        <label for="conf-cat" style="font-size: 0.85rem; color: #94a3b8;">coCategory</label>
        <select id="conf-cat" onchange="onContextChange()" style="width: 100%; background: #0d1117; border: 1px solid #374151; border-radius: 6px; padding: 8px 12px; color: #e2e8f0;" disabled><option value="">-- Loading --</option></select>
      </div>
      <div class="stat" style="flex-direction: column; align-items: flex-start; gap: 8px;">
        <label for="conf-merchant" style="font-size: 0.85rem; color: #94a3b8;">Merchant</label>
        <select id="conf-merchant" onchange="onContextChange()" style="width: 100%; background: #0d1117; border: 1px solid #374151; border-radius: 6px; padding: 8px 12px; color: #e2e8f0;" disabled><option value="">-- Loading --</option></select>
      </div>
      <div class="stat" style="flex-direction: column; align-items: flex-start; gap: 8px; border-bottom: none;">
        <label for="conf-trigger" style="font-size: 0.85rem; color: #94a3b8;">Trigger</label>
        <select id="conf-trigger" onchange="onContextChange()" style="width: 100%; background: #0d1117; border: 1px solid #374151; border-radius: 6px; padding: 8px 12px; color: #e2e8f0;" disabled><option value="">-- Loading --</option></select>
      </div>
      <button id="btn-start" onclick="startChat()" disabled style="margin-top: 16px; width: 100%; background: #1e3a5f; color: #bfdbfe; border: 1px solid #3b82f6; border-radius: 6px; padding: 10px; cursor: pointer; font-weight: 600; font-family: 'Inter', sans-serif; opacity: 0.5;">Start Chat</button>
      <div id="ctx-summary" style="margin-top: 16px; font-size: 0.8rem; color: #34d399; font-family: monospace;"></div>
    </div>
    <div class="card">
      <h3>📊 Live Status</h3>"""

code = code.replace("<div class=\"container\">\n  <div class=\"grid\">\n    <div class=\"card\">\n      <h3>📊 Live Status</h3>", card_html)

# 5. JS Logic
old_js = """<script>
  const BOT = window.location.origin;
  let convId = 'demo_meera_' + Date.now();
  // Real merchant from dataset: m_001_drmeera_dentist_delhi
  const MERCHANT_ID = 'm_001_drmeera_dentist_delhi';

  async function loadDemo() {{
    // REAL category context from dataset/categories/dentists.json
    await fetch(BOT+'/v1/context', {{method:'POST',headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        scope:'category', context_id:'dentists', version:1,
        delivered_at: new Date().toISOString(),
        payload:{{
          slug:'dentists',
          voice:{{tone:'peer_clinical', register:'doctor_to_doctor', vocab_taboo:['guaranteed','cure','permanent fix']}},
          offer_catalog:[
            {{id:'den_001',title:'Dental Cleaning @ \u20b9299',value:'299',anchor:'MRP \u20b9699'}},
            {{id:'den_002',title:'Root Canal (Single Sitting) @ \u20b92499',value:'2499'}},
            {{id:'den_003',title:'Clear Aligner Consult (Free)',value:'0'}}
          ],
          peer_stats:{{avg_rating:4.4, avg_calls_30d:12, avg_ctr:0.030, retention_6mo_pct:0.52}},
          digest:[{{
            id:'d_2026W17_jida_fluoride', kind:'research',
            title:'3-month fluoride recall cuts caries 38% better than 6-month',
            source:'JIDA Oct 2026, p.14', trial_n:2100, patient_segment:'high_risk_adults'
          }}],
          seasonal_beats:[
            {{month_range:'Nov-Feb', note:'exam-stress bruxism spike — night guards'}},
            {{month_range:'Mar-May', note:'wedding season aligners surge'}}
          ],
          trend_signals:[{{query:'clear aligners delhi', delta_yoy:0.62}}]
        }}
      }})
    }})
    // REAL merchant context from dataset/merchants_seed.json — m_001_drmeera_dentist_delhi
    await fetch(BOT+'/v1/context', {{method:'POST',headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        scope:'merchant', context_id: MERCHANT_ID, version:1,
        delivered_at: new Date().toISOString(),
        payload:{{
          merchant_id: MERCHANT_ID,
          category_slug:'dentists',
          identity:{{
            name:"Dr. Meera's Dental Clinic",
            city:'Delhi', locality:'Lajpat Nagar',
            verified:true, languages:['en','hi'],
            owner_first_name:'Meera', established_year:2018
          }},
          subscription:{{status:'active', plan:'Pro', days_remaining:82}},
          performance:{{
            window_days:30, views:2410, calls:18, ctr:0.021,
            delta_7d:{{views_pct:0.18, calls_pct:-0.05}}
          }},
          offers:[
            {{id:'o_meera_001',title:'Dental Cleaning @ \u20b9299',status:'active',started:'2026-03-01'}},
            {{id:'o_meera_002',title:'Deep Cleaning @ \u20b9499',status:'expired'}}
          ],
          customer_aggregate:{{
            total_unique_ytd:540, lapsed_180d_plus:78,
            retention_6mo_pct:0.38, high_risk_adult_count:124
          }},
          signals:['stale_posts:22d','ctr_below_peer_median','high_risk_adult_cohort'],
          conversation_history:[],
          review_themes:[
            {{theme:'wait_time',sentiment:'neg',occurrences_30d:3,common_quote:'had to wait 30 min on Sunday'}},
            {{theme:'doctor_manner',sentiment:'pos',occurrences_30d:5,common_quote:'Dr. Meera explains everything patiently'}}
          ]
        }}
      }})
    }})
  }}
  loadDemo();"""

new_js = """<script>
  const BOT = window.location.origin;
  let convId = 'demo_' + Date.now();
  let MERCHANT_ID = '';

  document.addEventListener("DOMContentLoaded", async () => {{
    await fetchDatasets();
  }});

  async function fetchDatasets() {{
    const statusDiv = document.getElementById('loader-status');
    statusDiv.innerHTML = '<div>Initiating dataset load...</div>';
    
    try {{
      const res = await fetch(BOT+'/v1/demo/load-datasets', {{method: 'POST'}});
      const counts = await res.json();
      statusDiv.innerHTML = `<div>coCategories loaded: ${{counts.categories}}</div>
                             <div>Merchants loaded: ${{counts.merchants}}</div>
                             <div>Triggers loaded: ${{counts.triggers}}</div>`;
                             
      const ctxRes = await fetch(BOT+'/v1/demo/available-contexts');
      const ctx = await ctxRes.json();
      
      populateSelect('conf-cat', ctx.categories);
      populateSelect('conf-merchant', ctx.merchants);
      populateSelect('conf-trigger', ctx.triggers);
      
    }} catch (e) {{
      statusDiv.innerHTML = `<div style="color: #ef4444;">Failed to load datasets. <a href="#" onclick="fetchDatasets()">Retry</a></div>`;
    }}
  }}
  
  function populateSelect(id, items) {{
    const sel = document.getElementById(id);
    if (!items || items.length === 0) {{
      sel.innerHTML = '<option value="">-- Empty --</option>';
      sel.disabled = true;
      return;
    }}
    sel.disabled = false;
    sel.innerHTML = '<option value="">-- None Selected --</option>';
    items.forEach(item => {{
      const opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item;
      sel.appendChild(opt);
    }});
  }}

  function onContextChange() {{
    const cat = document.getElementById('conf-cat').value;
    const mer = document.getElementById('conf-merchant').value;
    const trg = document.getElementById('conf-trigger').value;
    
    const btn = document.getElementById('btn-start');
    if (cat || mer || trg) {{
      btn.disabled = false;
      btn.style.opacity = 1;
    }} else {{
      btn.disabled = true;
      btn.style.opacity = 0.5;
    }}
    
    if (document.getElementById('msgs').innerHTML.includes('Configuration updated') || document.getElementById('msgs').innerHTML.includes('VERA')) {{
        updateContextSummary(cat, mer, trg);
        MERCHANT_ID = mer;
    }}
  }}

  function updateContextSummary(cat, mer, trg) {{
    const summary = `Context set &rarr; coCategory: ${{cat || 'None'}} | Merchant: ${{mer || 'None'}} | Trigger: ${{trg || 'None'}}`;
    document.getElementById('ctx-summary').innerHTML = summary;
  }}

  function startChat() {{
    const cat = document.getElementById('conf-cat').value;
    const mer = document.getElementById('conf-merchant').value;
    const trg = document.getElementById('conf-trigger').value;
    
    MERCHANT_ID = mer;
    updateContextSummary(cat, mer, trg);
    convId = 'demo_' + Date.now();
    
    document.getElementById('msgs').innerHTML = "<div class='msg vera'><div class='label'>VERA</div>Configuration updated. Hi! I'm Vera, magicpin's merchant AI. Ask me anything about your business.</div>";
  }}"""

code = code.replace(old_js, new_js)

# 6. Payload MERCHANT_ID update
code = code.replace("merchant_id: MERCHANT_ID,", "merchant_id: MERCHANT_ID || undefined,")

# 7. Endpoints
endpoints_code = """    return result

@app.post("/v1/demo/load-datasets")
async def load_datasets():
    cat_count = 0
    cat_files = glob.glob(os.path.join(DATA_DIR, "categories", "*.json"))
    for cf in cat_files:
        with open(cf, 'r') as f:
            data = json.load(f)
            slug = data.get("slug", os.path.basename(cf).replace(".json", ""))
            contexts[("category", slug)] = {"version": 1, "payload": data}
            cat_count += 1
            
    merch_count = 0
    merch_file = os.path.join(DATA_DIR, "merchants_seed.json")
    if os.path.exists(merch_file):
        with open(merch_file, 'r') as f:
            data = json.load(f)
            for m in data.get("merchants", []):
                contexts[("merchant", m["merchant_id"])] = {"version": 1, "payload": m}
                merch_count += 1
                
    trig_count = 0
    trig_file = os.path.join(DATA_DIR, "triggers_seed.json")
    if os.path.exists(trig_file):
        with open(trig_file, 'r') as f:
            data = json.load(f)
            for t in data.get("triggers", []):
                contexts[("trigger", t["id"])] = {"version": 1, "payload": t}
                trig_count += 1

    return {
        "categories": cat_count,
        "merchants": merch_count,
        "triggers": trig_count
    }

@app.get("/v1/demo/available-contexts")
async def get_available_contexts():
    categories = [ctx_id for (scope, ctx_id) in contexts if scope == "category"]
    merchants = [ctx_id for (scope, ctx_id) in contexts if scope == "merchant"]
    triggers = [ctx_id for (scope, ctx_id) in contexts if scope == "trigger"]
    return {
        "categories": sorted(categories),
        "merchants": sorted(merchants),
        "triggers": sorted(triggers)
    }

"""
code = code.replace("    return result\n", endpoints_code)

with open("main.py", "w") as f:
    f.write(code)

