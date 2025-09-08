
import streamlit as st
import yaml, json, requests, pandas as pd, plotly.express as px
st.set_page_config(layout="wide", page_title="Carbon-aware LLM Placement v2")
st.title("Carbon-aware LLM Placement — v2")

uploaded = st.file_uploader("Upload YAML/JSON config", type=['yaml','yml','json'], accept_multiple_files=False)
cfg_text = None
if uploaded is not None:
    try:
        cfg_text = uploaded.read().decode('utf-8')
    except Exception as e:
        st.error("Failed to read uploaded file: "+str(e))

if st.button("Use built-in example") or cfg_text is None:
    example = {
        "cities":[{"name":"Zurich","Iv":0.013,"Hv":900,"lat":47.3769,"lon":8.5417},{"name":"Paris","Iv":0.054,"Hv":3000,"lat":48.8566,"lon":2.3522},{"name":"London","Iv":0.165,"Hv":2560,"lat":51.5074,"lon":-0.1278}],
        "tasks":[{"name":"LLM_NLP","Ta":500,"tap":40,"Ca":1,"Ua":500,"Pa":0.8},{"name":"LLM_IR","Ta":700,"tap":80,"Ca":2,"Ua":150,"Pa":1.2}],
        "tsd":{"Zurich":{"Zurich":0,"Paris":10,"London":30},"Paris":{"Zurich":10,"Paris":0,"London":20},"London":{"Zurich":30,"Paris":20,"London":0}},
        "rav":{"0":{"Zurich":{"LLM_NLP":200,"LLM_IR":80},"Paris":{"LLM_NLP":1000,"LLM_IR":400},"London":{"LLM_NLP":1200,"LLM_IR":500}}},
        "duration_hours":1
    }
    cfg_text = yaml.safe_dump(example)

st.text_area("Config (YAML)", value=cfg_text, height=300, key="cfg_area")
col1, col2 = st.columns([1,1])
with col1:
    if st.button("Run locally (call backend.optimizer)"):
        try:
            from backend import optimizer
            cfg = yaml.safe_load(st.session_state["cfg_area"])
            res = optimizer.optimize_from_dict(cfg)
            st.session_state["last_res"] = res
            st.success("Finished: method="+res.get("method","?"))
        except Exception as e:
            st.error("Local run failed: "+str(e))
with col2:
    api_url = st.text_input("API URL", value="http://localhost:8000/optimize")
    if st.button("Call API"):
        try:
            payload = {"yaml": st.session_state["cfg_area"]}
            r = requests.post(api_url, json=payload, timeout=60)
            st.session_state["last_res"] = r.json()
            st.success("API responded: HTTP "+str(r.status_code))
        except Exception as e:
            st.error("API call failed: "+str(e))

if "last_res" in st.session_state:
    res = st.session_state["last_res"]
    st.subheader("Result overview")
    st.json(res if isinstance(res, dict) else json.loads(res))
    # If placements present, show map
    try:
        placements = res.get("result",{}).get("placements", res.get("placements",{}))
        # take first period
        first = list(placements.keys())[0]
        rows = []
        cities = yaml.safe_load(st.session_state["cfg_area"]).get("cities", [])
        for c in cities:
            r = {"name":c["name"],"Iv":c.get("Iv",None),"lat":c.get("lat",None),"lon":c.get("lon",None)}
            ps = placements[first].get(c["name"],{})
            for k,v in ps.items(): r[k]=v
            rows.append(r)
        df = pd.DataFrame(rows)
        if not df.empty and df['lat'].notnull().all():
            fig = px.scatter_geo(df, lat='lat', lon='lon', hover_name='name', size=df.iloc[:,4].fillna(0)+1,
                                 projection="natural earth", title="Placements (period="+str(first)+")")
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.write("Map rendering skipped:", e)
