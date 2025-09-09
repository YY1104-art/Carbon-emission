import streamlit as st
import yaml, json, pandas as pd, math
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(layout="wide", page_title="Carbon-aware LLM Placement Safe Version")
st.title("Carbon-aware LLM Placement — Safe Version")

# 初始化 session_state
for key in ["cfg_area","last_res","cfg_hash","expanded_clusters"]:
    if key not in st.session_state:
        st.session_state[key] = set() if key=="expanded_clusters" else None

# 上传或使用内置示例
uploaded = st.file_uploader("Upload YAML/JSON config", type=['yaml','yml','json'])
if uploaded:
    try:
        st.session_state["cfg_area"] = uploaded.read().decode('utf-8')
    except Exception as e:
        st.error(f"读取上传文件失败: {e}")

if not st.session_state.get("cfg_area"):
    example = {
        "cities":[{"name":"Zurich","Iv":0.013,"Hv":900,"lat":47.3769,"lon":8.5417},
                  {"name":"Paris","Iv":0.054,"Hv":3000,"lat":48.8566,"lon":2.3522},
                  {"name":"London","Iv":0.165,"Hv":2560,"lat":51.5074,"lon":-0.1278}],
        "tasks":[{"name":"LLM_NLP","Ta":500,"tap":40,"Ca":1,"Ua":500,"Pa":0.8},
                 {"name":"LLM_IR","Ta":700,"tap":80,"Ca":2,"Ua":150,"Pa":1.2}],
        "tsd":{"Zurich":{"Zurich":0,"Paris":10,"London":30},
               "Paris":{"Zurich":10,"Paris":0,"London":20},
               "London":{"Zurich":30,"Paris":20,"London":0}},
        "rav":{"0":{"Zurich":{"LLM_NLP":200,"LLM_IR":80},
                     "Paris":{"LLM_NLP":1000,"LLM_IR":400},
                     "London":{"LLM_NLP":1200,"LLM_IR":500}}},
        "duration_hours":1
    }
    st.session_state["cfg_area"] = yaml.safe_dump(example)

# 配置编辑区
cfg_area_new = st.text_area("Config (YAML)", value=st.session_state["cfg_area"], height=300)
cfg_hash_new = hash(cfg_area_new)
if cfg_hash_new != st.session_state.get("cfg_hash"):
    st.session_state["cfg_area"] = cfg_area_new
    st.session_state["cfg_hash"] = cfg_hash_new
    st.session_state["last_res"] = None
    st.session_state["expanded_clusters"].clear()

# 安全获取结果函数
def get_result():
    try:
        cfg = yaml.safe_load(st.session_state.get("cfg_area","")) or {}
        cities = cfg.get("cities", [])
        tasks = cfg.get("tasks", [])
        return {"placements": {"0": {c["name"]: {t["name"]: 100 for t in tasks} for c in cities}}}
    except Exception as e:
        st.error(f"生成示例结果失败: {e}")
        return {"placements": {}}

# 如果 last_res 为空，生成默认结果
if st.session_state["last_res"] is None:
    st.session_state["last_res"] = get_result()

res = st.session_state["last_res"]
placements = res.get("placements",{})

if not placements:
    st.warning("当前配置无城市或任务，请检查 YAML/JSON 文件内容。")
else:
    first_period = list(placements.keys())[0]
    try:
        cfg = yaml.safe_load(st.session_state["cfg_area"]) or {}
        cities = cfg.get("cities", [])
        tasks = [t["name"] for t in cfg.get("tasks",[])]
    except Exception as e:
        st.error(f"解析配置失败: {e}")
        cities=[]
        tasks=[]

    selected_tasks = st.multiselect("Select tasks to display", tasks, default=tasks)

    # 可调参数
    label_size = st.slider("Task label font size",8,20,12)
    circle_radius = st.slider("Task circle radius",0.1,1.0,0.3)
    city_offset = st.slider("City minimal offset",0.05,1.0,0.2)
    cluster_radius = st.slider("Cluster radius",0.5,3.0,1.0)
    auto_expand_threshold = st.slider("Auto expand total threshold",50,1000,250)

    # 构建城市数据
    rows=[]
    for c in cities:
        r={"name":c.get("name",""),"lat":c.get("lat"),"lon":c.get("lon")}
        ps=placements.get(first_period,{}).get(c.get("name",""),{})
        for t in selected_tasks: r[t]=ps.get(t,0)
        r["total"]=sum(r[t] for t in selected_tasks)
        rows.append(r)
    df=pd.DataFrame(rows)

    # 避免重叠
    df['lat_adj']=df['lat']; df['lon_adj']=df['lon']
    min_dist=city_offset
    for i in range(len(df)):
        for j in range(i+1,len(df)):
            dlat=df.loc[i,'lat_adj']-df.loc[j,'lat_adj']
            dlon=df.loc[i,'lon_adj']-df.loc[j,'lon_adj']
            dist=math.sqrt(dlat**2+dlon**2)
            if dist<min_dist:
                df.loc[j,'lat_adj']+=(min_dist-dist)/2
                df.loc[j,'lon_adj']+=(min_dist-dist)/2

    # 聚合城市
    clusters=[]; used=set()
    for i,row in df.iterrows():
        if i in used: continue
        cluster=[i]
        for j,row2 in df.iterrows():
            if j<=i or j in used: continue
            dlat=row['lat_adj']-row2['lat_adj']
            dlon=row['lon_adj']-row2['lon_adj']
            dist=math.sqrt(dlat**2+dlon**2)
            if dist<=cluster_radius: cluster.append(j); used.add(j)
        clusters.append(cluster)

    # 自动展开聚合点 + 手动展开
    expanded_clusters = set()
    for idx,cluster in enumerate(clusters):
        if len(cluster)==1 or df.loc[cluster,'total'].sum()>=auto_expand_threshold:
            expanded_clusters.add(idx)
    expanded_clusters = expanded_clusters.union(st.session_state["expanded_clusters"])

    # 手动展开按钮
    st.subheader("Cluster control")
    for idx,cluster in enumerate(clusters):
        if len(cluster)>1:
            label=f"Toggle cluster {idx} ({len(cluster)} cities)"
            if st.button(label, key=f"cluster_btn_{idx}"):
                if idx in st.session_state["expanded_clusters"]:
                    st.session_state["expanded_clusters"].remove(idx)
                else:
                    st.session_state["expanded_clusters"].add(idx)
                st.experimental_rerun()

    # 绘制地图
    fig=go.Figure()
    colors=px.colors.qualitative.Plotly
    for idx,cluster in enumerate(clusters):
        if idx in expanded_clusters:
            for i in cluster:
                row=df.loc[i]
                hover_text=f"{row['name']}<br>"+"<br>".join([f"{t}: {row[t]}" for t in selected_tasks])
                fig.add_trace(go.Scattergeo(
                    lon=[row['lon_adj']],lat=[row['lat_adj']],
                    text=[hover_text], hoverinfo='text',
                    mode='markers+text',
                    marker=dict(size=row['total']+1,color='blue'),
                    textposition="top center",
                    showlegend=False
                ))
                n=len(selected_tasks)
                for j,t in enumerate(selected_tasks):
                    angle=2*math.pi*j/n
                    offset_lat=circle_radius*math.sin(angle)
                    offset_lon=circle_radius*math.cos(angle)
                    fig.add_trace(go.Scattergeo(
                        lon=[row['lon_adj']+offset_lon],
                        lat=[row['lat_adj']+offset_lat],
                        text=[f"{t}: {row[t]}"],
                        mode='text',
                        textfont=dict(color=colors[j%len(colors)],size=label_size),
                        showlegend=False
                    ))
        else:
            lat_mean=df.loc[cluster,'lat_adj'].mean()
            lon_mean=df.loc[cluster,'lon_adj'].mean()
            total_sum=df.loc[cluster,'total'].sum()
            hover_text=f"Cluster ({len(cluster)} cities, Total: {total_sum})<br>" + \
                       "<br>".join([f"{df.loc[i,'name']}: {df.loc[i,'total']}" for i in cluster])
            fig.add_trace(go.Scattergeo(
                lon=[lon_mean],lat=[lat_mean],
                text=[hover_text], hoverinfo='text',
                mode='markers+text',
                marker=dict(size=total_sum+3,color='red',symbol='diamond'),
                textposition="top center",
                showlegend=False
            ))

    lats=df['lat_adj']; lons=df['lon_adj']
    fig.update_geos(lataxis_range=[lats.min()-1,lats.max()+1],
                    lonaxis_range=[lons.min()-1,lons.max()+1])
    st.plotly_chart(fig,use_container_width=True)
